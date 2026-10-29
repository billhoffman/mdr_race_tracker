import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tracker.core import Store, load_config
from tracker.radio import pack_rows
from tracker.sources import html_input, document_input
from tracker.pipeline import poll_once
from tracker.publish import publish

ROOT=Path(__file__).resolve().parents[2]

class RadioTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.path=self.root/'race.sqlite3'
        self.config=load_config(ROOT/'races/moreau-test/race.json')
        self.store=Store(self.path,self.config)
    def tearDown(self):self.store.close();self.temp.cleanup()
    def ingest(self,*rows):
        return self.store.ingest(pack_rows([{'time':t,'message':m} for t,m in rows]))
    def runner(self,bib='101'):
        return next(r for r in self.store.snapshot()['runners'] if r['bib']==bib)
    def test_grouped_bibs_and_separate_explicit_times(self):
        self.assertFalse(self.ingest(('1004','Checkpoint B Runners #101 and #102 passed at 0949, #103 @0951')))
        for bib,clock in [('101','09:49'),('102','09:49'),('103','09:51')]:
            self.assertEqual(self.runner(bib)['last']['time'][11:16],clock)
        self.assertEqual(self.runner()['last']['time_basis'],'explicit passage time')
    def test_leading_time_and_unmarked_bib(self):
        self.ingest(('1000','Checkpoint A 4 runners at the same time 0955 Bib #101, 102, 103, 104'))
        self.assertEqual(self.runner('104')['last']['time'][11:16],'09:55')
        self.ingest(('1010','Checkpoint B 101 just passed the checkpoint'))
        self.assertEqual(self.runner()['last']['station'],'B')
    def test_mixed_passage_drop_and_last_known_position(self):
        self.ingest(('0910','Checkpoint A Bib #102 passing location'),
                    ('0950','Checkpoint B First female runner #101 passed location bib #102 dropped from race'))
        self.assertEqual(self.runner()['status'],'on_course')
        dropped=self.runner('102')
        self.assertEqual(dropped['status'],'withdrawn')
        self.assertIsNone(dropped['last']['station'])
        self.assertEqual(dropped['position']['station'],'A')
        self.assertEqual(dropped['distance_m'],self.config['checkpoints']['A']['distance_m'])
    def test_grouped_drops_are_separate_from_passing_runner(self):
        self.assertFalse(self.ingest(('0950','Checkpoint B Bib #101 and #102 dropped out, #103 passed at 0949')))
        self.assertEqual(self.runner()['status'],'withdrawn')
        self.assertEqual(self.runner('102')['status'],'withdrawn')
        self.assertEqual(self.runner()['last']['time'][11:16],'09:50')
        self.assertEqual(self.runner('103')['last']['time'][11:16],'09:49')
        self.assertEqual(self.runner('103')['status'],'on_course')
    def test_negated_and_future_messages_do_not_create_passages(self):
        for text in ['Checkpoint B Bib #101 did not pass',
                     'Checkpoint B Bib #101 will pass at 1000',
                     'Checkpoint B Bib #101 expected to arrive at 1000']:
            self.assertTrue(self.ingest(('1000',text)))
            self.assertIsNone(self.runner()['last'])
    def test_drop_with_unknown_or_explicit_location(self):
        self.assertFalse(self.ingest(('0930','Bib #101 dropped out of race')))
        self.assertEqual(self.runner()['status'],'withdrawn')
        self.assertIsNone(self.runner()['distance_m'])
        self.assertFalse(self.ingest(('0930','Bib #101 dropped out at checkpoint B')))
        self.assertEqual(self.runner()['last']['station'],'B')
    def test_finishes_with_and_without_hash(self):
        self.ingest(('1100','Bibs 101 and 102 finished the race'),
                    ('1105','Finish Line bib #103 finished the race at 1058 #104 at 1059'))
        self.assertEqual(self.runner('103')['place'],1)
        self.assertEqual(self.runner('104')['place'],2)
        self.assertEqual(self.runner()['status'],'finished')
    def test_routine_traffic_and_sweeps_not_runners(self):
        self.assertFalse(self.ingest(('0538','KG5JEN on station at Checkpoint A'),
            ('0930','Net control announcement on repeater'),('0950','Checkpoint B Sweep #2 passed at 0940'),
            ('0955','Checkpoint B All runners passed and sweep has passed. Cleared to secure')))
        self.assertEqual(self.store.snapshot()['revision'],0)
    def test_ambiguous_unknown_and_future_reports_are_held(self):
        for text in ['Checkpoint B All but 2 runners #101 and #102',
                     'Checkpoint B Possible duplicate #101 passed at 0942 and again at 0950',
                     'Checkpoint B correction, second runner was bib #101',
                     'Checkpoint B Bib #101 might not finish, going towards checkpoint C',
                     'Net Control to Checkpoint B, has bib #101 passed?',
                     'Checkpoint B #101 passed at 0950 and #999 at 0951',
                     'Checkpoint B #101 passed at 1005','Checkpoint X #101 passed location',
                     'Checkpoint B 3 runners remaining including #101']:
            with self.subTest(text=text):
                self.assertTrue(self.ingest(('1000',text)))
                self.assertEqual(self.store.snapshot()['revision'],0)
    def test_group_edit_replaces_all_and_bad_edit_retains(self):
        self.ingest(('0910','Checkpoint A Bib #101 and #102 passed location'))
        self.assertFalse(self.ingest(('0911','Checkpoint A Bib #103 passed location')))
        self.assertIsNone(self.runner()['last']);self.assertIsNone(self.runner('102')['last'])
        self.assertEqual(self.runner('103')['last']['time'][11:16],'09:11')
        self.assertEqual(len(self.store.audit()),4)
        self.assertTrue(self.ingest(('0911','Checkpoint A Bib #999 passed location')))
        self.assertEqual(self.runner('103')['last']['time'][11:16],'09:11')
    def test_identity_survives_restart_insert_delete_and_restore(self):
        a=('0910','Checkpoint A Bib #101 passed location');b=('0935','Checkpoint B Bib #101 passed at 0930')
        self.ingest(a,b);revision=self.store.snapshot()['revision']
        self.store.close();self.store=Store(self.path,self.config)
        self.ingest(('0900','Net control announcement on repeater'),a,b)
        self.assertEqual(self.store.snapshot()['revision'],revision)
        self.assertTrue(self.ingest(a))
        self.assertEqual(self.runner()['last']['station'],'B')
        self.assertFalse(self.ingest(a,b))
        self.assertEqual(self.store.snapshot()['revision'],revision)
        self.ingest(a,('0936','Checkpoint B Bib #103 passed at 0931'))
        self.assertEqual(self.runner()['last']['station'],'A')
        self.assertEqual(self.runner('103')['last']['station'],'B')
    def test_ambiguous_multi_row_edits_keep_confirmed_data(self):
        self.ingest(('0910','Checkpoint A #101 passed'),('0915','Checkpoint A #102 passed'))
        with self.assertRaisesRegex(ValueError,'Several radio rows'):
            self.ingest(('0911','Checkpoint A #103 passed'),('0916','Checkpoint A #104 passed'))
        self.assertEqual(self.runner()['last']['station'],'A')
        self.assertIsNone(self.runner('103')['last'])
    def test_edit_last_row_while_appending_and_simultaneous_anchored_edits(self):
        self.ingest(('0910','Checkpoint A #101 passed'),('0915','Checkpoint A #102 passed'))
        self.assertFalse(self.ingest(('0910','Checkpoint A #103 passed'),
            ('0915','Checkpoint A #104 passed'),('0920','Checkpoint B #103 passed')))
        self.assertIsNone(self.runner()['last'])
        self.assertIsNone(self.runner('102')['last'])
        self.assertEqual(self.runner('103')['last']['station'],'B')
        self.assertEqual(self.runner('104')['last']['station'],'A')
    def test_buck_mixed_drop_absence_and_request_tail(self):
        self.assertFalse(self.ingest(('1000','Checkpoint D rogers #101 dropped out, #102 arrived at 0959 #103 remains')))
        self.assertEqual(self.runner()['status'],'withdrawn')
        self.assertEqual(self.runner('102')['last']['station'],'D')
        self.assertIsNone(self.runner('103')['last'])
        self.assertFalse(self.ingest(('1010','Checkpoint E Bib #104 passed at 1009 and asking for distance to next aid station')))
        self.assertEqual(self.runner('104')['last']['time'][11:16],'10:09')
    def test_small_clock_discrepancy_preserves_time_with_warning(self):
        self.assertTrue(self.ingest(('0950','Finish Line Bib #101 finished the race at 0951')))
        self.assertEqual(self.runner()['status'],'finished')
        self.assertEqual(self.runner()['last']['time'][11:16],'09:51')
    def test_missing_and_outstanding_runners_are_not_passages(self):
        self.assertTrue(self.ingest(('1000','Net Control to Checkpoint D 43 passed and 1 still out (#101) and sweeps')))
        self.assertIsNone(self.runner()['last'])
    def test_review_does_not_modify_database(self):
        from tracker.review import review
        self.ingest(('0910','Checkpoint A #999 passed'))
        issues,health=review(self.path)
        self.assertIn('Unknown bib',issues[0]['message'])
        self.assertEqual(self.store.snapshot()['revision'],0)
    def test_private_review_issues_persist(self):
        self.ingest(('0910','Checkpoint A #999 passed'))
        self.store.close();self.store=Store(self.path,self.config)
        self.assertIn('Unknown bib',self.store.snapshot()['issues'][0]['message'])
    def test_html_multiline_cells_and_plain_export(self):
        html='<style>ignore</style><table><tr><td>TIME</td><td>MESSAGE</td></tr><tr><td>0910</td><td><p>Checkpoint A #101 passed at 0909</p><p>#102 at 0910</p></td></tr></table>'
        self.assertFalse(self.store.ingest(html_input(html)))
        self.assertEqual(self.runner()['last']['time'][11:16],'09:09')
        self.assertEqual(self.runner('102')['last']['time'][11:16],'09:10')
        text='Net Controls: Demo\nTIME\n\tMESSAGE\n0930\n\tCheckpoint B Bib #101 passed at 0929\n'
        self.assertFalse(self.store.ingest(text))
        self.assertEqual(self.runner()['last']['station'],'B')
        self.store.ingest(html_input('<p>T001 | 09:45 | C | 101 | PASS</p>'))
        self.assertEqual(self.runner()['last']['station'],'C')
    def test_oauth_table_cells(self):
        p=lambda t:{'paragraph':{'elements':[{'textRun':{'content':t+'\n'}}]}}
        cells=lambda a,b:{'tableCells':[{'content':[p(a)]},{'content':[p(b)]}]}
        doc={'tabs':[{'documentTab':{'body':{'content':[{'table':{'tableRows':[cells('TIME','MESSAGE'),cells('0910','Checkpoint A #101 passed')]}}]}}}]}
        self.assertFalse(self.store.ingest(document_input(doc)))
        self.assertEqual(self.runner()['last']['station'],'A')
    def test_fictional_radio_script(self):
        self.assertFalse(self.store.ingest((ROOT/'races/moreau-test/radio-log.txt').read_text()))
        self.assertEqual(self.store.snapshot()['counts'],{'finished':5,'withdrawn':1,'on_course':0,'not_reported':0,'dns':0})
        self.assertFalse(self.store.snapshot()['anomalies'])
        revision=self.store.snapshot()['revision']
        self.store.ingest((ROOT/'races/moreau-test/radio-log.txt').read_text())
        self.assertEqual(self.store.snapshot()['revision'],revision)
    def test_google_poll_and_static_publish(self):
        html='<table><tr><td>TIME</td><td>MESSAGE</td></tr><tr><td>0910</td><td>Checkpoint A #101 passed</td></tr></table>'
        with patch('tracker.sources.request_text',return_value=html) as request:
            self.assertTrue(poll_once(self.store,'google',doc_id='example'))
            self.assertIn('format=html',request.call_args.args[0])
        log=self.root/'radio.txt';log.write_text(html_input(html))
        success,state=publish(self.config,self.root/'publish.sqlite3',self.root/'site',log=log)
        self.assertTrue(success);self.assertEqual(state['counts']['on_course'],1)
        public=json.loads((self.root/'site/state.json').read_text())
        self.assertEqual(public['issues'],[])
        self.assertNotIn('Checkpoint A #101',(self.root/'site/state.json').read_text())

if __name__=='__main__':unittest.main()
