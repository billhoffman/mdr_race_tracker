"""Show private radio-log issues on the race director's machine or hosting shell."""
import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3


def review(database):
    database=Path(database).resolve()
    if not database.is_file():raise ValueError('Database does not exist; use the same private database as the publisher.')
    # Read-only connection; reviewing never creates or changes the race database.
    with closing(sqlite3.connect(database.as_uri()+'?mode=ro',uri=True)) as db:
        meta=dict(db.execute('SELECT key,value FROM meta'))
        issues=json.loads(meta.get('input_issues','[]'))
        health=json.loads(meta.get('source_health','{}'))
        issues.extend({'line':None,'text':'Bib '+a['bib']+', '+a['id'],'message':a['message'],'source':'progression'} for a in json.loads(meta.get('review_anomalies','[]')))
    return issues,health


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',type=Path,required=True)
    args=parser.parse_args()
    try:issues,health=review(args.database)
    except (ValueError,sqlite3.Error) as exc:raise SystemExit(str(exc))
    if health.get('error'):print('SOURCE ERROR: '+health['error'])
    if health.get('director',{}).get('error'):print('DIRECTOR SOURCE ERROR: '+health['director']['error'])
    print(f'{len(issues)} input/progression reports need review.')
    for issue in issues:
        label=(issue.get('source','input')+' / ')+(issue.get('id') or ('line '+str(issue.get('line'))))
        print(f'\n{label}: {issue["message"]}\n  {issue["text"]}')



if __name__=='__main__':main()
