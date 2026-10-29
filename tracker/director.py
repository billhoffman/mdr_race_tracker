"""Append-only race-director commands, independent of radio operators' wording."""
from datetime import datetime
import hashlib
import json
import re
from zoneinfo import ZoneInfo

SOURCE='director-log'
HEADINGS={'race director log','race director','rd log','commands'}


def initialize(store):
    store.db.executescript('''
        CREATE TABLE IF NOT EXISTS director_commands(sequence INTEGER PRIMARY KEY AUTOINCREMENT,
            id TEXT UNIQUE,payload TEXT,raw TEXT,received TEXT);
        CREATE TABLE IF NOT EXISTS director_runners(bib TEXT PRIMARY KEY,name TEXT);
        CREATE TABLE IF NOT EXISTS director_removed(bib TEXT PRIMARY KEY);
    ''')
    removed={row['bib'] for row in store.db.execute('SELECT bib FROM director_removed')}
    for row in store.db.execute('SELECT bib,name FROM director_runners'):
        if row['bib'] in removed:
            if row['bib'] in store.base_bibs:
                raise ValueError('RD-removed bib '+row['bib']+' appears in the uploaded roster; review before importing it.')
            continue
        old=store.config['runners'].get(row['bib'])
        if old and old['name']!=row['name']:
            raise ValueError('Roster conflicts with director-added bib '+row['bib']+'; review the bib assignment.')
        store.config['runners'][row['bib']]={'bib':row['bib'],'name':row['name']}
    override=store.db.execute("SELECT value FROM meta WHERE key='director_start_override'").fetchone()
    if override:
        store.start_override=True
        store.config['start']=datetime.fromisoformat(override['value'])
        store.config['start_time']=override['value']


def parse(raw, command_id, config, validate):
    if re.fullmatch(r'UNDO\s+START\s+TIME',raw,re.I):
        return {'id':command_id,'action':'UNDO_START_TIME'}
    if re.match(r'START\s+TIME\b',raw,re.I):
        match=re.fullmatch(r'START\s+TIME(?:\s*\|\s*|\s+)(\d{4}|\d{2}:\d{2}(?::\d{2})?)',raw,re.I)
        if not match:raise ValueError('Use START TIME HH:MM[:SS], for example START TIME 08:01')
        clock=match[1]
        if len(clock)==4:clock=clock[:2]+':'+clock[2:]
        try:
            pattern='%Y-%m-%dT%H:%M:%S' if clock.count(':')==2 else '%Y-%m-%dT%H:%M'
            start=datetime.strptime(config['date']+'T'+clock,pattern).replace(tzinfo=ZoneInfo(config['timezone']))
        except ValueError as exc:raise ValueError('Invalid race start time; use HH:MM[:SS] on the configured race date') from exc
        return {'id':command_id,'action':'START_TIME','start_time':start.isoformat()}
    match=re.fullmatch(r'(UNDO DNS|UNDO PASS|UNDO FINISH|UNDO WITHDRAW|ADD|REMOVE|DNS|PASS|FINISH|WITHDRAW)\s+([A-Za-z0-9_-]+)\s*(.*)',raw,re.I)
    if not match:raise ValueError('Use START TIME HH:MM, ADD bib | Name, REMOVE bib, DNS bib, UNDO DNS bib, PASS bib | checkpoint | HH:MM, FINISH bib | HH:MM, or WITHDRAW bib | HH:MM')
    action,bib,tail=match.groups();action=action.upper()
    values=[part.strip() for part in tail.split('|')[1:]] if tail.startswith('|') else []
    if tail and not tail.startswith('|'):raise ValueError('Separate the command fields with |')
    command={'id':command_id,'action':action,'bib':bib}
    if action=='ADD':
        if len(values)!=1 or not values[0]:raise ValueError('Use ADD bib | Full Name')
        name=' '.join(values[0].split())
        old=config['runners'].get(bib)
        if old and old['name']!=name:raise ValueError('Bib '+bib+' already belongs to '+old['name']+'; reassignment needs review')
        return {**command,'name':name}
    if bib not in config['runners']:raise ValueError('Unknown bib '+bib+'; add it to the roster or put ADD above this command')
    if action in {'REMOVE','DNS','UNDO DNS','UNDO FINISH','UNDO WITHDRAW'}:
        if values:raise ValueError(action+' takes only a bib')
        return command
    if action=='UNDO PASS':
        if len(values)!=1 or values[0].upper() not in config['checkpoints'] and values[0].upper()!='START':
            raise ValueError('Use UNDO PASS bib | checkpoint')
        return {**command,'station':values[0].upper()}
    if action=='PASS':
        if len(values)!=2:raise ValueError('Use PASS bib | checkpoint | HH:MM[:SS]')
        station,clock=values
    elif action=='FINISH':
        if len(values)!=1:raise ValueError('Use FINISH bib | HH:MM[:SS]')
        station,clock='FINISH',values[0]
    else:
        if len(values) not in {1,2}:raise ValueError('Use WITHDRAW bib | HH:MM[:SS], optionally WITHDRAW bib | checkpoint | HH:MM')
        station,clock=(values if len(values)==2 else ('START',values[0]))
    if re.fullmatch(r'\d{4}',clock):clock=clock[:2]+':'+clock[2:]
    kind='WITHDRAWN' if action=='WITHDRAW' else action
    event=validate(f'{command_id} | {clock} | {station} | {bib} | {kind}',config)
    if action=='WITHDRAW' and len(values)==1:event['station']=None
    event['time_basis']='race director observation'
    return {**command,'event':event}



