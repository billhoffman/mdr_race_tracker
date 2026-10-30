"""Replay the original Buck radio table through the production ingestion code.

This is a message-ingestion regression, not a Buck course/visit reconstruction.
Expected finishes come from radio messages, never from official finish times.
"""
from datetime import datetime
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tracker.core import Store
from tracker.pipeline import poll_once
from tracker.radio import input_rows, pack_rows
from tracker.sources import html_input

FIXTURE=Path(__file__).parent/'fixtures/buck50'
EXPECTED=json.loads((FIXTURE/'expected.json').read_text())
HTML=(FIXTURE/'radio-log.html').read_text()


def buck_config():
    return {'race_id':'buck50-radio-regression','name':'Buck 50 radio regression',
        'test_mode':True,'date':EXPECTED['race_date'],'timezone':'America/New_York',
        'start':datetime.fromisoformat(EXPECTED['start_time']),'clock_mode':'latest_report',
        'runners':{bib:{'bib':bib,'name':'Bib '+bib} for bib in EXPECTED['roster_bibs']},
        'checkpoints':{station:{'distance_m':distance} for station,distance in EXPECTED['first_visit_distance_m'].items()},
        'course':{'route':{'length_m':EXPECTED['route_length_m']}}}


class Buck50RegressionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.database=Path(self.temp.name)/'buck50.sqlite3'
        self.store=Store(self.database,buck_config())
        self.text=html_input(HTML)
        self.rows=input_rows(self.text)
    def tearDown(self):
        self.store.close();self.temp.cleanup()
    def events(self):
        return [json.loads(row['payload']) for row in self.store.audit()
                if not json.loads(row['payload']).get('void') and json.loads(row['payload']).get('kind') in {'PASS','FINISH','WITHDRAWN'}]
    def ingest(self):self.store.ingest(self.text)
    def find(self,bib,station,report_time,kind='PASS'):
        return [event for event in self.events() if bib in event['bibs']
                and event['station']==station and event['report_time']==report_time and event['kind']==kind]
    def test_entire_original_table_through_google_poll(self):
        with patch('tracker.sources.request_text',return_value=HTML) as request:
            self.assertTrue(poll_once(self.store,'google',doc_id='offline-buck-fixture'))
        self.assertTrue(request.call_args.args[0].endswith('/export?format=html'))
        self.assertEqual(sum(bool(row['time'].strip()) for row in self.rows),EXPECTED['populated_table_rows'])
        self.assertEqual(len(self.events()),EXPECTED['accepted_observations'])
        finish_bibs={bib for event in self.events() if event['kind']=='FINISH' for bib in event['bibs']}
        drop_bibs={bib for event in self.events() if event['kind']=='WITHDRAWN' for bib in event['bibs']}
        self.assertEqual(finish_bibs,set(EXPECTED['radio_finish_bibs']))
        self.assertEqual(drop_bibs,set(EXPECTED['withdrawal_bibs']))
        self.assertNotIn(EXPECTED['missing_radio_finish_bib'],finish_bibs)
        for bib,clock in EXPECTED['selected_finishes'].items():
            events=[e for e in self.events() if e['kind']=='FINISH' and bib in e['bibs']]
            self.assertEqual([e['time'][11:16] for e in events],[clock])
    def test_delayed_grouped_and_multiline_passage_times(self):
        self.ingest()
        for expected in EXPECTED['selected_passages']:
            with self.subTest(expected=expected):
                events=self.find(expected['bib'],expected['station'],expected['report_time'])
                self.assertEqual(len(events),1)
                self.assertEqual(events[0]['time'][11:16],expected['time'])
        # TIME 0949 mixes #41 passing and #16 withdrawing: they must not swap roles.
        self.assertEqual(len(self.find('41','H','09:49')),1)
        self.assertFalse(self.find('16','H','09:49'))
        self.assertEqual(len(self.find('16',None,'09:49','WITHDRAWN')),1)
    def test_all_four_drops_without_inventing_locations(self):
        self.ingest()
        for bib,clock in EXPECTED['withdrawal_report_times'].items():
            with self.subTest(bib=bib):
                events=self.find(bib,None,clock,'WITHDRAWN')
                self.assertEqual(len(events),1)
                self.assertEqual(events[0]['time'][11:16],clock)
        # #29's drop broadcast is mixed with #57's arrival and #26 remaining.
        self.assertFalse(self.find('29','D','15:52'))
        self.assertFalse(self.find('26','D','15:52'))
        self.assertEqual(len(self.find('57','D','15:52')),1)
    def test_unknowns_corrections_and_outstanding_bibs_are_held(self):
        self.ingest()
        issues=self.store.snapshot()['issues']
        checks=[('0640','Unknown bib'),('0933','correction'),('1046','uncertain'),
                ('1143','Unknown bib'),('1209','Same bib'),('1536','uncertain')]
        for clock,message in checks:
            with self.subTest(clock=clock):
                self.assertTrue(any(i['text'].startswith(clock+' |') and message.lower() in i['message'].lower() for i in issues))
        self.assertFalse(self.find('31','K','12:09'))
        self.assertFalse(self.find('29','L','15:36'))
        self.assertFalse(self.find('26','A','18:32'))
        self.assertEqual(len(self.find('57','A','18:32')),1)
        self.assertFalse(any(bib in {'1','87'} for event in self.events() for bib in event['bibs']))
    def test_replay_row_by_row_repoll_and_restart(self):
        # Simulate a live document growing during the day, including blank rows.
        for end in range(1,len(self.rows)+1):
            self.store.ingest(pack_rows(self.rows[:end]))
        events=self.events()
        self.assertEqual(len(events),EXPECTED['accepted_observations'])
        self.store.close();self.store=Store(self.database,buck_config())
        self.ingest();self.ingest()
        self.assertEqual(self.events(),events)
        revision=len(self.store.audit());self.ingest()
        self.assertEqual(len(self.store.audit()),revision)
    def test_actual_all_passed_report_provides_a_separate_display_boundary(self):
        self.ingest()
        boundaries=self.store.snapshot()['progress_boundaries']
        cleared=[b for b in boundaries if b['kind']=='CLEARANCE' and b['station']=='G']
        self.assertEqual(len(cleared),1)
        self.assertEqual(cleared[0]['time'][11:16],'11:01')
        self.assertFalse(any(b['kind']=='CLEARANCE' and b['station'] in {'H','I','J'} for b in boundaries))
        self.assertEqual(len(self.events()),EXPECTED['accepted_observations'])
    def test_confirmed_summary_preserves_radio_gap_and_drops(self):
        self.ingest()
        snapshot=self.store.snapshot()
        self.assertEqual(snapshot['counts'],{'finished':42,'withdrawn':4,'on_course':1,'not_reported':0,'dns':0})
        runners={r['bib']:r for r in snapshot['runners']}
        self.assertEqual(runners['47']['status'],'on_course')
        self.assertEqual(runners['12']['place'],1)
        self.assertEqual(runners['26']['place'],42)
        self.assertEqual({b for b,r in runners.items() if r['status']=='withdrawn'},set(EXPECTED['withdrawal_bibs']))
        # A first-visit-only course cannot represent Buck's return leg. Keep that
        # limitation visible: the fixture must not hide it or assert return positions.
        self.assertTrue(any('behind a prior' in a['message'] for a in snapshot['anomalies']))
    def test_no_future_results_before_radio_reports_arrive(self):
        populated=[r for r in self.rows if r['time'].strip()]
        first_finish=next(i for i,r in enumerate(populated) if r['time']=='1303' and 'finished the race' in r['message'])
        self.store.ingest(pack_rows(populated[:first_finish]))
        self.assertFalse(any(e['kind']=='FINISH' for e in self.events()))
        early_drops={bib for e in self.events() if e['kind']=='WITHDRAWN' for bib in e['bibs']}
        self.assertEqual(early_drops,{'16','28','55'})
        self.store.ingest(pack_rows(populated[:first_finish+1]))
        self.assertEqual([e['bibs'] for e in self.events() if e['kind']=='FINISH'],[['12']])
    def test_edit_real_grouped_row_replaces_group_without_duplicates(self):
        rows=[dict(r) for r in self.rows]
        self.store.ingest(pack_rows(rows))
        index=next(i for i,r in enumerate(rows) if r['time']=='1158')
        self.assertIn('Bib #52, 54, 19, 15',rows[index]['message'])
        rows[index]['message']=rows[index]['message'].replace('Bib #52, 54, 19, 15','Bib #52, 54, 19')
        self.store.ingest(pack_rows(rows))
        active=[json.loads(r['payload']) for r in self.store.db.execute('SELECT payload FROM entries WHERE active=1')]
        grouped=[e for e in active if e['station']=='K' and e['report_time']=='11:58']
        self.assertEqual({b for e in grouped for b in e['bibs']},{'52','54','19'})
        self.assertTrue(any(json.loads(r['payload']).get('void') for r in self.store.audit()))
        revision=len(self.store.audit());self.store.ingest(pack_rows(rows))
        self.assertEqual(len(self.store.audit()),revision)


if __name__=='__main__':unittest.main()
