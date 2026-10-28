"""Conservative interpretation of existing TIME/MESSAGE radio logs.

No race-specific bibs, results or paragraph fixes belong in this module.
"""
from difflib import SequenceMatcher
import json
from datetime import datetime
import re

ENVELOPE = 'MDR-RADIO-TABLE-1\n'
CLOCK = r'(?:[0-2]\d:[0-5]\d(?::[0-5]\d)?|[0-2]\d[0-5]\d)'
STATION = re.compile(r'\b(?:check\s*point|aid\s*station|station)\s+([A-Za-z])\b', re.I)
BIB = re.compile(r'#\s*(\d+)\b|\bbibs?\s*(?:number\s*)?#?\s*(\d+)\b|\brunners?\s+(?:number\s*)#?\s*(\d+)\b', re.I)
TIME = re.compile(r'(?<![\w#])'+CLOCK+r'(?!\w)')
PASS = re.compile(r'\b(?:pass(?:ed|ing)?|past|arriv(?:ed|ing)|first|second|third|last\s+runner)\b', re.I)
DROP = re.compile(r'\b(?:dropp?ed\s+(?:out|from)|withdrawn|withdrew|DNF|scratch(?:ed)?)\b', re.I)
FINISH = re.compile(r'\b(?:finished|completed)\s+(?:the\s+)?race\b|\bfinished\b', re.I)


def pack_rows(rows):
    return ENVELOPE + json.dumps(rows)


def input_rows(text):
    """Return table rows, or None for the original ID/pipe input format."""
    if text.startswith(ENVELOPE):
        return json.loads(text[len(ENVELOPE):])
    lines = text.lstrip('\ufeff').splitlines()
    # Google TXT exports separate the TIME cell and MESSAGE cell by whitespace.
    if not any(line.strip().upper()=='TIME' for line in lines):
        return None
    rows, clock, message = [], None, []
    for line in lines:
        line=line.strip()
        if not line or line.upper() in {'TIME','MESSAGE'} or line.startswith('Net Controls:'):
            continue
        match=re.fullmatch('('+CLOCK+r')(?:\s+(.+))?',line)
        if match:
            if clock is not None:
                rows.append({'time':clock,'message':' '.join(message)})
            clock, message=match[1], [match[2]] if match[2] else []
        elif clock is not None:
            message.append(line)
    if clock is not None:
        rows.append({'time':clock,'message':' '.join(message)})
    return rows


def normalize(row):
    return {'time':' '.join(str(row.get('time','')).split()),
            'message':' '.join(str(row.get('message','')).split())}


def identify_rows(previous, rows, next_id, retired=()):
    """Match unchanged rows and uniquely anchored edits across inserts/deletes.

    An unanchored multi-row replacement has no reliable identity: hold it rather
    than applying a correction to the wrong runner. Save identities in SQLite so
    cron processes and server restarts behave identically.
    """
    rows=[normalize(r) for r in rows if r.get('time') or r.get('message')]
    key=lambda r:json.dumps({k:r[k] for k in ('time','message')},sort_keys=True)
    matcher=SequenceMatcher(None,[key(r) for r in previous],[key(r) for r in rows],autojunk=False)
    mapped=[]; removed=list(retired)
    for tag,a,b,c,d in matcher.get_opcodes():
        if tag=='equal':
            mapped.extend({**row,'id':old['id']} for row,old in zip(rows[c:d],previous[a:b]))
        elif tag=='replace' and b-a==d-c==1:
            mapped.append({**rows[c],'id':previous[a]['id']})
        elif tag=='replace':
            # A partially edited last row plus newly appended rows is normal.
            # Match unique report-time/checkpoint anchors before holding a block.
            anchor=lambda r:(r['time'].replace(':',''),tuple(m[1].upper() for m in STATION.finditer(r['message'])))
            remaining_old=list(previous[a:b]);remaining_new=list(rows[c:d]);matches={}
            for new in list(remaining_new):
                candidates=[old for old in remaining_old if anchor(old)==anchor(new)]
                peers=[other for other in remaining_new if anchor(other)==anchor(new)]
                if len(candidates)==len(peers)==1:
                    old=candidates[0];matches[id(new)]=old['id']
                    remaining_old.remove(old);remaining_new.remove(new)
            if len(remaining_old)==len(remaining_new)==1:
                matches[id(remaining_new[0])]=remaining_old[0]['id']
                remaining_old=[];remaining_new=[]
            if remaining_old and remaining_new:
                raise ValueError('Several radio rows changed together and their identities are uncertain. Restore the last document version, then edit one existing row per update; last confirmed data retained.')
            removed.extend(remaining_old)
            for new in rows[c:d]:
                if id(new) in matches:mapped.append({**new,'id':matches[id(new)]})
                else:
                    mapped.append({**new,'id':f'R{next_id:06d}'});next_id+=1
        else:
            if tag=='delete':removed.extend(previous[a:b])
            if tag=='insert':
                for row in rows[c:d]:
                    matches=[old for old in removed if key(old)==key(row)]
                    if len(matches)==1:
                        old=matches[0];removed.remove(old);mapped.append({**row,'id':old['id']})
                    else:
                        mapped.append({**row,'id':f'R{next_id:06d}'})
                        next_id+=1
    return mapped,next_id,removed


