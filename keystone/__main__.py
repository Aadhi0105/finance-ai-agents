"""Local inventory validation, consistent snapshots and new-directory restore."""
import argparse
import json
import sys
from pathlib import Path
from keystone.contracts import validate_plan, release_holds
from keystone.storage import snapshot, verify, restore


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='action',required=True)
    sub.add_parser('doctor')
    p=sub.add_parser('inspect-operation');p.add_argument('operation_id')
    p=sub.add_parser('validate-plan');p.add_argument('plan')
    p=sub.add_parser('snapshot');p.add_argument('plan');p.add_argument('--destination',required=True)
    p.add_argument('--quiescent',action='store_true',help='confirm direct API/other-checkout writers are stopped')
    p=sub.add_parser('verify');p.add_argument('snapshot')
    p=sub.add_parser('restore');p.add_argument('snapshot');p.add_argument('--destination',required=True)
    args=parser.parse_args(argv)
    try:
        if args.action=='doctor':
            from keystone.environment import inspect_environment
            result=inspect_environment();print(json.dumps(result,indent=2))
            return 0 if result['status']=='ready_for_local_checks' else 3
        elif args.action=='inspect-operation':
            from keystone.environment import inspect_operation
            print(json.dumps(inspect_operation(args.operation_id),indent=2))
        elif args.action in {'validate-plan','snapshot'}:
            plan=validate_plan(json.loads(Path(args.plan).read_text()))
            if args.action=='validate-plan':
                print(json.dumps({'valid_inventory':True,'release_approved':False,'permission_holds':release_holds(plan)}))
            else:
                result=snapshot(plan,args.destination,quiescent=args.quiescent)
                print(json.dumps({'snapshot':str(result),'verified':True,'protection':'local_snapshot_only','release_approved':False}))
        elif args.action=='verify':
            m=verify(args.snapshot)
            print(json.dumps({'snapshot_id':m['snapshot_id'],'verified':True,'permission_holds':m['permission_holds'],'protection':'local_snapshot_only'}))
        else:
            print(json.dumps({'restored':str(restore(args.snapshot,args.destination)),'protection':'local_restore_test_only'}))
        return 0
    except (Exception,KeyboardInterrupt) as exc:
        # Do not echo raw paths, provider payloads or exception bodies in CLI logs.
        print(json.dumps({'status':'failed','error_type':type(exc).__name__,
                          'action':args.action,'message':'No successful protection claimed. Check inventory, quiescence, integrity and destination; preserve existing snapshots.'}),file=sys.stderr)
        return 2


if __name__=='__main__':
    raise SystemExit(main())
