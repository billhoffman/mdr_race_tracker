"""Export a consistent private race archive, including SQLite and readable JSON."""
import argparse
from contextlib import closing
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import zipfile

TABLES={'capture_versions':'source-and-config-versions.jsonl','gps_history':'sweeper-gps.jsonl',
        'poll_history':'source-reads.jsonl','entries':'observations.jsonl','revisions':'audit-revisions.jsonl',
        'director_commands':'director-commands.jsonl','director_runners':'director-added-roster.jsonl',
        'director_removed':'director-removed-bibs.jsonl','meta':'metadata.jsonl'}


def export_race(database,output):
    database=Path(database).resolve();output=Path(output).resolve()
    if not database.is_file():raise ValueError('Race database does not exist: '+str(database))
    if output.exists():raise ValueError('Output already exists; choose a new archive filename')
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as directory:
        backup=Path(directory)/'race.sqlite3'
        # SQLite backup makes a consistent copy even while cron is writing.
        with closing(sqlite3.connect(database.as_uri()+'?mode=ro',uri=True)) as source:
            with closing(sqlite3.connect(backup)) as destination:source.backup(destination)
        with closing(sqlite3.connect(backup)) as db:
            db.row_factory=sqlite3.Row
            available={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            meta=dict(db.execute('SELECT key,value FROM meta'))
            manifest={'format_version':1,'race_id':meta.get('race_id'),
                      'exported_at':datetime.now(timezone.utc).isoformat(),
                      'capture_started_at':meta.get('capture_started_at'),'counts':{},
                      'notes':['Private archive: contains raw radio/RD text and race-day GPS; keep outside the public website.',
                               'Event time and receipt time are distinct. Runner movement between checkpoints is not observed GPS.',
                               'Only successful polls can capture input data; intermediate edits between polls cannot be recovered.',
                               'GPS history starts when archive support is deployed; an older saved latest fix may be recovered.',
                               'Garmin messages/device identifiers and unrelated-day GPS are not imported.']}
            fd,name=tempfile.mkstemp(prefix='.race-export-',suffix='.zip',dir=output.parent);os.close(fd)
            try:
                with zipfile.ZipFile(name,'w',compression=zipfile.ZIP_DEFLATED) as bundle:
                    bundle.write(backup,'race.sqlite3')
                    for table,filename in TABLES.items():
                        records=[]
                        if table in available:
                            for row in db.execute('SELECT * FROM '+table+' ORDER BY rowid'):
                                item=dict(row)
                                for key in ('payload','value'):
                                    if key in item:
                                        try:item[key]=json.loads(item[key])
                                        except (json.JSONDecodeError,TypeError):pass
                                records.append(item)
                        manifest['counts'][table]=len(records)
                        bundle.writestr(filename,''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in records))
                    bundle.writestr('manifest.json',json.dumps(manifest,indent=2)+'\n')
                # Publish the completed ZIP without overwriting another export.
                os.link(name,output)
            finally:os.unlink(name)
    return manifest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    try:manifest=export_race(args.database,args.output)
    except (ValueError,OSError,sqlite3.Error) as exc:raise SystemExit(str(exc))
    print('Saved private race archive:',args.output)
    print('Counts:',json.dumps(manifest['counts'],sort_keys=True))
    print('Includes a consistent SQLite backup; keep the ZIP outside the website directory.')


if __name__=='__main__':main()
