"""One-shot static publisher for shared hosting: python3 -m tracker.publish --help"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

from .core import Store, load_config
from .pipeline import poll_once
from .server import public_snapshot

ROOT = Path(__file__).resolve().parents[1]
WEB = Path(__file__).resolve().parent/'web'


def atomic_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.mdr-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as stream:
            stream.write(data if isinstance(data,bytes) else data.encode('utf-8'))
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary,0o644)
        os.replace(temporary,path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def publisher_lock(database):
    path = Path(str(database)+'.publish.lock')
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a') as lock:
        try:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('Another publisher is already running for this database; skipping this run.')
        try:
            yield
        finally:
            fcntl.flock(lock,fcntl.LOCK_UN)


def check_destination(web_root, database, config, token_path=None):
    web_root, database = Path(web_root).resolve(), Path(database).resolve()
    for private in [database,token_path]:
        if private and Path(private).resolve().is_relative_to(web_root):
            raise ValueError('Keep the SQLite database and Google token outside the public web directory.')
    # Never publish alongside the Git checkout (which can hold local credentials/config).
    if ROOT.is_relative_to(web_root) or web_root==ROOT:
        raise ValueError('Use a dedicated output directory, not the repository or its parent.')
    marker = web_root/'.mdr-tracker.json'
    if marker.exists():
        if json.loads(marker.read_text()).get('race_id')!=config['race_id']:
            raise ValueError('This output directory belongs to another race. Choose a separate directory.')
    elif web_root.exists() and any(web_root.iterdir()):
        raise ValueError('Output directory is not empty and is not owned by the tracker. Use a new /tracker/ directory.')
    return web_root


def write_site(web_root, course, snapshot):
    """Publish only allowlisted static assets and a sanitized spectator snapshot."""
    web_root = Path(web_root)
    web_root.mkdir(parents=True,exist_ok=True)
    atomic_write(web_root/'.mdr-tracker.json',json.dumps({'race_id':snapshot['race']['id']}))
    course_data = json.dumps(course,separators=(',',':')).encode()
    course_name = 'course-'+hashlib.sha256(course_data).hexdigest()[:16]+'.json'
    app_data, css_data = (WEB/'app.js').read_bytes(), (WEB/'style.css').read_bytes()
    geometry_data = (WEB/'course-geometry.js').read_bytes()
    geometry_name = 'course-geometry-'+hashlib.sha256(geometry_data).hexdigest()[:16]+'.js'
    app_name = 'app-'+hashlib.sha256(app_data).hexdigest()[:16]+'.js'
    css_name = 'style-'+hashlib.sha256(css_data).hexdigest()[:16]+'.css'
    atomic_write(web_root/course_name,course_data)
    atomic_write(web_root/app_name,app_data)
    atomic_write(web_root/css_name,css_data)
    atomic_write(web_root/geometry_name,geometry_data)
    state = public_snapshot(snapshot)
    state.update(published_at=datetime.now(timezone.utc).isoformat(),course_url='./'+course_name)
    # state.json is replaced atomically. Its course URL is immutable, so readers
    # cannot combine a new race state with a partially updated course file.
    atomic_write(web_root/'state.json',json.dumps(state,separators=(',',':')))
    html = (WEB/'index.html').read_text()
    html = html.replace('href="/style.css"',f'href="./{css_name}"')
    html = html.replace('src="/course-geometry.js"',f'src="./{geometry_name}"')
    html = html.replace('<body>','<body data-public="true">')
    settings = '<script>window.TRACKER_SETTINGS={stateUrl:"./state.json",static:true};</script>'
    html = html.replace('<script src="/app.js"></script>',settings+f'<script src="./{app_name}"></script>')
    # No audit endpoint exists in this mode. Remove its link from the HTML too.
    html = html.replace('<a href="/api/audit" target="_blank" rel="noopener">Open full audit log ↗</a>','')
    atomic_write(web_root/'index.html',html)
    atomic_write(web_root/'.htaccess','''# Tracker-generated Apache configuration.
Options -Indexes
<IfModule mod_headers.c>
  <FilesMatch "^(state\\.json|index\\.html)$">
    Header set Cache-Control "no-store, max-age=0"
  </FilesMatch>
</IfModule>
''')


def publish(config, database, web_root, source='file', log=None, doc_id=None, token_path=None, expected_interval=60):
    web_root = check_destination(web_root,database,config,token_path)
    with publisher_lock(database):
        store = Store(database,config)
        try:
            success = poll_once(store,source,log,doc_id,token_path,expected_interval)
            snapshot = store.snapshot()
            write_site(web_root,config['course'],snapshot)
            return success, snapshot
        finally:
            store.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,default=ROOT/'races/moreau-test/race.json')
    parser.add_argument('--roster',type=Path)
    parser.add_argument('--source',choices=['file','google'],default='file')
    parser.add_argument('--log',type=Path,default=ROOT/'races/moreau-test/live-log.txt')
    parser.add_argument('--google-doc',default=os.environ.get('TRACKER_GOOGLE_DOC',''))
    parser.add_argument('--google-token',type=Path)
    parser.add_argument('--database',type=Path,required=True)
    parser.add_argument('--web-root',type=Path,required=True)
    parser.add_argument('--expected-interval',type=int,default=60,help='Seconds between cron runs, used for freshness warnings')
    parser.add_argument('--clock',choices=['latest_report','live'])
    args = parser.parse_args()
    match = re.search(r'/document/d/([\w-]+)',args.google_doc)
    doc_id = match[1] if match else args.google_doc
    if args.source=='google' and not re.fullmatch(r'[\w-]+',doc_id):
        parser.error('Supply --google-doc ID_OR_URL or TRACKER_GOOGLE_DOC')
    if args.expected_interval<1:
        parser.error('Expected interval must be positive')
    try:
        config = load_config(args.config,args.roster)
        if args.clock:
            config['clock_mode']=args.clock
        success,state = publish(config,args.database,args.web_root,args.source,args.log,doc_id,args.google_token,args.expected_interval)
    except (ValueError,OSError,json.JSONDecodeError) as exc:
        raise SystemExit(str(exc))
    print(f'Published {config["name"]} to {args.web_root}; {state["revision"]} saved revisions.')
    if state['issues'] or state['anomalies']:
        print(f"Private review: {len(state['issues'])} input reports, {len(state['anomalies'])} runner progression conflicts.")
        print('Inspect input reports with: python3 -m tracker.review --database '+str(args.database))
    if not success:
        raise SystemExit('Input read failed. Published last confirmed observations with a source-error notice.')


if __name__=='__main__':
    main()
