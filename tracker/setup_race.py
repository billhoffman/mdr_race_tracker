"""Guided race configuration: python3 -m tracker.setup_race"""
import argparse
from datetime import datetime
import json
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]


def race_start(day, clock, timezone='America/New_York'):
    date=datetime.strptime(day.strip(),'%Y-%m-%d').date()
    clock=clock.strip().upper()
    for pattern in ['%I:%M %p','%I %p','%I:%M%p','%I%p','%H:%M']:
        try:
            time=datetime.strptime(clock,pattern).time()
            return datetime.combine(date,time,ZoneInfo(timezone))
        except ValueError:
            continue
    raise ValueError('Enter a time like 8:00 AM or 08:00.')


def create_config(directory, start):
    course=json.loads((directory/'course.json').read_text())
    return {'race_id':course.get('race_id',directory.name),
        'name':course.get('name','Race')+' '+str(start.year),
        'test_mode':False,'date':start.date().isoformat(),
        'timezone':start.tzinfo.key,'start_time':start.isoformat(),
        'clock_mode':'live','course_file':'course.json','roster_file':'roster.json'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--race-dir',type=Path,default=ROOT/'races/moreau-2026')
    parser.add_argument('--timezone',default='America/New_York')
    args=parser.parse_args()
    directory=args.race_dir.resolve()
    if not (directory/'course.json').exists():
        raise SystemExit(f'No course.json in {directory}')
    target=directory/'race.local.json'
    existing=json.loads(target.read_text()) if target.exists() else {}
    default_day=existing.get('date','2026-10-31')
    print('Race setup — local time in '+args.timezone)
    print('Enter the confirmed race start. The old 09:00 test start is not used.')
    while True:
        day=input(f'Race date [{default_day}]: ').strip() or default_day
        clock=input('Start time (for example, 8:00 AM): ').strip()
        try:
            start=race_start(day,clock,args.timezone)
            break
        except ValueError as exc:
            print('Invalid date or time:',exc)
    config=create_config(directory,start)
    print(f'\n{config["name"]}: {start.strftime("%B %d, %Y at %I:%M %p %Z")}')
    if input('Save this race setup? [y/N]: ').strip().lower() not in {'y','yes'}:
        print('No changes saved.')
        return
    if target.exists():
        backup=target.with_suffix('.json.bak')
        backup.write_text(target.read_text())
        print('Previous setup saved to',backup)
    target.write_text(json.dumps(config,indent=2)+'\n')
    print('Saved',target)
    print('Next: import the UltraSignup roster when it is available. This command does not switch the live website or cron settings.')


if __name__=='__main__':
    try:
        main()
    except (KeyboardInterrupt,EOFError):
        raise SystemExit('\nSetup cancelled; no changes saved.')
