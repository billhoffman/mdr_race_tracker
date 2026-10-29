"""Append-only race-director commands, independent of radio operators' wording."""
from datetime import datetime
import hashlib
import json
import re

SOURCE='director-log'
HEADINGS={'race director log','race director','rd log','commands'}


def initialize(store):
    store.db.executescript('''
        CREATE TABLE IF NOT EXISTS director_commands(sequence INTEGER PRIMARY KEY AUTOINCREMENT,
            id TEXT UNIQUE,payload TEXT,raw TEXT,received TEXT);
        CREATE TABLE IF NOT EXISTS director_runners(bib TEXT PRIMARY KEY,name TEXT);
    ''')
    for row in store.db.execute('SELECT bib,name FROM director_runners'):
        old=store.config['runners'].get(row['bib'])
        if old and old['name']!=row['name']:
            raise ValueError('Roster conflicts with director-added bib '+row['bib']+'; review the bib assignment.')
        store.config['runners'][row['bib']]={'bib':row['bib'],'name':row['name']}


def parse(raw, command_id, config, validate):
    match=re.fullmatch(r'(UNDO DNS|UNDO PASS|UNDO FINISH|UNDO WITHDRAW|ADD|DNS|PASS|FINISH|WITHDRAW)\s+([A-Za-z0-9_-]+)\s*(.*)',raw,re.I)
    if not match:raise ValueError('Use ADD bib | Name, DNS bib, UNDO DNS bib, PASS bib | checkpoint | HH:MM, FINISH bib | HH:MM, or WITHDRAW bib | HH:MM')
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
    if action in {'DNS','UNDO DNS','UNDO FINISH','UNDO WITHDRAW'}:
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
            except ValueError as exc:
                issues.append({'line':line_number,'text':raw,'message':str(exc)})
                continue
            payload=json.dumps(command,sort_keys=True)
            store.db.execute('INSERT INTO director_commands(id,payload,raw,received) VALUES(?,?,?,?)',
                             (command_id,payload,raw,received))
            store.db.execute('INSERT INTO revisions(source,id,payload,raw,received) VALUES(?,?,?,?,?)',
                             (SOURCE,command_id,payload,raw,received))
            if command['action']=='ADD':
                store.db.execute('INSERT OR IGNORE INTO director_runners VALUES(?,?)',(command['bib'],command['name']))
                store.config['runners'][command['bib']]={'bib':command['bib'],'name':command['name']}
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
        command=json.loads(row['payload']);bib=command['bib'];action=command['action']
        if action in {'DNS','UNDO DNS'}:dns[bib]=action=='DNS'
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
