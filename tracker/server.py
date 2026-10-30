"""Run locally: python3 -m tracker.server --source file"""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import threading
import urllib.parse

from .core import Store, load_config
from .pipeline import poll_once

ROOT = Path(__file__).resolve().parents[1]
WEB = Path(__file__).resolve().parent/'web'


def public_snapshot(snapshot):
    """Public viewers get confirmed progress, not operator log/review content."""
    snapshot = {**snapshot,'public_view':True,'history':[],'issues':[],'anomalies':[]}
    snapshot['source'] = dict(snapshot['source'])
    if snapshot['source'].get('error'):
        snapshot['source']['error'] = 'Source update failed. Showing last confirmed observations.'
    if snapshot['source'].get('director'):
        snapshot['source']['director']=dict(snapshot['source']['director'])
        if snapshot['source']['director'].get('error'):
            snapshot['source']['director']['error']='Director log update failed. Last confirmed director commands retained.'
    return snapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,default=ROOT/'races/moreau-test/race.json')
    parser.add_argument('--source',choices=['file','google'],default='file')
    parser.add_argument('--log',type=Path,default=ROOT/'races/moreau-test/live-log.txt')
    parser.add_argument('--google-doc',default=os.environ.get('TRACKER_GOOGLE_DOC',''),help='Google Doc ID or URL (or TRACKER_GOOGLE_DOC environment variable)')
    parser.add_argument('--google-token',type=Path)
    parser.add_argument('--director-doc',default=os.environ.get('TRACKER_DIRECTOR_DOC',''),help='Separate race director Google Doc ID/URL')
    parser.add_argument('--director-log',type=Path,help='Local director command file for offline testing')
    parser.add_argument('--sweeper-url',default=os.environ.get('TRACKER_SWEEPER_URL',''))
    parser.add_argument('--sweeper-kml',type=Path,help='Offline KML file for sweep tracking tests')
    parser.add_argument('--database',type=Path)
    parser.add_argument('--roster',type=Path,help='Imported roster JSON, overriding the config roster')
    parser.add_argument('--clock',choices=['latest_report','live'],help='Test report clock or continuously running race clock')
    parser.add_argument('--port',type=int,default=8000)
    parser.add_argument('--host',default='127.0.0.1',help='Bind address; default loopback, or 0.0.0.0 in a container')
    parser.add_argument('--public',action='store_true',help='Spectator view: hide raw audit log and operator review details')
    parser.add_argument('--interval',type=float,default=15)
    args = parser.parse_args()
    if args.interval < 2:
        parser.error('Polling interval must be at least two seconds')
    match = re.search(r'/document/d/([\w-]+)',args.google_doc)
    doc_id = match[1] if match else args.google_doc
    if args.source=='google' and not re.fullmatch(r'[\w-]+',doc_id):
        parser.error('Supply --google-doc ID_OR_URL or set TRACKER_GOOGLE_DOC')
    director_match=re.search(r'/document/d/([\w-]+)',args.director_doc)
    director_id=(director_match[1] if director_match else args.director_doc) if not args.director_log else None
    if director_id and not re.fullmatch(r'[\w-]+',director_id):
        parser.error('Supply --director-doc ID_OR_URL')
    config = load_config(args.config,args.roster)
    if args.clock:
        config['clock_mode'] = args.clock
    store = Store(args.database or ROOT/f'outputs/tracker/{config["race_id"]}.sqlite3',config)
    stop = threading.Event()

    def poll():
        while not stop.is_set():
            poll_once(store,args.source,args.log,doc_id,args.google_token,args.interval,director_id,args.director_log,args.sweeper_url,args.sweeper_kml)
            stop.wait(args.interval)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            path = urllib.parse.urlsplit(self.path).path
            if path=='/api/state':
                state=store.snapshot()
                return self.send_json(public_snapshot(state) if args.public else state)
            if path=='/api/course':
                return self.send_json(config['course'])
            if path=='/api/audit':
                if args.public:
                    return self.send_error(404)
                return self.send_json(store.audit())
            if path=='/healthz':
                # Process readiness only; /api/state reports input freshness separately.
                return self.send_json({'status':'ok','race_id':config['race_id']})
            filename = {'/':'index.html','/app.js':'app.js','/course-geometry.js':'course-geometry.js','/progress.js':'progress.js','/style.css':'style.css'}.get(path)
            if not filename:
                return self.send_error(404)
            data = (WEB/filename).read_bytes()
            self.send_response(200)
            self.send_header('Content-Type',{'html':'text/html; charset=utf-8','js':'text/javascript; charset=utf-8','css':'text/css; charset=utf-8'}[filename.rsplit('.',1)[-1]])
            self.send_header('Cache-Control','no-store')
            self.send_header('Content-Length',str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def send_json(self,data):
            encoded = json.dumps(data).encode()
            self.send_response(200)
            self.send_header('Content-Type','application/json; charset=utf-8')
            self.send_header('Cache-Control','no-store')
            self.send_header('Content-Length',str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self,format,*values):
            pass

    try:
        server = ThreadingHTTPServer((args.host,args.port),Handler)
    except PermissionError:
        store.close()
        raise SystemExit('This environment cannot open a local listening port. Run this command in your Mac Terminal.')
    except OSError as exc:
        store.close()
        raise SystemExit(f'Could not start the server on port {args.port}: {exc}. Try --port 8001.')
    worker = threading.Thread(target=poll,daemon=True)
    worker.start()
    print(f'Tracker listening: http://{args.host}:{args.port}',flush=True)
    print(f'{config["name"]} | {args.source} input | refresh every {args.interval:g} seconds',flush=True)
    print('Ctrl+C stops the server. Confirmed observations remain in the database.',flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        server.server_close()
        worker.join(timeout=15)
        if not worker.is_alive():
            store.close()


if __name__=='__main__':
    main()
