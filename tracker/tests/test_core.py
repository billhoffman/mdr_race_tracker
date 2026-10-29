import json
from pathlib import Path
import tempfile
import unittest

from tracker.core import Store, load_config, parse_line
from tracker.sources import document_text

ROOT = Path(__file__).resolve().parents[2]


class TrackerTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config(ROOT/'races/moreau-test/race.json')
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)/'test.sqlite3'
        self.store = Store(self.path,self.config)
    def tearDown(self):
        self.store.close()
        self.temp.cleanup()
    def runner(self,bib='101'):
        return next(r for r in self.store.snapshot()['runners'] if r['bib']==bib)
    def test_repoll_is_idempotent_and_persists(self):
        log='T001 | 09:10 | A | 101 | PASS'
        self.store.ingest(log)
        self.store.ingest(log)
        self.assertEqual(self.store.snapshot()['revision'],1)
        self.store.close()
        self.store=Store(self.path,self.config)
        self.assertEqual(self.runner()['last']['station'],'A')
    def test_correction_changes_runner_without_losing_history(self):
        self.store.ingest('T001 | 09:10 | A | 101 | PASS')
        self.store.ingest('T001 | 09:11 | A | 103 | PASS')
        self.assertIsNone(self.runner()['last'])
        self.assertEqual(self.runner('103')['last']['time'][11:16],'09:11')
        self.assertEqual(len(self.store.audit()),2)
    def test_invalid_correction_retains_previous_valid_entry(self):
        self.store.ingest('T001 | 09:10 | A | 101 | PASS')
        issues=self.store.ingest('T001 | 09:11 | A | 999 | PASS')
        self.assertEqual(len(issues),1)
        self.assertEqual(self.runner()['last']['time'][11:16],'09:10')
    def test_deleted_line_retained_but_void_retracts(self):
        self.store.ingest('T001 | 09:10 | A | 101 | PASS')
        self.store.ingest('')
        self.assertEqual(self.runner()['last']['station'],'A')
        self.store.ingest('T001 | VOID')
        self.assertIsNone(self.runner()['last'])
    def test_late_reports_sorted_by_event_time(self):
        self.store.ingest('T002 | 09:35 | B | 101 | PASS\nT001 | 09:10 | A | 101 | PASS')
        self.assertEqual(self.runner()['last']['station'],'B')
        self.assertEqual(self.store.snapshot()['race']['elapsed_seconds'],35*60)
    def test_duplicate_id_not_applied(self):
        self.store.ingest('T001 | 09:10 | A | 101 | PASS\nT001 | 09:12 | A | 103 | PASS')
        self.assertIsNone(self.runner()['last'])
        self.assertEqual(self.store.snapshot()['revision'],0)
    def test_backwards_passage_flagged_and_not_displayed(self):
        self.store.ingest('T001 | 09:20 | B | 101 | PASS\nT002 | 09:30 | A | 101 | PASS')
        self.assertEqual(self.runner()['last']['station'],'B')
        self.assertEqual(len(self.store.snapshot()['anomalies']),1)
    def test_withdrawal_blocks_later_passage_until_corrected(self):
        self.store.ingest('T001 | 09:10 | A | 101 | WITHDRAWN\nT002 | 09:30 | B | 101 | PASS')
        self.assertEqual(self.runner()['status'],'withdrawn')
        self.assertEqual(len(self.store.snapshot()['anomalies']),1)
        self.store.ingest('T001 | VOID')
        self.assertEqual(self.runner()['status'],'on_course')
        self.assertEqual(self.runner()['last']['station'],'B')
    def test_finish_place_recomputed_after_correction(self):
        self.store.ingest('T001 | 12:00 | FINISH | 101 | FINISH\nT002 | 11:55 | FINISH | 103 | FINISH')
        self.assertEqual(self.runner('103')['place'],1)
        self.assertEqual(self.runner()['place'],2)
        self.store.ingest('T002 | 12:05 | FINISH | 103 | FINISH')
        self.assertEqual(self.runner()['place'],1)
    def test_validation_and_multi_bib(self):
        event=parse_line('T001 | 09:12 | A | 101,103 | PASS',self.config)
        self.assertEqual(event['bibs'],['101','103'])
        for line in ['T001 | 25:00 | A | 101 | PASS','T001 | 08:59 | A | 101 | PASS',
                     'T001 | 09:10 | X | 101 | PASS','T001 | 09:10 | FINISH | 101 | PASS']:
            with self.assertRaises(ValueError):parse_line(line,self.config)
    def test_google_tabs_and_tables(self):
        paragraph=lambda text:{'paragraph':{'elements':[{'textRun':{'content':text}}]}}
        doc={'tabs':[{'documentTab':{'body':{'content':[paragraph('first\n')]}},'childTabs':[
            {'documentTab':{'body':{'content':[{'table':{'tableRows':[{'tableCells':[{'content':[paragraph('second\n')]}]}]}}]}}}]}]}
        self.assertEqual(document_text(doc),'first\n\nsecond\n')
    def test_fictional_script_end_to_end(self):
        # Replay actual typing instructions including the explicit correction steps.
        import re
        script=(ROOT/'races/moreau-test/test-script.md').read_text()
        reports={}
        for block in re.findall(r'```text\n(.*?)```',script,re.S):
            for line in block.strip().splitlines():reports[line.split('|')[0].strip()]=line
            self.store.ingest('\n'.join(reports.values()))
        self.assertEqual(self.store.snapshot()['counts'],{'finished':5,'withdrawn':1,'on_course':0,'not_reported':0,'dns':0})
        self.assertEqual(self.store.snapshot()['race']['elapsed_seconds'],4*3600+20*60)
        self.assertFalse(self.store.snapshot()['issues'])
        self.assertFalse(self.store.snapshot()['anomalies'])


if __name__=='__main__':
    unittest.main()
