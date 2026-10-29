"""Read public Garmin MapShare KML without importing messages or device identifiers."""
from datetime import datetime,timezone
import hashlib
import math
from pathlib import Path
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo
from . import archive

NS={'k':'http://www.opengis.net/kml/2.2'}
STALE_SECONDS=1800


def feed_url(value):
    url=urllib.parse.urlsplit(value)
    if url.scheme!='https' or url.hostname!='share.garmin.com' or url.username or url.password or url.port:
        raise ValueError('Use a public https://share.garmin.com/NAME MapShare link')
    match=re.fullmatch(r'/(?:Feed/Share/)?([A-Za-z0-9_-]+)/?',url.path,re.I)
    if not match:raise ValueError('Invalid Garmin MapShare link')
    return 'https://share.garmin.com/Feed/Share/'+match[1]


def read_kml(url):
    request=urllib.request.Request(feed_url(url),headers={'User-Agent':'MountainDogRaceTracker/0.1'})
    with urllib.request.urlopen(request,timeout=12) as response:
        data=response.read(5_000_001)
    if len(data)>5_000_000:raise ValueError('Garmin feed exceeds the five-megabyte limit')
    return data


def race_positions(data,date,timezone_name,now=None):
    now=now or datetime.now(timezone.utc)
    try:root=ET.fromstring(data)
    except ET.ParseError as exc:raise ValueError('Garmin did not return valid KML') from exc
    if root.tag!='{'+NS['k']+'}kml':raise ValueError('Garmin did not return a KML feed; check MapShare sharing')
    positions=[];devices=set()
    for mark in root.findall('.//k:Placemark',NS):
        point=mark.find('k:Point/k:coordinates',NS)
        stamp=mark.findtext('k:TimeStamp/k:when',namespaces=NS)
        if point is None or not point.text or not stamp:continue
        fields={d.get('name'):d.findtext('k:value',namespaces=NS) for d in mark.findall('k:ExtendedData/k:Data',NS)}
        if str(fields.get('Valid GPS Fix','true')).lower() not in {'true','1'}:continue
        if 'waypoint' in (mark.findtext('k:styleUrl',default='',namespaces=NS)).lower():continue
        try:
            moment=datetime.fromisoformat(stamp.replace('Z','+00:00'))
            if moment.tzinfo is None:continue
            if moment.astimezone(ZoneInfo(timezone_name)).date().isoformat()!=date:continue
            if (moment-now).total_seconds()>300:continue
            coordinates=[float(x) for x in point.text.strip().split(',')]
            lon,lat=coordinates[:2]
            if not math.isfinite(lon) or not math.isfinite(lat) or not -180<=lon<=180 or not -90<=lat<=90:continue
        except (ValueError,TypeError):continue
        device=fields.get('Device Identifier') or fields.get('IMEI')
        if device:devices.add(device)
        positions.append({'longitude':lon,'latitude':lat,'time':moment.astimezone(timezone.utc).isoformat()})
    if len(devices)>1:raise ValueError('Garmin feed has multiple devices; use a MapShare feed for the sweep device only')
    return sorted(positions,key=lambda p:p['time'])


def latest_position(data,date,timezone_name,now=None):
    points=race_positions(data,date,timezone_name,now)
    return points[-1] if points else None


def locate_on_course(position,route,max_offset=500):
    coordinates=route['coordinates'];distances=route.get('distance_m')
    if len(coordinates)<2:raise ValueError('Course has no route to compare with sweeper GPS')
    lon,lat=position['longitude'],position['latitude']
    scale_x=111320*math.cos(math.radians(lat));scale_y=111320
    candidates=[];walked=0
    for i,(a,b) in enumerate(zip(coordinates,coordinates[1:])):
        ax,ay=(a[0]-lon)*scale_x,(a[1]-lat)*scale_y
        bx,by=(b[0]-lon)*scale_x,(b[1]-lat)*scale_y
        dx,dy=bx-ax,by-ay;length=math.hypot(dx,dy)
        t=max(0,min(1,-(ax*dx+ay*dy)/(length*length))) if length else 0
        offset=math.hypot(ax+t*dx,ay+t*dy)
        distance=(distances[i]+t*(distances[i+1]-distances[i])) if distances and len(distances)==len(coordinates) else walked+t*length
        candidates.append((offset,distance));walked+=length
    offset,distance=min(candidates)
    near=[d for error,d in candidates if error<=offset+20]
    ambiguous=max(near)-min(near)>500
    return {**position,'offset_m':round(offset,1),'on_course':offset<=max_offset,
            'distance_m':round(distance,1) if offset<=max_offset and not ambiguous else None,
            'course_distance_ambiguous':ambiguous}


def poll(store,url=None,kml_file=None,now=None):
    now=now or datetime.now(timezone.utc)
    identity=str(Path(kml_file).resolve()) if kml_file else feed_url(url)
    key=hashlib.sha256(identity.encode()).hexdigest()
    previous=store.sweeper
    saved=previous if previous.get('feed_key')==key and previous.get('race_date')==store.config['date'] else {}
    saved={**saved,'enabled':True,'feed_key':key,'race_date':store.config['date'],
           'label':'Sweep team','last_attempt':now.isoformat(),'stale_after_seconds':STALE_SECONDS}
    try:
        data=Path(kml_file).read_bytes() if kml_file else read_kml(url)
        if len(data)>5_000_000:raise ValueError('Garmin feed exceeds the five-megabyte limit')
        points=race_positions(data,store.config['date'],store.config['timezone'],now)
        archive.record_gps(store,key,points,now.isoformat())
        position=points[-1] if points else None
        if position and (not saved.get('position') or position['time']>=saved['position']['time']):
            saved['position']=locate_on_course(position,store.config['course']['route'])
        saved.update(last_success=now.isoformat(),error=None)
        success=True
    except Exception as exc:
        saved['error']=str(exc) if isinstance(exc,ValueError) else 'Could not read Garmin tracking feed; last GPS report retained.'
        success=False
    store.set_sweeper(saved)
    archive.record_poll(store,'garmin',success,saved.get('error'))
    return success


def public_state(saved):
    if not saved.get('enabled'):return {'enabled':False}
    # Never export raw KML, messages, device numbers, file paths or source cache keys.
    result={k:saved[k] for k in ('enabled','label','position','last_attempt','last_success','stale_after_seconds') if k in saved}
    if result.get('position') and not result['position'].get('on_course'):
        result['off_course']=True
        result['last_position_time']=result['position']['time']
        result['position']=None
    result['error']='Garmin update failed; showing the last reported GPS position.' if saved.get('error') else None
    return result
