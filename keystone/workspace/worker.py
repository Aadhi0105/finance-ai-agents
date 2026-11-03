"""Single offline worker. A claimed operation is never automatically executed twice."""
import argparse
import os
from pathlib import Path
import signal
import sys
import threading

from keystone.maintenance import ROOT, gate
from keystone import operation
from .job_contract import JobError, now
from .job_delivery import publish_result, verified_result
from .job_files import prepare_inputs
from .job_store import JobStore, private_member


def offline_environment(root):
    allowed = {'PATH', 'LANG', 'LC_ALL', 'TZ', 'TMPDIR', 'SYSTEMROOT'}
    env = {k:v for k,v in os.environ.items() if k in allowed}
    env.update(PYTHONNOUSERSITE='1', AGENT_STATS_VIA_MCP='0', AGENT_DATA_SOURCE='fixture',
               LM_DICTIONARY_CSV='', OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1',
               MPLCONFIGDIR=str(Path(root) / 'runtime' / 'matplotlib'))
    return env


def run_one(store):
    """Main-thread worker entry; the inherited CLI gate covers the entire attempt."""
    with store._connect(write=False) as con:
        if store.next_queued(con) is None:
            return False, False
    with gate():
        record = store.claim_next()
        if record is None:
            return False, False
        result = None
        dispatched = False
        op = None
        try:
            if ((store.root / 'jobs' / record.job_id).exists()
                    or (store.root / 'operations' / record.operation_id).exists()):
                store.update_execution(record.job_id, event='interrupted', status='outcome_unknown',
                    finished_at=now(), reason='interrupted', operation_status='outcome_unknown')
                return True, False
            folder = prepare_inputs(store, record)
            store.update_execution(record.job_id, event='inputs_verified', inputs_verified_at=now(), operation_status='running')
            dispatched = True
            _, _, op = operation.execute('workspace-saved', [str(folder)], record.operation_id,
                directory=store.root / 'operations', allow_paid=False, allow_live_data=False,
                timeout=record.request.timeout_seconds, max_requests=record.max_requests,
                max_output_tokens=record.max_output_tokens, environment=offline_environment(store.root),
                lease_fds=(store._lease,))
            if op['status'] not in {'completed','review_required'}:
                unknown = op['status'] == 'outcome_unknown'
                store.update_execution(record.job_id, event='interrupted' if unknown else 'failed',
                    status='outcome_unknown' if unknown else 'failed', finished_at=now(),
                    reason='interrupted' if unknown else 'execution_failed', operation_status=op['status'])
                return True, op.get('termination') == 'cancelled'
            commit_values = {}
            if record.schema_version == 3:
                from .onboarding.close_state import committed, remember
                from .onboarding.store import InputStore
                inputs = InputStore(store.workspace.parent)
                _,proof = committed(inputs,record)
                commit_values['accounting_commit_sha256'] = remember(inputs,proof)
            if record.schema_version==4:
                from .onboarding.research.delivery import commit_hash
                commit_values['analysis_commit_sha256']=commit_hash(store,record)
            result, _, _ = verified_result(store, record)
            store.update_execution(record.job_id, event='prepared', result=result.model_dump(), operation_status=op['status'],**commit_values)
            publish_result(store, record, result)
            store.update_execution(record.job_id, event='registered', status='review_required',
                finished_at=now(), reason='registered')
            if record.schema_version == 3:
                from .onboarding.close_state import resolve
                resolve(inputs,record)
            return True, False
        except (KeyboardInterrupt, SystemExit):
            store.update_execution(record.job_id, event='interrupted', status='outcome_unknown',
                finished_at=now(), reason='interrupted', operation_status='outcome_unknown')
            return True, True
        except Exception as error:
            if isinstance(error,JobError) and error.code=='job_source_unavailable':
                store.update_execution(record.job_id,event='source_changed',status='source_changed',finished_at=now(),reason='source_changed')
            elif result is not None:
                store.update_execution(record.job_id, event='delivery_failed', status='delivery_failed',
                    finished_at=now(), reason='delivery_failed', result=result.model_dump(),
                    operation_status=op['status'])
            elif not dispatched and isinstance(error, JobError) and error.code == 'job_recovery_unavailable':
                store.update_execution(record.job_id, event='interrupted', status='outcome_unknown',
                    finished_at=now(), reason='interrupted', operation_status='outcome_unknown')
            else:
                unknown = dispatched and op is None
                store.update_execution(record.job_id, event='interrupted' if unknown else 'failed',
                    status='outcome_unknown' if unknown else 'failed', finished_at=now(),
                    reason='interrupted' if unknown else 'execution_failed',
                    operation_status='outcome_unknown' if unknown else op['status'] if op else 'not_started')
            return True, False


