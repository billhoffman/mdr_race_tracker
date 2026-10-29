from datetime import datetime,timezone
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
import zipfile

from tracker.core import Store,load_config
from tracker.pipeline import poll_once
from tracker.sweepers import poll
from tracker.archive import record_version
from tracker.export_race import export_race
from tracker.tests.test_sweepers import kml,mark,NOW

ROOT=Path(__file__).resolve().parents[2]


class RaceArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.config=load_config(ROOT/'races/moreau-test/race.json')
        self.path=self.root/'race.sqlite3';self.store=Store(self.path,self.config)
    def tearDown(self):self.store.close();self.temp.cleanup()
    def rows(self,table):return [dict(r) for r in self.store.db.execute('SELECT * FROM '+table+' ORDER BY rowid')]
    def test_all_gps_points_in_feed_are_saved_once_with_late_arrivals(self):
        path=self.root/'gps.kml';path.write_bytes(kml(mark('2026-10-31T13:40:00Z'),mark()))
        poll(self.store,kml_file=path,now=NOW)
        self.assertEqual(len(self.rows('gps_history')),2)
        poll(self.store,kml_file=path,now=NOW)
        self.assertEqual(len(self.rows('gps_history')),2)
        path.write_bytes(kml(mark('2026-10-31T13:30:00Z')))
        poll(self.store,kml_file=path,now=NOW)
        self.assertEqual(len(self.rows('gps_history')),3)
        self.assertEqual(self.store.sweeper['position']['time'],'2026-10-31T13:55:00+00:00')
        for row in self.rows('gps_history'):
            self.assertEqual(set(json.loads(row['payload'])),{'longitude','latitude','time'})
            self.assertNotIn('private-imei',row['payload'])
    def test_restart_preserves_history_and_recovers_legacy_latest_fix(self):
        self.store.set_sweeper({'enabled':True,'feed_key':'test','last_success':NOW.isoformat(),
            'position':{'longitude':-73,'latitude':43,'time':NOW.isoformat(),'on_course':True}})
        self.store.close();self.store=Store(self.path,self.config)
        self.assertEqual(len(self.rows('gps_history')),1)
        self.assertEqual(self.rows('gps_history')[0]['origin'],'recovered-latest-state')
        self.store.close();self.store=Store(self.path,self.config)
        self.assertEqual(len(self.rows('gps_history')),1)
    def test_full_source_versions_capture_invalid_edits_deletions_and_reverts(self):
        radio=self.root/'radio.txt';rd=self.root/'rd.txt';rd.write_text('# reference\nDNS 102')
        a='T001 | 09:10 | A | 101 | PASS';radio.write_text(a)
        poll_once(self.store,'file',radio,director_log=rd)
        poll_once(self.store,'file',radio,director_log=rd)
        for text in ['bad partial edit','',a]:
            radio.write_text(text);poll_once(self.store,'file',radio,director_log=rd)
        versions=[r for r in self.rows('capture_versions') if r['source']=='primary-log']
        self.assertEqual([r['content'] for r in versions],[a,'bad partial edit','',a])
        self.assertEqual(len([r for r in self.rows('capture_versions') if r['source']=='director-log']),1)
        self.assertEqual(len(self.rows('poll_history')),10)
        self.assertEqual(self.store.snapshot()['runners'][0]['last']['station'],'A')
    def test_configuration_versions_save_course_roster_and_configured_start(self):
        first=self.rows('capture_versions');self.assertEqual(len(first),1)
        decoded=json.loads(first[0]['content'])
        self.assertEqual(decoded['race']['start_time'],self.config['start'].isoformat())
        self.assertEqual(decoded['course'],self.config['course'])
        self.assertEqual(len(decoded['roster']),6)
        self.store.close();self.store=Store(self.path,self.config)
        self.assertEqual(len(self.rows('capture_versions')),1)
        self.store.close()
        changed={**self.config,'name':'Updated name'}
        self.store=Store(self.path,changed)
        self.assertEqual(len(self.rows('capture_versions')),2)
    def test_read_failures_are_saved_without_erasing_versions(self):
        radio=self.root/'radio.txt';radio.write_text('')
        poll_once(self.store,'file',radio)
        radio.unlink();self.assertFalse(poll_once(self.store,'file',radio))
        self.assertEqual(len([r for r in self.rows('capture_versions') if r['source']=='primary-log']),1)
        polls=self.rows('poll_history');self.assertEqual([p['success'] for p in polls],[1,0])
        self.assertTrue(polls[-1]['error'])
    def test_export_consistent_backup_contains_history_and_readable_json(self):
        self.store.ingest_director('START TIME 09:01\nADD 107 | Late Runner\nDNS 102')
        self.store.ingest('T001 | 09:10 | A | 107 | PASS')
        path=self.root/'gps.kml';path.write_bytes(kml(mark()))
        poll(self.store,kml_file=path,now=NOW)
        output=self.root/'private-export.zip'
        before=self.store.snapshot()['revision']
        manifest=export_race(self.path,output)
        self.assertEqual(manifest['counts']['gps_history'],1)
        self.assertEqual(manifest['counts']['director_commands'],3)
        self.assertEqual(self.store.snapshot()['revision'],before)
        with zipfile.ZipFile(output) as bundle:
            self.assertIn('race.sqlite3',bundle.namelist())
            gps=bundle.read('sweeper-gps.jsonl').decode()
            self.assertNotIn('private-message',gps);self.assertNotIn('private-imei',gps)
            backup=self.root/'backup.sqlite3';backup.write_bytes(bundle.read('race.sqlite3'))
            db=sqlite3.connect(backup)
            try:
                self.assertEqual(db.execute("SELECT value FROM meta WHERE key='director_start_override'").fetchone()[0],'2026-10-31T09:01:00-04:00')
                self.assertEqual(db.execute('SELECT COUNT(*) FROM revisions').fetchone()[0],before)
                self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            finally:db.close()
        with self.assertRaisesRegex(ValueError,'already exists'):export_race(self.path,output)
    def test_export_missing_database_does_not_create_one(self):
        missing=self.root/'missing.sqlite3'
        with self.assertRaisesRegex(ValueError,'does not exist'):export_race(missing,self.root/'bad.zip')
        self.assertFalse(missing.exists())


if __name__=='__main__':unittest.main()
