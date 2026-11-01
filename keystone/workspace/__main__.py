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
    project = commands.add_parser('project', help='Project registered synthetic evidence into a new native workspace')
    project.add_argument('--workspace', type=Path, required=True)
    project.add_argument('--destination', type=Path, required=True)
    serve = commands.add_parser('serve', help='Serve the explicit workspace on loopback only')
    serve.add_argument('--workspace', type=Path, default=Path('output/workspace-demo'))
    serve.add_argument('--port', type=int, default=8765)
    serve.add_argument('--enable-job-admission', action='store_true',
                       help='Accept protected offline saved-evidence jobs')
    serve.add_argument('--enable-worker', action='store_true', help='Start the supervised offline background worker')
    serve.add_argument('--jobs-dir', type=Path,
                       help='Private control directory outside the report workspace (default state/workspace-jobs)')
    recover = commands.add_parser('recover-job', help='Recover verified saved delivery without executing the job again')
    recover.add_argument('--workspace', type=Path, required=True)
    recover.add_argument('--jobs-dir', type=Path, required=True)
    recover.add_argument('--job-id', required=True)
    args = parser.parse_args(argv)
    if args.command == 'prepare':
        from .prepare import prepare_workspace
        result = prepare_workspace(args.destination, native=args.native)
        print(json.dumps({'workspace': str(result), 'classification': 'synthetic', 'production_release_approved': False}))
    elif args.command == 'project':
        from .report_views.publish import project_workspace
        result = project_workspace(args.workspace, args.destination)
        print(json.dumps({'workspace': str(result), 'classification': 'synthetic', 'production_release_approved': False}))
    elif args.command == 'recover-job':
        from .job_store import JobStore
        from .worker import recover_delivery
        from .job_contract import JobError
        store = None
        try:
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
        Catalog(args.workspace).load()
        from .api import create_app
        from .job_contract import JobError
        import uvicorn
        admission = None
        try:
            if args.enable_job_admission:
                from keystone.maintenance import ROOT
                from .jobs import Admission
                admission = Admission(args.workspace, args.jobs_dir or ROOT / 'state/workspace-jobs',
                                      f'http://127.0.0.1:{args.port}', enable_worker=args.enable_worker)
                print(json.dumps(dict(job_admission_enabled=True, job_worker_enabled=False,
                    job_worker_requested=args.enable_worker,
                    token_file=str(admission.token_file),
                    next_action='Keep the token private. Inspect /api/execution for worker readiness.')), flush=True)
            uvicorn.run(create_app(args.workspace, admission=admission), host='127.0.0.1', port=args.port,
                        proxy_headers=False, access_log=False)
        except JobError as error:
            print(json.dumps(error.envelope()), file=sys.stderr)
            return 2
        finally:
            if admission is not None:
                admission.close()


if __name__ == '__main__':
    raise SystemExit(main())
