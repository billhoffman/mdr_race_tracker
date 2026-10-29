"""Private capture for later replay; no movie rendering or public endpoints."""
from datetime import datetime,timezone
import hashlib
import json


def initialize(store,config):
    store.db.executescript('''
        CREATE TABLE IF NOT EXISTS capture_versions(sequence INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT,digest TEXT,content TEXT,received TEXT);
        CREATE INDEX IF NOT EXISTS capture_source ON capture_versions(source,sequence);
        CREATE TABLE IF NOT EXISTS gps_history(sequence INTEGER PRIMARY KEY AUTOINCREMENT,
            feed_key TEXT,digest TEXT,payload TEXT,received TEXT,origin TEXT,UNIQUE(feed_key,digest));
        CREATE TABLE IF NOT EXISTS poll_history(sequence INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT,received TEXT,success INTEGER,error TEXT);
    ''')
    store.db.execute("INSERT OR IGNORE INTO meta VALUES('capture_started_at',?)",(datetime.now(timezone.utc).isoformat(),))
    store.db.commit()
    race={k:config[k] for k in ('race_id','name','date','timezone','test_mode','clock_mode') if k in config}
    race['start_time']=config['start'].isoformat()
    content={'race':race,'course':config['course'],'roster':list(config['runners'].values())}
    record_version(store,'configuration',json.dumps(content,sort_keys=True))


def record_version(store,source,content):
    digest=hashlib.sha256(content.encode()).hexdigest()
    with store.lock,store.db:
        old=store.db.execute('SELECT digest FROM capture_versions WHERE source=? ORDER BY sequence DESC LIMIT 1',(source,)).fetchone()
        if old and old['digest']==digest:return
        store.db.execute('INSERT INTO capture_versions(source,digest,content,received) VALUES(?,?,?,?)',
                         (source,digest,content,datetime.now(timezone.utc).isoformat()))


def record_poll(store,source,success,error=None):
    with store.lock,store.db:
        store.db.execute('INSERT INTO poll_history(source,received,success,error) VALUES(?,?,?,?)',
                         (source,datetime.now(timezone.utc).isoformat(),int(success),error))


def record_gps(store,feed_key,positions,received=None,origin='garmin-feed'):
    received=received or datetime.now(timezone.utc).isoformat()
    with store.lock,store.db:
        for point in positions:
            # Keep race-day GPS coordinates/timestamps only, never Garmin texts,
            # account names, emergency messages, or device identifiers.
            safe={'longitude':float(point['longitude']),'latitude':float(point['latitude']),
                  'time':datetime.fromisoformat(point['time']).astimezone(timezone.utc).isoformat()}
            payload=json.dumps(safe,sort_keys=True)
            digest=hashlib.sha256(payload.encode()).hexdigest()
            store.db.execute('INSERT OR IGNORE INTO gps_history(feed_key,digest,payload,received,origin) VALUES(?,?,?,?,?)',
                             (feed_key,digest,payload,received,origin))
