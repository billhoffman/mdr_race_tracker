"""Director start corrections change elapsed times, never recorded wall times."""
from datetime import datetime
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tracker.core import Store,load_config
from tracker.pipeline import poll_once
from tracker.publish import publish

ROOT=Path(__file__).resolve().parents[2]


class StartTimeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.config=load_config(ROOT/'races/moreau-test/race.json')
        self.path=self.root/'test.sqlite3';self.store=Store(self.path,self.config)
    def tearDown(self):self.store.close();self.temp.cleanup()
    def runner(self):return self.store.snapshot()['runners'][0]
    def test_correction_adjusts_elapsed_clock_finish_and_preserves_passages(self):
        self.store.ingest('T001 | 09:10 | A | 101 | PASS\nT002 | 11:00 | FINISH | 101 | FINISH')
        before=self.store.snapshot();times=[r['time'] for r in self.runner()['reports']]
        self.assertFalse(self.store.ingest_director('START TIME 09:01'))
        after=self.store.snapshot()
        self.assertEqual(after['race']['start_time'],'2026-10-31T09:01:00-04:00')
        self.assertEqual(after['race']['elapsed_seconds'],before['race']['elapsed_seconds']-60)
        self.assertEqual(self.runner()['elapsed_seconds'],before['runners'][0]['elapsed_seconds']-60)
        self.assertEqual([r['time'] for r in self.runner()['reports']],times)
        self.assertEqual(self.config['start'].hour,9)
        self.assertEqual(self.config['start'].minute,0)
    def test_seconds_compact_and_pipe_formats(self):
        log=''
        for raw,clock in [('START TIME 09:01:12','09:01:12'),('START TIME | 0902','09:02:00')]:
            with self.subTest(raw=raw):
                log+=raw+'\n'
                self.assertFalse(self.store.ingest_director(log))
                self.assertEqual(self.store.snapshot()['race']['start_time'][11:19],clock)
    def test_latest_correction_persists_across_cron_and_undo_restores_config(self):
        log='START TIME 09:01\nSTART TIME 09:02:05'
        self.store.ingest_director(log)
        revision=self.store.snapshot()['revision']
        self.store.close();self.store=Store(self.path,self.config)
        self.assertEqual(self.store.snapshot()['race']['start_time'][11:19],'09:02:05')
        self.assertFalse(self.store.ingest_director(log))
        self.assertEqual(self.store.snapshot()['revision'],revision)
        self.assertFalse(self.store.ingest_director(log+'\nUNDO START TIME'))
        self.assertEqual(self.store.snapshot()['race']['start_time'],self.config['start'].isoformat())
        self.store.close();self.store=Store(self.path,self.config)
        self.assertEqual(self.store.snapshot()['race']['start_time'],self.config['start'].isoformat())
    def test_invalid_and_commented_start_leave_previous_value(self):
        log='START TIME 09:01'
        self.store.ingest_director(log)
        for bad in ['START TIME 25:00','START TIME 24:00','START TIME 09:61','START TIME 09:00:99','START TIME tomorrow','START TIME 2026-11-01T09:00']:
            with self.subTest(bad=bad):
                self.assertTrue(self.store.ingest_director(log+'\n'+bad))
                self.assertEqual(self.store.snapshot()['race']['start_time'][11:16],'09:01')
        self.assertFalse(self.store.ingest_director(log+'\n# START TIME 09:10'))
        self.assertEqual(self.store.snapshot()['race']['start_time'][11:16],'09:01')
    def test_later_start_holds_earlier_reports_without_negative_finish_times(self):
        self.store.ingest('T001 | 09:00 | FINISH | 101 | FINISH')
        self.store.ingest_director('START TIME 09:01')
        snapshot=self.store.snapshot()
        self.assertEqual(snapshot['race']['elapsed_seconds'],0)
        self.assertEqual(self.runner()['status'],'not_reported')
        self.assertIsNone(self.runner()['elapsed_seconds'])
        self.assertIn('before the current race start',snapshot['anomalies'][0]['message'])
        self.store.ingest_director('START TIME 09:01\nUNDO START TIME')
        self.assertEqual(self.runner()['status'],'finished')
        self.assertEqual(len(self.store.audit()),3)
    def test_earlier_start_releases_pending_radio_report(self):
        radio=self.root/'radio.txt';radio.write_text('T001 | 08:59 | A | 101 | PASS')
        rd=self.root/'rd.txt';rd.write_text('')
        self.assertTrue(poll_once(self.store,'file',radio,director_log=rd))
        self.assertTrue(self.store.snapshot()['issues'])
        rd.write_text('START TIME 08:58')
        self.assertTrue(poll_once(self.store,'file',radio,director_log=rd))
        self.assertEqual(self.runner()['status'],'on_course')
        self.assertFalse(self.store.snapshot()['issues'])
    def test_live_clock_uses_corrected_start_and_waits_before_start(self):
        self.store.config['clock_mode']='live'
        self.store.ingest_director('START TIME 09:01')
        with patch('tracker.core.datetime',wraps=datetime) as clock:
            clock.now.return_value=datetime.fromisoformat('2026-10-31T09:10:00-04:00')
            self.assertEqual(self.store.snapshot()['race']['elapsed_seconds'],9*60)
            clock.now.return_value=datetime.fromisoformat('2026-10-31T09:00:30-04:00')
            self.assertEqual(self.store.snapshot()['race']['elapsed_seconds'],0)
    def test_start_command_works_before_roster_is_available(self):
        config={**self.config,'runners':{}}
        empty=Store(self.root/'empty.sqlite3',config)
        try:
            self.assertFalse(empty.ingest_director('START TIME 08:01'))
            self.assertEqual(empty.snapshot()['race']['start_time'][11:16],'08:01')
            self.assertEqual(empty.snapshot()['runners'],[])
        finally:empty.close()
    def test_published_clock_survives_missing_rd_input(self):
        rd=self.root/'rd.txt';rd.write_text('START TIME 09:01')
        radio=self.root/'radio.txt';radio.write_text('T001 | 10:00 | FINISH | 101 | FINISH')
        database=self.root/'publish.sqlite3';site=self.root/'site'
        success,first=publish(self.config,database,site,log=radio,director_log=rd)
        self.assertTrue(success);self.assertEqual(first['runners'][0]['elapsed_seconds'],59*60)
        rd.unlink()
        success,second=publish(self.config,database,site,log=radio,director_log=rd)
        self.assertFalse(success)
        self.assertEqual(second['race']['start_time'],first['race']['start_time'])
        public=json.loads((site/'state.json').read_text())
        self.assertEqual(public['race']['start_time'][11:16],'09:01')
        self.assertEqual(public['history'],[])


if __name__=='__main__':unittest.main()