def recover_delivery(store, job_id):
    """Explicit delivery-only recovery; never calls execute or the render/replay spine."""
    with gate():
        public = store.get(job_id)['job']
        if public['status'] == 'running':
            # The recovery caller already owns the exclusive worker lease, and
            # this gate excludes a surviving supervised child. Record the orphaned
            # attempt before inspecting its saved output; never dispatch it again.
            store.update_execution(job_id, event='interrupted', status='outcome_unknown',
                finished_at=now(), reason='interrupted')
            public = store.get(job_id)['job']
        record = store.immutable(job_id)
        if record.schema_version == 3:
            return recover_close_delivery(store,record,public)
        if public['status'] not in ({'failed'} if record.schema_version==4 else set())|{'delivery_failed','outcome_unknown','completed','review_required'}:
            raise JobError('job_recovery_unavailable', 409)
        record = store.immutable(job_id)
        from .job_execution import parse_execution
        old = parse_execution(public['execution'])
        result, _, saved = verified_result(store, record, old.result)
        publish_result(store, record, result)
        if old.status not in {'completed','review_required'}:
            commit_values={}
            if record.schema_version==4:
                from .onboarding.research.delivery import commit_hash
                commit_values['analysis_commit_sha256']=commit_hash(store,record)
            store.update_execution(job_id, event='recovered', status='review_required', finished_at=now(),
                reason='recovered', result=result.model_dump(), operation_status=saved['status'],
                inputs_verified_at=old.inputs_verified_at or now(),
                **commit_values)
        return store.get(job_id)


def recover_close_delivery(store,record,public):
    """Worker lease and gate are held. Read frozen accounting evidence only."""
    from .job_execution import parse_execution
    from .onboarding.store import InputStore
    from .onboarding import close_state
    from .onboarding.execution import render
    from .job_files import read_job
    import uuid
    inputs = InputStore(store.workspace.parent)
    old = parse_execution(public['execution'])
    if old.status not in {'failed','outcome_unknown','delivery_failed','completed','review_required'}:
        raise JobError('job_recovery_unavailable',409)
    folder = store.root/'jobs'/record.job_id
    if read_job(folder) != record: raise JobError('job_recovery_unavailable',409)
    # Successful deliveries can be reopened after later closes using their
    # immutable proof. Interrupted deliveries must first prove an actual commit.
    if old.status in {'completed','review_required'}:
        result,_,_ = verified_result(store,record,old.result)
        publish_result(store,record,result)
        close_state.resolve(inputs,record)
        return store.get(record.job_id)
    saved,proof = close_state.committed(inputs,record,recovery=True)
    commit_sha = close_state.remember(inputs,proof)
    from .job_delivery import operation_proof
    operation_proof(store,record,committed_close=True)
    try: result,_,op = verified_result(store,record,old.result)
    except Exception:
        if old.result is not None: raise
        # Preserve partial delivery bytes for inspection. Nothing is overwritten.
        pending = folder/'result'
        if pending.exists() or pending.is_symlink():
            private_member(pending,directory=True)
            os.rename(pending,folder/('held-result-'+uuid.uuid4().hex))
        render(folder,record,saved_close=(saved,proof))
        result,_,op = verified_result(store,record)
    publish_result(store,record,result)
    store.update_execution(record.job_id,event='recovered',status='review_required',finished_at=now(),
        reason='recovered',result=result.model_dump(),operation_status=op['status'],
        inputs_verified_at=old.inputs_verified_at or now(),accounting_commit_sha256=commit_sha)
    close_state.resolve(inputs,record)
    return store.get(record.job_id)


def release_uncommitted_close(store,job_id):
    """Explicit operator inspection, never a requeue or financial execution."""
    from .onboarding.store import InputStore
    from .onboarding.close_state import resolve
    with gate():
        record = store.immutable(job_id); public = store.get(job_id)['job']
        if record.schema_version != 3 or public['status'] not in {'failed','outcome_unknown','source_changed'}:
            raise JobError('job_recovery_unavailable',409)
        resolve(InputStore(store.workspace.parent),record,no_commit=True)
        return dict(job_id=job_id,status=public['status'],resolution='no_commit_verified',financial_approval=False)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--jobs-dir', type=Path, required=True)
    parser.add_argument('--parent-pid', type=int)
    parser.add_argument('--ready-fd', type=int)
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args(argv)
    stop = threading.Event()
    store = None
    def interrupted(*_):
        stop.set()
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    def parent_watch():
        while not stop.wait(.25):
            if os.getppid() != args.parent_pid:
                os.kill(os.getpid(), signal.SIGTERM)
                return
    try:
        if args.parent_pid is not None and os.getppid() != args.parent_pid:
            return 2
        store = JobStore(args.jobs_dir, args.workspace, worker=True)
        private_member(store.workspace, directory=True)
        private_member(store.workspace / 'runs', directory=True)
        store.interrupt_running()
        if args.ready_fd is not None:
            os.write(args.ready_fd, b'1')
            os.close(args.ready_fd)
        if args.parent_pid is not None:
            threading.Thread(target=parent_watch, daemon=True).start()
        while not stop.is_set():
            try:
                _, cancelled = run_one(store)
                if cancelled or args.once:
                    break
            except (RuntimeError, BlockingIOError):
                # A busy cooperative gate does not consume a queued identity.
                pass
            if args.parent_pid is not None and os.getppid() != args.parent_pid:
                break
            stop.wait(.25)
        return 0
    except (KeyboardInterrupt, SystemExit):
        return 130
    except Exception:
        return 2
    finally:
        stop.set()
        if store is not None:
            store.close()


if __name__ == '__main__':
    raise SystemExit(main())