def clock_text(value):
    value=value.strip()
    if not re.fullmatch(CLOCK,value):
        raise ValueError('Invalid radio TIME cell; expected HHMM or HH:MM')
    return value if ':' in value else value[:2]+':'+value[2:]


def parse_report(row, config, validate):
    """Return observations, [] for routine radio traffic, or raise for review.

    validate is the common structured-observation validator. Natural messages
    follow the same roster, date, time and checkpoint validation.
    """
    text=row['message']; report=clock_text(row['time'])
    text=re.split(r'\band asking for\b',text,flags=re.I)[0]
    if not text:
        raise ValueError('Radio row is incomplete; waiting for its message')
    # Never infer passages from requests, retrospective corrections, or sweep bibs.
    caution=r'\?|\b(?:correction|duplicate|last known|last checked|logged pass(?:ed)?|outstanding|remaining|remains|no sign of|all but|still out|not|never|will|expected|heading|returning|might not|may not|will be|hiking back|asking|asked|request(?:ing|ed)?|when\b|has not|not returned|no runners|no sweep|bib list|drop out list|scratches|scratched list)\b'
    # Cut clearly separated trailing summaries before inspecting the passage.
    text=re.split(r'(?:,?\s*(?:bib\s*)?#\s*\d+\s+remains\b)',text,flags=re.I)[0]
    text=re.split(r'\b(?:no sign of|\d+\s+runners?\s+have\s+passed|total\b|\d+-\d+ dozen|sweeps?\b|waiting for the sweeps|waiting on sweeps)',text,flags=re.I)[0].strip()
    if re.search(r'\ball runners (?:have )?passed\b',text,re.I) and not BIB.search(text):return []
    if re.search(caution,text,re.I):
        if BIB.search(text):raise ValueError('Question, correction, or uncertain runner report; review the original row')
        return []
    if re.search(r'\b(?:on station|setting up|ready|radio check|repeater|secure|safely left course|ride has arrived|leaving checkpoint with|taking .* to the start|ride back|update .*scratch)\b',text,re.I):
        return []
    finish=bool(FINISH.search(text)); drop=bool(DROP.search(text)); passage=bool(PASS.search(text))
    stations=list(dict.fromkeys(m[1].upper() for m in STATION.finditer(text)))
    if re.search(r'\b(?:finish\s*line|start\s*finish)\b',text,re.I) and not finish:
        return []
    if not BIB.search(text) and re.search(r'\b(?:reassigned|calling|securing|all runners|\d+ (?:male |female )?runners passed|checkpoint [A-Za-z] arrived)\b',text,re.I):return []
    if len(stations)>1:raise ValueError('More than one checkpoint in this report; location needs review')
    station='FINISH' if finish else stations[0] if stations else None
    # "Checkpoint K Bib #57 at @1415" is an explicit position report.
    position=bool(re.search(r'(?:\bat\s*@?|@|at the same time\s*)\s*'+CLOCK,text,re.I))
    if not (finish or drop or passage or position):
        if BIB.search(text) and station:
            raise ValueError('Runner mentioned without a clear passage or withdrawal')
        return []
    if not station and not drop:
        raise ValueError('Runner passage has no checkpoint')
    bibs=[]
    for match in BIB.finditer(text):
        if any(a<=match.start()<b for a,b,_ in bibs):continue
        bibs.append((match.start(),match.end(),next(v for v in match.groups() if v is not None)))
        tail=text[match.end():]
        listing=re.match(r'(?:\s*(?:,\s*(?:and\s+)?|and\s+)(?!#)\d{1,3}\b)+',tail,re.I)
        if listing:
            for sub in re.finditer(r'\d+',listing[0]):
                bibs.append((match.end()+sub.start(),match.end()+sub.end(),sub[0]))
    # Buck occasionally omitted "Bib" immediately after the checkpoint label.
    if not bibs and stations:
        cp=STATION.search(text)
        match=re.match(r'\s+(\d{1,3})\b(?=\s+(?:just\s+)?pass)',text[cp.end():],re.I)
        if match:bibs.append((cp.end()+match.start(1),cp.end()+match.end(1),match[1]))
    bibs.sort()
    if not bibs:
        if drop or passage or finish:
            raise ValueError('Passage or withdrawal has no identifiable bib; counts alone cannot identify runners')
        return []
    # Associate actions with preceding bib groups, independently of time tokens.
    # This distinguishes "#101 and #102 dropped, #103 passed" correctly.
    actions=re.compile(DROP.pattern+'|'+FINISH.pattern+r'|\b(?:passed|passing|past|arrived|arriving)\b',re.I)
    action_tokens=[(m.start(),'action',m[0]) for m in actions.finditer(text)]
    action_tokens.extend((a,'bib',a) for a,_,_ in bibs)
    action_tokens.sort(key=lambda item:item[0])
    kinds={};pending_actions=[];last_action=None
    for _,token,value in action_tokens:
        if token=='bib':pending_actions.append(value)
        else:
            last_action='WITHDRAWN' if DROP.fullmatch(value) else 'FINISH' if FINISH.fullmatch(value) else 'PASS'
            for bib_pos in pending_actions:kinds[bib_pos]=last_action
            pending_actions=[]
    default='FINISH' if finish else 'WITHDRAWN' if drop and not passage and not position else 'PASS'
    for bib_pos in pending_actions:kinds[bib_pos]=last_action or default
    tokens=[(a,'bib',(bib,b)) for a,b,bib in bibs]
    for match in TIME.finditer(text):
        if not any(a<=match.start()<b for a,b,_ in bibs):tokens.append((match.start(),'time',match[0]))
    tokens.sort(key=lambda t:t[0])
    paired=[];pending=[];leading=None;explicit_bibs=set()
    for pos,kind,value in tokens:
        if kind=='bib':pending.append((pos,*value))
        elif pending:
            last_kind=kinds[pending[-1][0]]
            for p,bib,end in pending:
                shared=kinds[p]==last_kind
                paired.append((p,bib,end,clock_text(value) if shared else report))
                if shared:explicit_bibs.add(p)
            pending=[];leading=None
        else:leading=clock_text(value)
    paired.extend((p,bib,end,leading or report) for p,bib,end in pending)
    if leading:explicit_bibs.update(p for p,_,_ in pending)
    if len({bib for _,bib,_,_ in paired})!=len(paired):
        raise ValueError('Same bib appears more than once in a radio row; review times/identity')
    events=[]
    for i,(pos,bib,end,clock) in enumerate(paired,1):
        kind=kinds[pos]
        if kind=='PASS' and not station:
            raise ValueError('Runner passage has no checkpoint')
        # A broadcast drop does not establish a location. Keep last known position
        # separately; do not move a dropped runner to the reporting operator.
        place=station
        if kind=='WITHDRAWN':
            explicit=re.search(r'\b(?:dropp?ed\s+(?:out|from)|withdrew|withdrawn).*?\bat\s+(?:check\s*point|aid\s*station)\s+([A-Za-z])\b',text,re.I)
            place=explicit[1].upper() if explicit else None
        event=validate(f'{row["id"]}_{i:02d} | {clock} | {place or "START"} | {bib} | {kind}',config)
        event['station']=place
        event['time_basis']='explicit passage time' if pos in explicit_bibs else 'radio report time'
        event['report_time']=report
        # A future passage in a past-tense report is a likely typo.
        report_event=validate(f'{row["id"]} | {report} | START | {bib} | PASS',config)
        ahead=(datetime.fromisoformat(event['time'])-datetime.fromisoformat(report_event['time'])).total_seconds()
        if ahead>120:
            raise ValueError('Passage time is more than two minutes later than the radio report time; review the clock')
        if ahead>0:event['clock_warning']=True
        events.append(event)
    return events
