from datetime import datetime,timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tracker.core import Store,load_config
from tracker.pipeline import poll_once
from tracker.publish import publish
from tracker.sweepers import feed_url,latest_position,locate_on_course,poll,public_state

ROOT=Path(__file__).resolve().parents[2]
NOW=datetime.fromisoformat('2026-10-31T14:00:00+00:00')
ROUTE={'coordinates':[[-73,43,100],[-72.99,43,200]],'distance_m':[0,813],'length_m':813}


def mark(stamp='2026-10-31T13:55:00Z',lon=-72.995,lat=43,valid='True',device='private-imei',extra=''):
    return f'''<Placemark><TimeStamp><when>{stamp}</when></TimeStamp><ExtendedData>
    <Data name="Valid GPS Fix"><value>{valid}</value></Data>
    <Data name="IMEI"><value>{device}</value></Data>
    <Data name="Text"><value>private-message</value></Data>
    <Data name="Name"><value>private-name</value></Data></ExtendedData>
    {extra}<Point><coordinates>{lon},{lat},100</coordinates></Point></Placemark>'''


def kml(*marks):return ('<kml xmlns="http://www.opengis.net/kml/2.2"><Document>'+''.join(marks)+'</Document></kml>').encode()


class SweeperTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.config=load_config(ROOT/'races/moreau-test/race.json')
        self.config['course']['route']=ROUTE
        self.path=self.root/'state.sqlite3';self.store=Store(self.path,self.config)
    def tearDown(self):self.store.close();self.temp.cleanup()
    def file(self,data):
        path=self.root/'gps.kml';path.write_bytes(data);return path
    def test_public_mapshare_url_becomes_feed_and_rejects_other_hosts(self):
        self.assertEqual(feed_url('https://share.garmin.com/4YNCH'),'https://share.garmin.com/Feed/Share/4YNCH')
        self.assertEqual(feed_url('https://share.garmin.com/Feed/Share/4YNCH'),feed_url('https://share.garmin.com/4YNCH'))
        for bad in ['http://share.garmin.com/a','https://example.com/a','https://share.garmin.com:443/a','https://x@y/a']:
            with self.subTest(bad=bad),self.assertRaises(ValueError):feed_url(bad)
    def test_latest_point_selected_by_gps_time_without_importing_private_fields(self):
        p=latest_position(kml(mark(),mark('2026-10-31T13:50:00Z')),'2026-10-31','America/New_York',NOW)
        self.assertEqual(p['time'],'2026-10-31T13:55:00+00:00')
        self.assertEqual(set(p),{'longitude','latitude','time'})
    def test_filters_wrong_day_invalid_future_fix_and_waypoint(self):
        for m in [mark('2026-10-30T13:55:00Z'),mark('2026-10-31T14:10:00Z'),mark(valid='False'),mark(lon='nan'),mark(lat=100),mark(extra='<styleUrl>#waypointstyle_123</styleUrl>')]:
            with self.subTest(mark=m):self.assertIsNone(latest_position(kml(m),'2026-10-31','America/New_York',NOW))
    def test_race_day_filter_uses_local_date_not_utc_date(self):
        self.assertIsNone(latest_position(kml(mark('2026-10-31T02:00:00Z')),'2026-10-31','America/New_York',NOW))
    def test_empty_feed_is_valid_but_html_and_multiple_devices_are_not(self):
        self.assertIsNone(latest_position(kml(),'2026-10-31','America/New_York',NOW))
        for data in [b'<html>Sign in</html>',b'not xml',kml(mark(device='one'),mark(device='two'))]:
            with self.subTest(data=data),self.assertRaises(ValueError):latest_position(data,'2026-10-31','America/New_York',NOW)
    def test_actual_gps_is_not_snapped_and_course_distance_is_approximate(self):
        position={'longitude':-72.995,'latitude':43.0001,'time':NOW.isoformat()}
        result=locate_on_course(position,ROUTE)
        self.assertEqual(result['latitude'],43.0001)
        self.assertTrue(result['on_course'])
        self.assertAlmostEqual(result['offset_m'],11.1,delta=.2)
        self.assertAlmostEqual(result['distance_m'],406.5,delta=1)
    def test_course_crossing_leaves_profile_distance_unknown(self):
        route={'coordinates':[[-73,43],[-72.99,43],[-73,43]],'distance_m':[0,813,1626]}
        result=locate_on_course({'longitude':-73,'latitude':43},route)
        self.assertTrue(result['course_distance_ambiguous'])
        self.assertIsNone(result['distance_m'])
    def test_off_course_coordinates_never_appear_in_public_state(self):
        path=self.file(kml(mark(lon=-74)))
        self.assertTrue(poll(self.store,kml_file=path,now=NOW))
        public=self.store.snapshot()['sweeper']
        self.assertTrue(public['off_course']);self.assertIsNone(public['position'])
        self.assertNotIn('longitude',json.dumps(public))
    def test_failure_and_restart_keep_same_gps_time_and_location(self):
        path=self.file(kml(mark()))
        self.assertTrue(poll(self.store,kml_file=path,now=NOW))
        initial=self.store.snapshot()['sweeper']['position']
        self.store.close();self.store=Store(self.path,self.config)
        path.unlink()
        self.assertFalse(poll(self.store,kml_file=path,now=NOW))
        self.assertEqual(self.store.snapshot()['sweeper']['position'],initial)
        self.assertTrue(self.store.snapshot()['sweeper']['error'])
    def test_empty_or_older_feed_does_not_advance_last_position(self):
        path=self.file(kml(mark()))
        poll(self.store,kml_file=path,now=NOW)
        initial=self.store.snapshot()['sweeper']['position']
        for data in [kml(),kml(mark('2026-10-31T13:30:00Z'))]:
            path.write_bytes(data);poll(self.store,kml_file=path,now=NOW)
            self.assertEqual(self.store.snapshot()['sweeper']['position'],initial)
    def test_before_race_day_reports_are_hidden(self):
        path=self.file(kml(mark('2026-10-29T13:55:00Z')))
        self.assertTrue(poll(self.store,kml_file=path,now=NOW))
        self.assertIsNone(self.store.snapshot()['sweeper'].get('position'))
    def test_failed_garmin_does_not_block_radio_or_director(self):
        radio=self.root/'radio.txt';radio.write_text('T001 | 09:10 | A | 101 | PASS')
        rd=self.root/'rd.txt';rd.write_text('DNS 102')
        self.assertFalse(poll_once(self.store,'file',radio,director_log=rd,sweeper_kml=self.root/'missing.kml'))
        s=self.store.snapshot()
        self.assertEqual(s['counts']['on_course'],1);self.assertEqual(s['counts']['dns'],1)
        self.assertIsNone(s['source']['error']);self.assertTrue(s['sweeper']['error'])
    def test_disabling_sweeper_setting_hides_marker(self):
        path=self.file(kml(mark()));poll(self.store,kml_file=path,now=NOW)
        radio=self.root/'radio.txt';radio.write_text('')
        poll_once(self.store,'file',radio)
        self.assertEqual(self.store.snapshot()['sweeper'],{'enabled':False})
    def test_static_publish_has_no_messages_ids_or_file_paths(self):
        path=self.file(kml(mark()));radio=self.root/'radio.txt';radio.write_text('')
        site=self.root/'site'
        with patch('tracker.sweepers.datetime',wraps=datetime) as clock:
            clock.now.return_value=NOW
            success,state=publish(self.config,self.root/'publish.sqlite3',site,log=radio,sweeper_kml=path)
        self.assertTrue(success);self.assertEqual(state['counts']['on_course'],0)
        public=(site/'state.json').read_text()
        for private in ['private-message','private-name','private-imei',str(path),'feed_key']:
            self.assertNotIn(private,public)
        self.assertTrue(json.loads(public)['sweeper']['position']['on_course'])


if __name__=='__main__':unittest.main()
