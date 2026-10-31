from datetime import datetime
from unittest.mock import patch
from pathlib import Path
import tempfile
import unittest
from tracker.core import Store,load_config
from tracker.radio import pack_rows
ROOT=Path(__file__).resolve().parents[2]
class StarterTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'state.sqlite3';self.config=load_config(ROOT/'races/moreau-test/race.json');self.store=Store(self.path,self.config)
 def tearDown(self):self.store.close();self.tmp.cleanup()
 def test_start_all_excludes_radio_and_director_dns_without_inventing_passages(self):
  self.store.ingest_director('DNS 102\nSTART ALL')
  self.store.ingest(pack_rows([{'time':'0850','message':'Bib numbers #103, #104 did not start'},{'time':'0930','message':'Checkpoint A All runners have passed at 0925'}]))
  s=self.store.snapshot();self.assertEqual(s['counts']['on_course'],3);self.assertEqual(s['counts']['dns'],3)
  self.assertTrue(all(r['last'] is None for r in s['runners']))
  self.assertEqual(len(s['progress_boundaries']),1)
  self.store.close();self.store=Store(self.path,self.config)
  self.assertEqual(self.store.snapshot()['counts'],s['counts'])
 def test_individual_start_undo_and_late_addition(self):
  self.store.ingest_director('START ALL\nADD 107 | Late Runner\nSTART 107\nUNDO START 101')
  self.assertNotIn('107',self.config['runners'])
  s=self.store.snapshot();self.assertEqual(s['counts']['on_course'],6);self.assertEqual(s['counts']['not_reported'],1)
 def test_undo_dns_overrides_radio_dns(self):
  self.store.ingest_director('START ALL\nUNDO DNS 101')
  self.store.ingest(pack_rows([{'time':'0855','message':'Bib #101 did not start'}]))
  self.assertEqual(self.store.snapshot()['runners'][0]['status'],'on_course')
 def test_race_has_to_begin_before_started_roster_is_on_course(self):
  self.store.config['clock_mode']='live';self.store.ingest_director('START ALL')
  with patch('tracker.core.datetime',wraps=datetime) as clock:
   clock.now.return_value=datetime.fromisoformat('2026-10-31T08:59:00-04:00')
   self.assertEqual(self.store.snapshot()['counts']['on_course'],0)
   clock.now.return_value=datetime.fromisoformat('2026-10-31T09:01:00-04:00')
   self.assertEqual(self.store.snapshot()['counts']['on_course'],6)
