import json
from pathlib import Path
import tempfile
import unittest
from tracker.core import Store,load_config
from tracker.radio import pack_rows

ROOT=Path(__file__).resolve().parents[2]


class BoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'test.sqlite3'
        self.config=load_config(ROOT/'races/moreau-test/race.json');self.store=Store(self.path,self.config)
    def tearDown(self):self.store.close();self.temp.cleanup()
    def ingest(self,text,clock='1030'):
        return self.store.ingest(pack_rows([{'time':clock,'message':text}]))
    def test_explicit_clearance_is_separate_from_runner_observations(self):
        self.assertFalse(self.ingest('Checkpoint B All runners have passed at 1020. Sweep passed at 1028'))
        s=self.store.snapshot();self.assertEqual(len(s['progress_boundaries']),1)
        self.assertEqual(s['progress_boundaries'][0]['time'][11:16],'10:20')
        self.assertEqual(s['progress_boundaries'][0]['kind'],'CLEARANCE')
        self.assertEqual(s['counts']['on_course'],0)
        self.assertTrue(all(not r['reports'] for r in s['runners']))
    def test_weak_or_uncertain_reports_never_clear_the_field(self):
        for message in ['Checkpoint B Last runner #101 passed at 1020',
            'Checkpoint B sweeps passed at 1020',
            'Checkpoint B All but 2 runners passed',
            'Checkpoint B have all runners passed?',
            'Checkpoint B not all runners passed',
            'Checkpoint B all runners passed except #101',
            'Checkpoint B all runners passed. No sign of bib #101']:
            with self.subTest(message=message):
                self.ingest(message)
                self.assertFalse(any(b['kind']=='CLEARANCE' for b in self.store.snapshot()['progress_boundaries']))
    def test_first_runner_with_bib_retains_its_individual_passage(self):
        self.assertFalse(self.ingest('Checkpoint B first runner Bib #101 passed at 1020'))
        s=self.store.snapshot();self.assertEqual(s['runners'][0]['last']['station'],'B')
        self.assertEqual(s['progress_boundaries'][0]['kind'],'LEADER')
    def test_gender_first_does_not_claim_overall_lead(self):
        self.ingest('Checkpoint B First female runner #101 passed at 1020')
        self.assertFalse(self.store.snapshot()['progress_boundaries'])
    def test_anonymous_first_runner_does_not_invent_a_bib(self):
        self.assertFalse(self.ingest('Checkpoint B First runner passed at 1020'))
        self.assertEqual(self.store.snapshot()['counts']['on_course'],0)
        self.assertEqual(len(self.store.snapshot()['progress_boundaries']),1)
    def test_correction_replaces_boundary_and_restart_is_idempotent(self):
        self.ingest('Checkpoint B All runners passed at 1020')
        self.ingest('Checkpoint C All runners passed at 1025')
        self.assertEqual([b['station'] for b in self.store.snapshot()['progress_boundaries']],['C'])
        revision=self.store.snapshot()['revision']
        self.store.close();self.store=Store(self.path,self.config)
        self.ingest('Checkpoint C All runners passed at 1025')
        self.assertEqual(self.store.snapshot()['revision'],revision)
    def test_incomplete_negative_or_deleted_row_suspends_inference_but_keeps_audit(self):
        message='Checkpoint B All runners passed at 1020'
        self.ingest(message)
        self.assertTrue(self.ingest('Checkpoint B Not all runners passed'))
        self.assertFalse(self.store.snapshot()['progress_boundaries'])
        self.assertEqual(len(self.store.audit()),1)
        self.ingest(message)
        self.assertEqual(len(self.store.snapshot()['progress_boundaries']),1)
        self.store.ingest(pack_rows([]))
        self.assertFalse(self.store.snapshot()['progress_boundaries'])
    def test_implausible_future_boundary_is_held(self):
        self.assertTrue(self.ingest('Checkpoint B All runners passed at 1100'))
        self.assertFalse(self.store.snapshot()['progress_boundaries'])
    def test_pre_start_boundary_is_held_after_start_correction(self):
        self.ingest('Checkpoint B All runners passed at 1020')
        self.store.ingest_director('START TIME 10:25')
        self.assertFalse(self.store.snapshot()['progress_boundaries'])


if __name__=='__main__':unittest.main()
