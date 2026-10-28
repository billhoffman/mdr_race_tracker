"""Fill missing course elevations once from USGS: python3 -m tracker.fill_elevation"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import time
import urllib.parse
import urllib.request

from .publish import atomic_write

ROOT=Path(__file__).resolve().parents[1]
SERVICE='https://epqs.nationalmap.gov/v1/json'


def elevation_value(response):
    try:
        value=float(response['value'])
    except (TypeError,KeyError,ValueError) as exc:
        raise ValueError('USGS response has no usable elevation value') from exc
    if not math.isfinite(value) or value < -500 or value > 9000:
        raise ValueError('USGS returned an invalid/no-data elevation')
    return value


def query(longitude,latitude):
    url=SERVICE+'?'+urllib.parse.urlencode({'x':longitude,'y':latitude,'units':'Meters','wkid':'4326','includeDate':'true'})
    request=urllib.request.Request(url,headers={'User-Agent':'MountainDogRaceTracker/0.1','Accept':'application/json'})
    with urllib.request.urlopen(request,timeout=20) as response:
        result=json.load(response)
    elevation_value(result)
    return result


def fill_course(path,cache,fetch=query):
    path,cache=Path(path),Path(cache)
    original=path.read_bytes()
    course=json.loads(original)
    route=course['route']
    indices=[i for i,p in enumerate(route['coordinates']) if len(p)<3 or p[2] is None or (route.get('elevation_zero_is_missing') and p[2]==0)]
    if not indices:
        print('No missing elevations; no changes needed.')
        return 0
    cache.mkdir(parents=True,exist_ok=True)
    recovered=[]
    for count,index in enumerate(indices,1):
        point=route['coordinates'][index]
        key=hashlib.sha256(json.dumps([point[0],point[1],'Meters',4326]).encode()).hexdigest()
        saved=cache/(key+'.json')
        if saved.exists():
            response=json.loads(saved.read_text())
        else:
            response=fetch(point[0],point[1])
            elevation_value(response)
            atomic_write(saved,json.dumps(response))
            time.sleep(0.1)
        value=elevation_value(response)
        recovered.append({'point_index':index,'longitude':point[0],'latitude':point[1],
                          'original_m':point[2] if len(point)>2 else None,'elevation_m':round(value,3)})
        print(f'Elevation {count}/{len(indices)}: {value:.1f} m',flush=True)
    # All point queries succeeded before replacing any original course elevations.
    backup=cache/('course-original-'+hashlib.sha256(original).hexdigest()[:16]+'.json')
    if not backup.exists():
        atomic_write(backup,original)
    backfill={'source':'USGS 3DEP Elevation Point Query Service',
        'service':SERVICE,'units':'meters','retrieved_at':datetime.now(timezone.utc).isoformat(),
        'points':recovered}
    if original!=path.read_bytes():
        raise ValueError('Course changed while downloading. Original course was not overwritten; rerun to apply cached data.')
    output=path.with_name(path.stem+'.elevation.local.json')
    atomic_write(output,json.dumps({'elevation_backfill':backfill},indent=2)+'\n')
    print(f'Filled {len(recovered)} elevations in {output}. The tracker loads this automatically.')
    print(f'Original course unchanged. Backup: {backup}')
    return len(recovered)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--course',type=Path,default=ROOT/'races/moreau-2026/course.json')
    parser.add_argument('--cache',type=Path,default=ROOT/'outputs/elevation-cache')
    args=parser.parse_args()
    try:
        fill_course(args.course,args.cache)
    except Exception as exc:
        raise SystemExit(f'Could not fill elevation: {exc}\nThe course is unchanged if download did not complete. Completed queries are cached; rerun to resume.')


if __name__=='__main__':main()
