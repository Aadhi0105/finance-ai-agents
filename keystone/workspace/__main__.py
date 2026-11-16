"""Prepare/serve synthetic evidence, with optional protected job admission."""
import argparse
import json
from pathlib import Path
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    prepare = commands.add_parser('prepare', help='Generate a new offline synthetic workspace')
    prepare.add_argument('--destination', type=Path, default=Path('output/workspace-demo'))
    prepare.add_argument('--native', action='store_true', help='Register native report data (catalogue v2)')
    private = commands.add_parser('prepare-private', help='Create a fresh private input/report workspace')
    private.add_argument('--destination',type=Path,required=True)
    private.add_argument('--name',required=True)
    permission = commands.add_parser('install-source-permission',help='Install an operator-reviewed, content-scoped local permission record')
    permission.add_argument('--workspace',type=Path,required=True)
    permission.add_argument('--record',type=Path,required=True)
    permission.add_argument('--evidence',type=Path,required=True)
    revoke = commands.add_parser('revoke-source-permission',help='Hold further use of a local source permission')
    revoke.add_argument('--workspace',type=Path,required=True)
    revoke.add_argument('--permission-id',required=True)
    revoke.add_argument('--reason',required=True)
    recover_input=commands.add_parser('recover-import',help='Accept verified prepared input without validation or financial reexecution')
    recover_input.add_argument('--workspace',type=Path,required=True)
    recover_input.add_argument('--import-id',required=True)
    snapshot_input=commands.add_parser('snapshot-private',help='Capture a permission-checked local private workspace snapshot after stopping its server')
    snapshot_input.add_argument('--workspace',type=Path,required=True)
    snapshot_input.add_argument('--destination',type=Path,required=True)
    audit=commands.add_parser('audit-private',help='Check retained evidence after stopping the workspace server; no repair or deletion')
    audit.add_argument('--workspace',type=Path,required=True)
    restored=commands.add_parser('restore-private',help='Verify and restore a private snapshot to a fresh directory; hold queued work')
    restored.add_argument('snapshot',type=Path)
    restored.add_argument('--destination',type=Path,required=True)
    resumed=commands.add_parser('release-restored-job',help='Recheck and release one never-started restored request; no processing')
    resumed.add_argument('--workspace',type=Path,required=True)
    resumed.add_argument('--job-id',required=True)
    resumed.add_argument('--reason',required=True)
    project = commands.add_parser('project', help='Project registered synthetic evidence into a new native workspace')
    project.add_argument('--workspace', type=Path, required=True)
    project.add_argument('--destination', type=Path, required=True)
    serve = commands.add_parser('serve', help='Serve the explicit workspace on loopback only')
    serve.add_argument('--workspace', type=Path, default=Path('output/workspace-demo'))
    serve.add_argument('--port', type=int, default=8765)
    serve.add_argument('--enable-job-admission', action='store_true',
                       help='Accept protected offline saved-evidence jobs')
    serve.add_argument('--enable-worker', action='store_true', help='Start the supervised offline background worker')
    serve.add_argument('--enable-imports',action='store_true',help='Accept protected input packages in a private workspace')
    serve.add_argument('--enable-review-notes',action='store_true',help='Record protected analyst notes; no financial decisions or approval')
    serve.add_argument('--enable-review-corrections',action='store_true',help='Link validated replacement inputs to reviewed reports; no automatic execution or approval')
    serve.add_argument('--enable-review-decisions',action='store_true',help='Record analyst dispositions with history; no authenticated financial approval')
    serve.add_argument('--jobs-dir', type=Path,
                       help='Private control directory outside the report workspace (default state/workspace-jobs)')
    recover = commands.add_parser('recover-job', help='Recover verified saved delivery without executing the job again')
    recover.add_argument('--workspace', type=Path, required=True)
    recover.add_argument('--jobs-dir', type=Path, required=True)
    recover.add_argument('--job-id', required=True)
    recover_private=commands.add_parser('recover-private-job',help='Inspect and recover saved job delivery after stopping this private server and worker; no financial reexecution')
    recover_private.add_argument('--workspace',type=Path,required=True,help='Private workspace root')
    recover_private.add_argument('--job-id',required=True)
    release = commands.add_parser('release-uncommitted-close', help='Inspect and release a failed close intent only when no accounting commit exists')
    release.add_argument('--workspace', type=Path, required=True, help='Private workspace root')
    release.add_argument('--job-id', required=True)
    args = parser.parse_args(argv)
    if args.command=='audit-private':
        from .lifecycle import audit_private
        try:
            result=audit_private(args.workspace)
            print(json.dumps(result))
            return 0 if result['state']=='verified' else 2
        except Exception:
            print(json.dumps(dict(error=dict(code='evidence_audit_unavailable',
                message='Stop this workspace server and worker, preserve saved evidence, and inspect local storage before retrying.'))),file=sys.stderr)
            return 2
    elif args.command=='restore-private':
        from .onboarding.recovery import restore_private
        from .onboarding.contracts import InputError
        try:
            root=restore_private(args.snapshot,args.destination)
            print(json.dumps(dict(restored=str(root),protection='local_restore_test_only',
                                  queued_execution='held_for_operator_review',financial_approval=False)))
        except Exception:
            print(json.dumps(InputError('input_unavailable',503).envelope()),file=sys.stderr)
            return 2
    elif args.command in {'release-restored-job','recover-private-job','recover-import','release-uncommitted-close'}:
        from .onboarding.recovery import release_restored_job
        from .recovery_support import operator_store
        from .onboarding.store import InputStore
        from .worker import recover_delivery,release_uncommitted_close
        from .job_contract import JobError
        try:
            with operator_store(args.workspace) as store:
                inputs=InputStore(args.workspace,recover=True)
                if args.command=='release-restored-job':result=release_restored_job(store,args.job_id,args.reason)
                elif args.command=='recover-import':result=inputs.recover(args.import_id)
                elif args.command=='release-uncommitted-close':result=release_uncommitted_close(store,args.job_id)
                else:
                    job=recover_delivery(store,args.job_id)['job']
                    result=dict(job_id=job['job_id'],status=job['status'],result_run_id=job['execution']['result']['run_id'],
                                financial_execution_started=False,financial_approval=False)
                print(json.dumps(result))
            return 0
        except Exception:
            print(json.dumps(JobError('job_recovery_unavailable',409).envelope()),file=sys.stderr)
            return 2
    elif args.command in {'prepare-private','install-source-permission','revoke-source-permission','snapshot-private'}:
        from .onboarding.store import create_workspace,InputStore
        from .onboarding.contracts import InputError
        from .catalog import read_confined,read_json
        try:
            if args.command=='prepare-private':
                root=create_workspace(args.destination,args.name)
                result={'workspace':str(root),'workspace_id':InputStore(root).descriptor['id'],
                        'classification':'private','production_release_approved':False}
            else:
                inputs=InputStore(args.workspace,recover=True)
                if args.command=='install-source-permission':
                    from keystone.storage import prohibited
                    if prohibited(args.record) or prohibited(args.evidence):raise InputError()
                    record=read_json(read_confined(args.record.absolute().parent,args.record.name,65536))
                    evidence=read_confined(args.evidence.absolute().parent,args.evidence.name)
                    value=inputs.install_permission(record,evidence)
                    result={'permission_id':value['id'],'status':'local_operator_recorded','financial_approval':False}
                elif args.command=='revoke-source-permission':
                    inputs.revoke_permission(args.permission_id,args.reason)
                    result={'permission_id':args.permission_id,'status':'revoked','financial_approval':False}
                else:
                    from .job_store import JobStore
                    from keystone.storage import snapshot
                    lease=JobStore(inputs.root/'control',inputs.root/'reports')
                    try:
                        plan=inputs.backup_plan()
                        def check_source():
                            if inputs.backup_plan()!=plan:raise InputError('input_unavailable',503)
                            from .lifecycle import audit_evidence
                            if audit_evidence(inputs,lease)['state']!='verified':raise InputError('input_unavailable',503)
                        saved=snapshot(plan,args.destination,quiescent=True,verify_source=check_source)
                        result={'snapshot':str(saved),'protection':'local_snapshot_only','restore_command':'keystone.workspace restore-private'}
                    finally:lease.close()
            print(json.dumps(result))
        except Exception:
            print(json.dumps(InputError('input_unavailable',503).envelope()),file=sys.stderr)
            return 2
    elif args.command == 'prepare':
        from .prepare import prepare_workspace
        result = prepare_workspace(args.destination, native=args.native)
        print(json.dumps({'workspace': str(result), 'classification': 'synthetic', 'production_release_approved': False}))
    elif args.command == 'project':
        from .report_views.publish import project_workspace
        result = project_workspace(args.workspace, args.destination)
        print(json.dumps({'workspace': str(result), 'classification': 'synthetic', 'production_release_approved': False}))
    elif args.command=='recover-job':
        from .job_store import JobStore
        from .worker import recover_delivery
        from .job_contract import JobError
        store = None
        try:
            from .catalog import Catalog
            if Catalog(args.workspace).load().schema_version==3:
                root=args.workspace.absolute().parent
                if args.workspace.absolute()!=root/'reports' or args.jobs_dir.absolute()!=root/'control':
                    raise JobError('job_recovery_unavailable',409)
                # Preserve the existing reports/control spelling, with the same
                # stop-before-recovery guard as the root-based command.
                return main(['recover-private-job','--workspace',str(root),'--job-id',args.job_id])
            else:
                store = JobStore(args.jobs_dir, args.workspace, worker=True)
                result = recover_delivery(store, args.job_id)['job']
                print(json.dumps(dict(job_id=result['job_id'], status=result['status'],
                    result_run_id=result['execution']['result']['run_id'], financial_approval=False)))
        except Exception:
            print(json.dumps(JobError('job_recovery_unavailable',409).envelope()), file=sys.stderr)
            return 2
        finally:
            if store is not None:
                store.close()
    else:
        if not 1024 <= args.port <= 65535:
            parser.error('Port must be between 1024 and 65535.')
        if args.jobs_dir is not None and not args.enable_job_admission:
            parser.error('--jobs-dir requires --enable-job-admission.')
        if args.enable_worker and not args.enable_job_admission:
            parser.error('--enable-worker requires --enable-job-admission.')
        from .catalog import Catalog
        is_private=(args.workspace/'workspace.json').is_file()
        if args.enable_imports and not is_private:
            parser.error('--enable-imports requires a separately prepared private workspace.')
        if args.enable_review_notes and not is_private:
            parser.error('--enable-review-notes requires a separately prepared private workspace.')
        if args.enable_review_corrections and not is_private:
            parser.error('--enable-review-corrections requires a separately prepared private workspace.')
        if args.enable_review_decisions and not is_private:
            parser.error('--enable-review-decisions requires a separately prepared private workspace.')
        if is_private and args.jobs_dir is not None:
            parser.error('Private workspace job control has a fixed private location; omit --jobs-dir.')
        if not is_private and Catalog(args.workspace).load().schema_version==3:
            parser.error('Serve the private workspace root, not its reports subdirectory.')
        from .api import create_app
        from .job_contract import JobError
        import uvicorn
        admission = None
        try:
            if is_private:
                from .onboarding.service import PrivateAdmission
                admission=PrivateAdmission(args.workspace,f'http://127.0.0.1:{args.port}',
                    enable_imports=args.enable_imports,enable_jobs=args.enable_job_admission,enable_worker=args.enable_worker,
                    enable_review_notes=args.enable_review_notes,enable_review_corrections=args.enable_review_corrections,
                    enable_review_decisions=args.enable_review_decisions)
                print(json.dumps(dict(private_workspace=True,web_url=f'http://127.0.0.1:{args.port}/',imports_enabled=args.enable_imports,
                    job_admission_enabled=args.enable_job_admission,token_file=str(admission.token_file),
                    next_action='Open this local address, connect with the current private token, and inspect inputs before processing.')),flush=True)
            elif args.enable_job_admission:
                from keystone.maintenance import ROOT
                from .jobs import Admission
                admission = Admission(args.workspace, args.jobs_dir or ROOT / 'state/workspace-jobs',
                                      f'http://127.0.0.1:{args.port}', enable_worker=args.enable_worker)
                print(json.dumps(dict(job_admission_enabled=True, job_worker_enabled=False,
                    job_worker_requested=args.enable_worker,
                    token_file=str(admission.token_file),
                    next_action='Keep the token private. Inspect /api/execution for worker readiness.')), flush=True)
            uvicorn.run(create_app(args.workspace/'reports' if is_private else args.workspace, admission=admission,
                                  private=admission if is_private else None), host='127.0.0.1', port=args.port,
                        proxy_headers=False, access_log=False)
        except JobError as error:
            print(json.dumps(error.envelope()), file=sys.stderr)
            return 2
        except Exception:
            if not is_private:raise
            from .onboarding.contracts import InputError
            print(json.dumps(InputError('input_unavailable',503).envelope()),file=sys.stderr)
            return 2
        finally:
            if admission is not None:
                admission.close()


if __name__ == '__main__':
    raise SystemExit(main())
