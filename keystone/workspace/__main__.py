"""Prepare synthetic saved evidence or serve it locally; never runs work over HTTP."""
import argparse
import json
from pathlib import Path


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
    args = parser.parse_args(argv)
    if args.command == 'prepare':
        from .prepare import prepare_workspace
        result = prepare_workspace(args.destination, native=args.native)
        print(json.dumps({'workspace': str(result), 'classification': 'synthetic', 'production_release_approved': False}))
    elif args.command == 'project':
        from .report_views.publish import project_workspace
        result = project_workspace(args.workspace, args.destination)
        print(json.dumps({'workspace': str(result), 'classification': 'synthetic', 'production_release_approved': False}))
    else:
        if not 1024 <= args.port <= 65535:
            parser.error('Port must be between 1024 and 65535.')
        from .catalog import Catalog
        Catalog(args.workspace).load()
        from .api import create_app
        import uvicorn
        uvicorn.run(create_app(args.workspace), host='127.0.0.1', port=args.port,
                    proxy_headers=False, access_log=False)


if __name__ == '__main__':
    main()
