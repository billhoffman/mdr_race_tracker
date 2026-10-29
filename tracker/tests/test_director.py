import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tracker.core import Store,load_config
from tracker.pipeline import poll_once
from tracker.publish import publish
from tracker.radio import pack_rows
from tracker.server import public_snapshot
from tracker.sources import html_input

ROOT=Path(__file__).resolve().parents[2]


class DirectorTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.config=load_config(ROOT/'races/moreau-test/race.json')
        self.path=self.root/'race.sqlite3';self.store=Store(self.path,self.config)
    def tearDown(self):self.store.close();self.temp.cleanup()
    def runner(self,bib='101'):
        return next(r for r in self.store.snapshot()['runners'] if r['bib']==bib)
    def reopen(self):
        self.store.close();self.store=Store(self.path,self.config)
    def radio(self,message='Checkpoint A Bib #107 passed at 0910',clock='0911'):
        return pack_rows([{'time':clock,'message':message}])
    def test_add_runner_persists_without_mutating_base_roster(self):
        self.assertFalse(self.store.ingest_director('ADD 107 | Late Runner'))
        self.assertEqual(self.runner('107')['status'],'not_reported')
        self.assertNotIn('107',self.config['runners'])
        self.reopen()
        self.assertEqual(self.runner('107')['name'],'Late Runner')
        self.assertFalse(self.store.ingest_director('ADD 107 | Late Runner'))
        self.assertEqual(self.store.snapshot()['revision'],1)
    def test_addition_releases_pending_radio_on_next_poll(self):
        radio=self.root/'radio.txt';radio.write_text(self.radio())
        rd=self.root/'rd.txt';rd.write_text('')
        self.assertTrue(poll_once(self.store,'file',radio,director_log=rd))
        self.assertTrue(self.store.snapshot()['issues'])
        rd.write_text('ADD 107 | Late Runner')
        self.assertTrue(poll_once(self.store,'file',radio,director_log=rd))
        self.assertEqual(self.runner('107')['last']['station'],'A')
        self.assertFalse(self.store.snapshot()['issues'])
    def test_dns_undo_and_repeated_dns_command(self):
        self.store.ingest('T001 | 09:10 | A | 101 | PASS')
        log='DNS 101';self.store.ingest_director(log)
        self.assertEqual(self.runner()['status'],'dns')
        self.assertIsNone(self.runner()['distance_m'])
        self.assertEqual(self.store.snapshot()['counts']['dns'],1)
        self.assertTrue(self.store.snapshot()['anomalies'])
        log+='\nUNDO DNS 101';self.store.ingest_director(log)
        self.assertEqual(self.runner()['status'],'on_course')
        log+='\nDNS 101';self.store.ingest_director(log)
        self.assertEqual(self.runner()['status'],'dns')
        self.reopen();self.assertEqual(self.runner()['status'],'dns')
    def test_director_pass_correction_and_undo_reveal_radio(self):
        self.store.ingest('T001 | 09:10 | A | 101,102 | PASS')
        log='PASS 101 | A | 09:12';self.store.ingest_director(log)
        self.assertEqual(self.runner()['last']['time'][11:16],'09:12')
        self.assertEqual(self.runner('102')['last']['time'][11:16],'09:10')
        self.assertEqual(len(self.runner()['reports']),1)
        self.assertTrue(self.store.snapshot()['anomalies'])
        log+='\nPASS 101 | A | 09:13';self.store.ingest_director(log)
        self.assertEqual(self.runner()['last']['time'][11:16],'09:13')
        log+='\nUNDO PASS 101 | A';self.store.ingest_director(log)
        self.assertEqual(self.runner()['last']['time'][11:16],'09:10')
    def test_director_finish_wins_over_radio_terminal_and_recomputes_place(self):
        self.store.ingest('T001 | 09:10 | A | 101 | WITHDRAWN\nT002 | 11:00 | FINISH | 102 | FINISH')
        log='FINISH 101 | 10:59:12';self.store.ingest_director(log)
        self.assertEqual(self.runner()['status'],'finished')
        self.assertEqual(self.runner()['place'],1)
        self.assertEqual(self.runner('102')['place'],2)
        log+='\nFINISH 101 | 11:01';self.store.ingest_director(log)
        self.assertEqual(self.runner()['place'],2)
        self.assertEqual(self.runner()['last']['time'][11:16],'11:01')
        log+='\nUNDO FINISH 101';self.store.ingest_director(log)
        self.assertEqual(self.runner()['status'],'withdrawn')
    def test_withdrawal_without_or_with_location_and_undo(self):
        self.store.ingest('T001 | 09:10 | A | 101 | PASS')
        log='WITHDRAW 101 | 09:20';self.store.ingest_director(log)
        self.assertEqual(self.runner()['status'],'withdrawn')
        self.assertEqual(self.runner()['position']['station'],'A')
        log+='\nWITHDRAW 101 | B | 09:25';self.store.ingest_director(log)
        self.assertEqual(self.runner()['position']['station'],'B')
        log+='\nUNDO WITHDRAW 101';self.store.ingest_director(log)
        self.assertEqual(self.runner()['status'],'on_course')
    def test_director_withdrawal_is_honored_even_after_backtracking(self):
        self.store.ingest('T001 | 09:10 | B | 101 | PASS')
        self.store.ingest_director('WITHDRAW 101 | A | 09:20')
        self.assertEqual(self.runner()['status'],'withdrawn')
        self.assertEqual(self.runner()['position']['station'],'A')
        self.assertTrue(self.store.snapshot()['anomalies'])
    def test_deleted_commands_retained_and_invalid_commands_do_not_apply(self):
        self.store.ingest_director('DNS 101')
        self.assertTrue(self.store.ingest_director(''))
        self.assertEqual(self.runner()['status'],'dns')
        self.assertTrue(self.store.ingest_director('DNS 999\nPASS 102 | X | 10:00\nFINISH 102 | 08:00\nADD 101 | Wrong Person'))
        self.assertEqual(self.runner()['name'],'Alex Demo')
        self.assertEqual(self.runner('102')['status'],'not_reported')
    def test_comments_headings_invalid_times_and_partial_commands(self):
        self.assertFalse(self.store.ingest_director('# notes\nRace Director Log\n'))
        for raw in ['ADD 107 |','DNS','DNS 101 | extra','PASS 101 | A | 25:00','UNDO PASS 101 | X']:
            with self.subTest(raw=raw):self.assertTrue(self.store.ingest_director(raw))
        self.assertEqual(self.store.snapshot()['revision'],0)
    def test_independent_health_and_persisted_commands_on_source_failures(self):
        rd=self.root/'rd.txt';rd.write_text('DNS 101')
        radio=self.root/'radio.txt';radio.write_text('T001 | 09:10 | A | 102 | PASS')
        self.assertTrue(poll_once(self.store,'file',radio,director_log=rd))
        rd.unlink();radio.write_text('T002 | 09:30 | B | 102 | PASS')
        self.assertFalse(poll_once(self.store,'file',radio,director_log=rd))
        self.assertEqual(self.runner('102')['last']['station'],'B')
        self.assertEqual(self.runner()['status'],'dns')
        self.assertIsNone(self.store.health['error'])
        self.assertTrue(self.store.health['director']['error'])
        radio.unlink();rd.write_text('DNS 101\nADD 107 | New Runner')
        self.assertFalse(poll_once(self.store,'file',radio,director_log=rd))
        self.assertEqual(self.runner('107')['name'],'New Runner')
        self.assertIsNone(self.store.health['director']['error'])
        self.assertTrue(self.store.health['error'])
    def test_upgrade_keeps_legacy_radio_issues_when_rd_is_read_first(self):
        legacy=[{'line':1,'text':'old radio report','message':'Unknown bib'}]
        with self.store.db:
            self.store.db.execute("DELETE FROM meta WHERE key LIKE 'issues:%'")
            self.store.db.execute("INSERT OR REPLACE INTO meta VALUES('input_issues',?)",(json.dumps(legacy),))
        self.reopen()
        self.store.ingest_director('')
        self.assertEqual(self.store.snapshot()['issues'][0]['text'],'old radio report')
    def test_radio_and_director_review_issues_do_not_overwrite_each_other(self):
        self.store.ingest_director('DNS 999')
        self.store.ingest(self.radio())
        issues=self.store.snapshot()['issues']
        self.assertEqual({i['source'] for i in issues},{'primary-log','director-log'})
        self.reopen();self.assertEqual(len(self.store.snapshot()['issues']),2)
    def test_public_view_hides_private_rd_errors_and_commands(self):
        self.store.ingest_director('ADD 107 | Late Runner\nDNS 101\nFINISH 107 | 11:00')
        self.store.set_health(director={'error':'private /secret/path detail'})
        private=self.store.snapshot();before=copy.deepcopy(private)
        public=public_snapshot(private)
        self.assertEqual(private,before)
        self.assertEqual(public['history'],[])
        self.assertNotIn('/secret/path',json.dumps(public))
        self.assertNotIn('ADD 107',json.dumps(public))
        self.assertEqual(next(r for r in public['runners'] if r['bib']=='107')['status'],'finished')
    def test_two_google_docs_and_cron_publisher(self):
        radio=self.root/'radio.txt';radio.write_text(self.radio())
        director=self.root/'rd.txt';director.write_text('ADD 107 | Late Runner\nDNS 101')
        database=self.root/'publish.sqlite3';site=self.root/'site'
        success,state=publish(self.config,database,site,log=radio,director_log=director)
        self.assertTrue(success)
        self.assertEqual(state['counts']['dns'],1)
        self.assertEqual(state['counts']['on_course'],1)
        success,again=publish(self.config,database,site,log=radio,director_log=director)
        self.assertTrue(success);self.assertEqual(state['revision'],again['revision'])
        with patch('tracker.pipeline.read_google',side_effect=lambda doc,token:'ADD 107 | Late Runner' if doc=='rd' else self.radio()):
            self.assertTrue(poll_once(self.store,'google',doc_id='radio',director_doc_id='rd'))
        self.assertEqual(self.runner('107')['last']['station'],'A')
    def test_empty_export_is_valid_but_login_page_is_not(self):
        self.assertEqual(html_input('<html><head><style>p{}</style></head><body><p></p></body></html>').strip(),'')
        with self.assertRaises(ValueError):html_input('<html><body><a href="https://accounts.google.com/ServiceLogin">Sign in</a></body></html>')


if __name__=='__main__':unittest.main()