def check_roster_command(store,command):
    if 'bib' not in command:return
    bib=command['bib']
    saved=store.db.execute('SELECT name FROM director_runners WHERE bib=?',(bib,)).fetchone()
    if command['action']=='ADD' and saved and saved['name']!=command['name']:
        raise ValueError('Bib '+bib+' has an earlier director assignment; use a different bib instead of reassigning it')
    if command['action']!='REMOVE':return
    if bib in store.base_bibs or not saved:
        raise ValueError('REMOVE is only for RD-added runners absent from the uploaded roster; use DNS for an entrant who did not start')
    # Inspect the entire audit, including voided/overridden observations. Keeping
    # a runner's history intact takes precedence over removing a test entry.
    for row in store.db.execute('SELECT payload FROM revisions'):
        payload=json.loads(row['payload'])
        event=payload.get('event',payload)
        if bib in event.get('bibs',[]) and event.get('kind') in {'PASS','FINISH','WITHDRAWN'}:
            raise ValueError('Cannot REMOVE bib '+bib+': it has recorded race observations, including any later voided or overridden reports')

def ingest(store,text,validate):
    # Plain paragraphs, not the radio team's TIME/MESSAGE table.
    from .radio import input_rows
    if input_rows(text) is not None:raise ValueError('Use plain command paragraphs in the RD document, not a TIME/MESSAGE table')
    occurrences={};issues=[];present=set()
    with store.lock,store.db:
        received=datetime.now().astimezone().isoformat()
        for line_number,raw in enumerate(text.splitlines(),1):
            raw=' '.join(raw.lstrip('\ufeff').split())
            if not raw or raw.startswith('#') or raw.lower().rstrip(':') in HEADINGS:continue
            # Include occurrence number so DNS -> UNDO DNS -> DNS can be appended.
            canonical=re.sub(r'\s*\|\s*',' | ',raw)
            digest=hashlib.sha256(canonical.encode()).hexdigest()[:24]
            occurrences[digest]=occurrences.get(digest,0)+1
            command_id=f'D{digest}_{occurrences[digest]}'
            present.add(command_id)
            old=store.db.execute('SELECT payload FROM director_commands WHERE id=?',(command_id,)).fetchone()
            if old:continue
            try:
                command=parse(raw,command_id,store.config,validate)
                check_roster_command(store,command)
            except ValueError as exc:
                issues.append({'line':line_number,'text':raw,'message':str(exc)})
                continue
            payload=json.dumps(command,sort_keys=True)
            store.db.execute('INSERT INTO director_commands(id,payload,raw,received) VALUES(?,?,?,?)',
                             (command_id,payload,raw,received))
            store.db.execute('INSERT INTO revisions(source,id,payload,raw,received) VALUES(?,?,?,?,?)',
                             (SOURCE,command_id,payload,raw,received))
            if command['action'] in {'START_TIME','UNDO_START_TIME'}:
                if command['action']=='START_TIME':
                    start=datetime.fromisoformat(command['start_time'])
                    store.db.execute("INSERT OR REPLACE INTO meta VALUES('director_start_override',?)",(start.isoformat(),))
                else:
                    start=store.base_start
                    store.db.execute("DELETE FROM meta WHERE key='director_start_override'")
                store.start_override=command['action']=='START_TIME'
                store.config['start']=start
                store.config['start_time']=start.isoformat()
            elif command['action']=='ADD':
                store.db.execute('INSERT OR IGNORE INTO director_runners VALUES(?,?)',(command['bib'],command['name']))
                store.db.execute('DELETE FROM director_removed WHERE bib=?',(command['bib'],))
                store.config['runners'][command['bib']]={'bib':command['bib'],'name':command['name']}
            elif command['action']=='REMOVE':
                store.db.execute('INSERT OR IGNORE INTO director_removed VALUES(?)',(command['bib'],))
                store.config['runners'].pop(command['bib'],None)
            if 'event' in command:
                store.db.execute('INSERT OR REPLACE INTO entries VALUES(?,?,?,?,?,1)',
                    (SOURCE,command_id,json.dumps(command['event'],sort_keys=True),raw,received))
        for old in store.db.execute('SELECT id,raw FROM director_commands ORDER BY sequence'):
            if old['id'] not in present:
                issues.append({'line':None,'text':old['raw'],'message':'Accepted RD command is missing; its effect is retained. Append an UNDO or a correcting command instead of deleting history.'})
        store.save_issues(SOURCE,issues)
    return issues


