"""Aggregate radio evidence used only for display estimates, never bib passages."""
from datetime import datetime
import re
from zoneinfo import ZoneInfo
from .radio import CLOCK,STATION,clock_text


def parse_boundary(row,config):
    text=row['message']
    if re.search(r'\?|\b(?:correction|duplicate|last known|last checked|no sign of|all but|except|outstanding|remaining|not|never|will|request|requesting)\b',text,re.I):return None
    clearance=bool(re.search(r'\ball\s+(?:the\s+)?runners\s+(?:have\s+)?passed\b',text,re.I))
    leader=bool(re.search(r'\bfirst\s+(?:overall\s+)?runner\b',text,re.I))
    if not (clearance or leader):return None
    stations=list(dict.fromkeys(m[1].upper() for m in STATION.finditer(text)))
    if len(stations)!=1:return None
    station=stations[0]
    if station not in config['checkpoints']:raise ValueError('Unknown aggregate-report checkpoint '+station)
    passage_text=re.split(r'\bsweeps?\b',text,flags=re.I)[0]
    clocks=re.findall(r'(?:\bat\b|@)\s*('+CLOCK+r')(?!\d)',passage_text,re.I)
    if len(set(clocks))>1:raise ValueError('Aggregate report has several passage times; review the row')
    clock=clock_text(clocks[0] if clocks else row['time'])
    try:
        moment=datetime.strptime(config['date']+'T'+clock,'%Y-%m-%dT%H:%M:%S' if clock.count(':')==2 else '%Y-%m-%dT%H:%M').replace(tzinfo=ZoneInfo(config['timezone']))
    except ValueError as exc:raise ValueError('Invalid aggregate passage time') from exc
    report=clock_text(row['time'])
    try:reported=datetime.strptime(config['date']+'T'+report,'%Y-%m-%dT%H:%M:%S' if report.count(':')==2 else '%Y-%m-%dT%H:%M').replace(tzinfo=ZoneInfo(config['timezone']))
    except ValueError as exc:raise ValueError('Invalid aggregate report time') from exc
    if (moment-reported).total_seconds()>120:raise ValueError('Aggregate passage is more than two minutes ahead of the report clock')
    if moment<config['start']:raise ValueError('Aggregate passage is before the configured race start')
    return {'id':row['id']+'_B','kind':'CLEARANCE' if clearance else 'LEADER',
            'station':station,'time':moment.isoformat(),'report_time':clock_text(row['time']),'bibs':[],'void':False,
            'time_basis':'explicit passage time' if clocks else 'radio report time'}
