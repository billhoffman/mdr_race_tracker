"""Add a late entrant: python3 -m tracker.add_runner"""
import argparse
from .roster import DEFAULT_ROSTER, update_roster


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--roster',default=DEFAULT_ROSTER)
    parser.add_argument('--bib')
    parser.add_argument('--name')
    args=parser.parse_args()
    bib=args.bib if args.bib is not None else input('Assigned bib number: ')
    name=args.name if args.name is not None else input('Runner full name: ')
    try:
        result=update_roster(args.roster,[{'bib':bib,'name':name}],require_existing=True)
    except (ValueError,OSError) as exc:raise SystemExit(str(exc))
    print(f'{result["added"]} added; {result["total"]} runners in {result["path"]}.')
    print('The next DreamHost publish loads the roster and rechecks pending radio reports. Local continuous servers need a restart.')
    print('Give the same bib/name to net control and the timing/check-in team.')


if __name__=='__main__':
    try:main()
    except (KeyboardInterrupt,EOFError):raise SystemExit('\nCancelled; roster unchanged.')
