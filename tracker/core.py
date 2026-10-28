"""Validated observations and an auditable, persistent race state."""
from datetime import datetime
import json
import math
from pathlib import Path
import re
import sqlite3
import threading
from zoneinfo import ZoneInfo
from .radio import input_rows, identify_rows, parse_report


def load_config(path, roster_path=None):
    path = Path(path).resolve()
    config = json.loads(path.read_text())
    course_path=(path.parent/config['course_file']).resolve()
    config['course'] = json.loads(course_path.read_text())
    elevation_patch=course_path.with_name(course_path.stem+'.elevation.local.json')
    if elevation_patch.exists():
        patch=json.loads(elevation_patch.read_text())['elevation_backfill']
        for item in patch['points']:
            index=item['point_index']
            points=config['course']['route']['coordinates']
            if not isinstance(index,int) or index<0 or index>=len(points):
                raise ValueError('Elevation patch no longer matches the course; regenerate it.')
            point=points[index]
            original=point[2] if len(point)>2 else None
            if point[:2]!=[item['longitude'],item['latitude']] or original!=item['original_m']:
                raise ValueError('Elevation patch no longer matches the course; regenerate it.')
            if not isinstance(item['elevation_m'],(int,float)) or not math.isfinite(item['elevation_m']):
                raise ValueError('Elevation patch contains an invalid height.')
            if len(point)<3:point.append(item['elevation_m'])
            else:point[2]=item['elevation_m']
        config['course']['route']['elevation_backfill']=patch
    config['checkpoints'] = {c['id']: c for c in config['course']['checkpoints']}
    if roster_path or config.get('roster_file'):
        roster_path = Path(roster_path).resolve() if roster_path else (path.parent/config['roster_file']).resolve()
        config['roster'] = json.loads(roster_path.read_text())
    config['runners'] = {}
    for runner in config['roster']:
        bib = str(runner.get('bib','')).strip()
        if not bib or not runner.get('name') or bib in config['runners']:
            raise ValueError('Roster must have a unique nonempty bib and a name for each runner')
        config['runners'][bib] = {**runner,'bib':bib}
    config['start'] = datetime.fromisoformat(config['start_time'])
    if config['start'].tzinfo is None:
        raise ValueError('Race start time must include a timezone offset')
    return config


def parse_line(line, config):
    parts = [p.strip() for p in line.split('|')]
    event_id = parts[0]
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,47}', event_id):
        raise ValueError('Use an entry ID such as T001 before the first |')
    if len(parts)==2 and parts[1].upper()=='VOID':
        return {'id':event_id,'void':True}
    if len(parts)!=5:
        raise ValueError('Expected ID | HH:MM[:SS] | CHECKPOINT | BIB[,BIB] | PASS/FINISH/WITHDRAWN')
    _, clock, station, bib_text, kind = parts
    if not re.fullmatch(r'\d{2}:\d{2}(?::\d{2})?',clock):
        raise ValueError('Time must be HH:MM or HH:MM:SS')
    try:
        moment = datetime.fromisoformat(config['date']+'T'+clock).replace(tzinfo=ZoneInfo(config['timezone']))
    except ValueError as exc:
        raise ValueError('Invalid clock time') from exc
    if moment < config['start']:
        raise ValueError('Passage time is before the configured race start')
    station, kind = station.upper(), kind.upper()
    if station not in config['checkpoints'] and station not in {'START','FINISH'}:
        raise ValueError(f'Unknown checkpoint {station}')
    if kind not in {'PASS','FINISH','WITHDRAWN'}:
        raise ValueError('Action must be PASS, FINISH or WITHDRAWN')
    if (kind=='FINISH') != (station=='FINISH'):
        raise ValueError('FINISH checkpoint and FINISH action must be used together')
    bibs = list(dict.fromkeys(p.strip() for p in bib_text.split(',')))
    unknown = [bib for bib in bibs if bib not in config['runners']]
    if unknown:
        raise ValueError('Unknown bib(s): '+', '.join(unknown))
    return {'id':event_id,'time':moment.isoformat(),'station':station,'kind':kind,'bibs':bibs,'void':False}