def controls(store):
    dns={};passages={};terminals={}
    for row in store.db.execute('SELECT payload FROM director_commands ORDER BY sequence'):
        command=json.loads(row['payload'])
        if 'bib' not in command:continue
        bib=command['bib'];action=command['action']
        if action=='REMOVE':
            dns.pop(bib,None);terminals.pop(bib,None)
            passages={key:value for key,value in passages.items() if key[0]!=bib}
        elif action in {'DNS','UNDO DNS'}:dns[bib]=action=='DNS'
        elif action=='PASS':passages[bib,command['event']['station']]=command['event']
        elif action=='UNDO PASS':passages[bib,command['station']]=None
        elif action in {'FINISH','WITHDRAW'}:terminals[bib]=command['event']
        elif action in {'UNDO FINISH','UNDO WITHDRAW'}:
            old=terminals.get(bib)
            if old and old['kind']==('FINISH' if action=='UNDO FINISH' else 'WITHDRAWN'):terminals[bib]=None
    return dns,passages,terminals


def select_events(bib,events,settings,anomalies):
    dns,passages,terminals=settings
    if dns.get(bib):
        if events:anomalies.append({'bib':bib,'id':'RD-DNS','message':'Director DNS conflicts with observations; DNS takes precedence. UNDO DNS restores report-based status.'})
        return []
    terminal=terminals.get(bib)
    filtered=[]
    for event in events:
        passage=passages.get((bib,event['station']))
        override=terminal if event['kind'] in {'FINISH','WITHDRAWN'} else passage
        if event['source']==SOURCE:
            if not override or override['id']!=event['id']:continue
        elif override:
            if event['time']!=override['time'] or event['kind']!=override['kind']:
                anomalies.append({'bib':bib,'id':event['id'],'message':'Director correction overrides this radio observation; original retained in audit.'})
            continue
        filtered.append(event)
    return filtered