class Store:
    def __init__(self, path, config):
        Path(path).parent.mkdir(parents=True,exist_ok=True)
        self.config = config
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path,check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS entries(source TEXT,id TEXT,payload TEXT,raw TEXT,received TEXT,
                active INTEGER, PRIMARY KEY(source,id));
            CREATE TABLE IF NOT EXISTS revisions(sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT,id TEXT,payload TEXT,raw TEXT,received TEXT);
            CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT);
        ''')
        race = self.db.execute("SELECT value FROM meta WHERE key='race_id'").fetchone()
        if race and race[0]!=config['race_id']:
            raise ValueError('Database belongs to a different race; choose another database path')
        self.db.execute("INSERT OR IGNORE INTO meta VALUES('race_id',?)",(config['race_id'],))
        self.db.commit()
        saved_issues=self.db.execute("SELECT value FROM meta WHERE key='input_issues'").fetchone()
        self.issues = json.loads(saved_issues[0]) if saved_issues else []
        self.health = {'last_attempt':None,'last_success':None,'error':None,'mode':None}
        health = self.db.execute("SELECT value FROM meta WHERE key='source_health'").fetchone()
        if health:
            self.health.update(json.loads(health[0]))

    def close(self):
        self.db.close()

    def set_health(self, **values):
        with self.lock, self.db:
            self.health.update(values)
            self.db.execute("INSERT OR REPLACE INTO meta VALUES('source_health',?)",(json.dumps(self.health),))

    def ingest(self, text, source='primary-log'):
        rows=input_rows(text)
        if rows is not None:
            return self.ingest_radio(rows,source)
        parsed, issues, seen = [], [], set()
        for line_number, raw in enumerate(text.splitlines(),1):
            raw = raw.strip().lstrip('\ufeff')
            if not raw or raw.startswith('#'):
                continue
            try:
                event = parse_line(raw,self.config)
                if event['id'] in seen:
                    raise ValueError('Duplicate entry ID in this document; use a unique ID per report')
                seen.add(event['id'])
                parsed.append((event,raw))
            except ValueError as exc:
                issues.append({'line':line_number,'text':raw,'message':str(exc)})
        # Never apply either occurrence of a duplicated ID.
        duplicate_ids = {i['text'].split('|')[0].strip() for i in issues if i['message'].startswith('Duplicate entry ID')}
        received = datetime.now().astimezone().isoformat()
        with self.lock, self.db:
            for event, raw in parsed:
                if event['id'] in duplicate_ids:
                    continue
                old = self.db.execute('SELECT payload FROM entries WHERE source=? AND id=?',(source,event['id'])).fetchone()
                if event['void'] and not old:
                    issues.append({'line':None,'text':raw,'message':'Cannot void an unknown entry'})
                    continue
                payload = json.dumps(event,sort_keys=True)
                if old and old[0]==payload:
                    continue
                self.db.execute('INSERT OR REPLACE INTO entries VALUES(?,?,?,?,?,?)',
                    (source,event['id'],payload,raw,received,int(not event['void'])))
                self.db.execute('INSERT INTO revisions(source,id,payload,raw,received) VALUES(?,?,?,?,?)',
                    (source,event['id'],payload,raw,received))
            self.issues = issues
            self.db.execute("INSERT OR REPLACE INTO meta VALUES('input_issues',?)",(json.dumps(issues),))
        return issues

    def ingest_radio(self, rows, source):
        """Apply each table row atomically, including edited multi-runner reports."""
        key='radio_rows:'+source
        with self.lock, self.db:
            saved=self.db.execute('SELECT value FROM meta WHERE key=?',(key,)).fetchone()
            saved=json.loads(saved[0]) if saved else {'rows':[],'next_id':1,'retired':[]}
            mapped,next_id,retired=identify_rows(saved['rows'],rows,saved['next_id'],saved.get('retired',[]))
            issues=[]
            received=datetime.now().astimezone().isoformat()
            for line,row in enumerate(mapped,1):
                raw=row['time']+' | '+row['message']
                # IDs are internal and stable. All observations from a valid row
                # supersede its previous group together; malformed edits keep it.
                old=self.db.execute('SELECT id,payload FROM entries WHERE source=? AND id GLOB ?',
                                    (source,row['id']+'_*')).fetchall()
                try:
                    events=parse_report(row,self.config,parse_line)
                    if not events and any(not json.loads(r['payload']).get('void') for r in old):
                        raise ValueError('An accepted runner report was replaced with non-runner text; last confirmed data retained')
                except ValueError as exc:
                    issues.append({'line':line,'id':row['id'],'text':raw,'message':str(exc)})
                    continue
                if any(e.get('clock_warning') for e in events):
                    issues.append({'line':line,'id':row['id'],'text':raw,
                        'message':'Accepted explicit passage time up to two minutes ahead of report clock; verify operator clocks.'})
                ids={e['id'] for e in events}
                events.extend({'id':r['id'],'void':True} for r in old
                              if r['id'] not in ids and not json.loads(r['payload']).get('void'))
                for event in events:
                    payload=json.dumps(event,sort_keys=True)
                    previous=next((r['payload'] for r in old if r['id']==event['id']),None)
                    if previous==payload:continue
                    self.db.execute('INSERT OR REPLACE INTO entries VALUES(?,?,?,?,?,?)',
                                    (source,event['id'],payload,raw,received,int(not event['void'])))
                    self.db.execute('INSERT INTO revisions(source,id,payload,raw,received) VALUES(?,?,?,?,?)',
                                    (source,event['id'],payload,raw,received))
            for row in retired:
                active=self.db.execute('SELECT 1 FROM entries WHERE source=? AND id GLOB ? AND active=1',
                                       (source,row['id']+'_*')).fetchone()
                if active:issues.append({'line':None,'id':row['id'],'text':row['time']+' | '+row['message'],
                    'message':'Previously accepted row is missing. Last confirmed observations retained; restore and edit the original row to correct it.'})
            self.db.execute('INSERT OR REPLACE INTO meta VALUES(?,?)',
                            (key,json.dumps({'rows':mapped,'next_id':next_id,'retired':retired})))
            self.issues=issues
            self.db.execute("INSERT OR REPLACE INTO meta VALUES('input_issues',?)",(json.dumps(issues),))
        return issues

    def snapshot(self):
        with self.lock:
            rows = self.db.execute('SELECT * FROM entries WHERE active=1 ORDER BY source,id').fetchall()
            revision = self.db.execute('SELECT COUNT(*) FROM revisions').fetchone()[0]
            history = [dict(r) for r in self.db.execute('SELECT sequence,id,raw,received FROM revisions ORDER BY sequence DESC LIMIT 12')]
            issues, health = list(self.issues), dict(self.health)
        observations = []
        for row in rows:
            event = json.loads(row['payload'])
            event.update(received=row['received'],source=row['source'])
            observations.append(event)
        observations.sort(key=lambda e:(e['time'],e['id']))
        start = self.config['start']
        clock = max([start]+[datetime.fromisoformat(e['time']) for e in observations]) if self.config.get('clock_mode')=='latest_report' else datetime.now(start.tzinfo)
        checkpoint_distance = {key:value['distance_m'] for key,value in self.config['checkpoints'].items()}
        checkpoint_distance.update(START=0,FINISH=self.config['course']['route']['length_m'])
        runners, anomalies = [], []
        for bib, runner in self.config['runners'].items():
            events = [e for e in observations if bib in e['bibs']]
            accepted, terminal, previous = [], None, -1
            for event in events:
                distance = checkpoint_distance.get(event['station'],previous)
                if terminal:
                    anomalies.append({'bib':bib,'id':event['id'],'message':'Report after finish/withdrawal; correct or void the conflicting entry'})
                    continue
                if distance < previous:
                    anomalies.append({'bib':bib,'id':event['id'],'message':'Checkpoint is behind a prior confirmed passage; review entry'})
                    continue
                accepted.append(event)
                previous = distance
                if event['kind'] in {'FINISH','WITHDRAWN'}:
                    terminal = event['kind']
            last = accepted[-1] if accepted else None
            position = next((e for e in reversed(accepted) if e['station'] is not None),None)
            status = 'finished' if terminal=='FINISH' else 'withdrawn' if terminal else 'on_course' if last else 'not_reported'
            runners.append({**runner,'bib':bib,'status':status,'last':last,
                'position':position,
                'distance_m':checkpoint_distance[position['station']] if position else None,
                'elapsed_seconds':(datetime.fromisoformat(last['time'])-start).total_seconds() if status=='finished' else None,
                'reports':[{'id':e['id'],'station':e['station'],'time':e['time'],'kind':e['kind']} for e in accepted]})
        finishers = sorted([r for r in runners if r['status']=='finished'],key=lambda r:(r['elapsed_seconds'],r['bib']))
        for runner in runners:
            runner['place'] = next((i+1 for i,r in enumerate(finishers) if r['bib']==runner['bib']),None)
        return {'race':{'id':self.config['race_id'],'name':self.config['name'],'test_mode':self.config.get('test_mode',True),
                'start_time':start.isoformat(),'clock_mode':self.config.get('clock_mode'),'clock':clock.isoformat(),
                'elapsed_seconds':max(0,(clock-start).total_seconds()),'timezone':self.config['timezone']},
            'revision':revision,'runners':runners,'issues':issues,'anomalies':anomalies,'history':history,'source':health,
            'counts':{kind:sum(r['status']==kind for r in runners) for kind in ['finished','withdrawn','on_course','not_reported']}}

    def audit(self):
        with self.lock:
            return [dict(row) for row in self.db.execute('SELECT * FROM revisions ORDER BY sequence')]
