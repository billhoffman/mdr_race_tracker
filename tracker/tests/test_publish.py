import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tracker.core import load_config
from tracker.publish import atomic_write, check_destination, publish, publisher_lock

ROOT=Path(__file__).resolve().parents[2]


class PublisherTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.web=self.root/'public/mdr/moreau'
        self.database=self.root/'private/state.sqlite3'
        self.log=self.root/'log.txt'
        self.log.write_text('T001 | 09:10 | A | 101 | PASS\n')
        self.config=load_config(ROOT/'races/moreau-test/race.json')
    def tearDown(self):
        self.temp.cleanup()
    def run_publish(self):
        return publish(self.config,self.database,self.web,'file',self.log)
    def state(self):
        return json.loads((self.web/'state.json').read_text())
    def test_subfolder_site_contains_relative_assets_and_public_only_state(self):
        success,_=self.run_publish()
        self.assertTrue(success)
        state=self.state()
        self.assertTrue(state['public_view'])
        self.assertEqual(state['history'],[])
        self.assertEqual(state['issues'],[])
        self.assertTrue((self.web/state['course_url']).exists())
        self.assertEqual(state['source']['expected_interval_seconds'],60)
        html=(self.web/'index.html').read_text()
        self.assertIn('stateUrl:"./state.json"',html)
        self.assertNotIn('src="/',html)
        self.assertNotIn('href="/api/audit"',html)
        self.assertNotIn('href="/style.css"',html)
        self.assertNotIn('src="/course-geometry.js"',html)
        self.assertEqual(len(list(self.web.glob('course-geometry-*.js'))),1)
        self.assertTrue((self.web/'.htaccess').exists())
        self.assertFalse(any(p.suffix in {'.sqlite3','.db','.txt'} for p in self.web.iterdir()))
    def test_separate_runs_are_idempotent_and_corrections_persist(self):
        self.run_publish()
        self.run_publish()
        self.assertEqual(self.state()['revision'],1)
        self.log.write_text('T001 | 09:11 | A | 103 | PASS')
        self.run_publish()
        state=self.state()
        self.assertEqual(state['revision'],2)
        runners={r['bib']:r for r in state['runners']}
        self.assertIsNone(runners['101']['last'])
        self.assertEqual(runners['103']['last']['time'][11:16],'09:11')
    def test_failure_retains_data_and_last_success_between_processes(self):
        self.run_publish()
        first=self.state()
        self.log.unlink()
        success,_=self.run_publish()
        state=self.state()
        self.assertFalse(success)
        self.assertEqual(state['runners'],first['runners'])
        self.assertEqual(state['source']['last_success'],first['source']['last_success'])
        self.assertTrue(state['source']['error'])
    def test_first_source_failure_still_publishes_clear_error_page(self):
        self.log.unlink()
        success,_=self.run_publish()
        self.assertFalse(success)
        self.assertIsNone(self.state()['source']['last_success'])
        self.assertTrue(self.state()['source']['error'])
    def test_rejects_private_data_in_web_directory(self):
        with self.assertRaisesRegex(ValueError,'outside the public'):
            check_destination(self.web,self.web/'state.sqlite3',self.config)
        with self.assertRaisesRegex(ValueError,'outside the public'):
            check_destination(self.web,self.database,self.config,self.web/'token.json')
    def test_does_not_overwrite_existing_website(self):
        self.web.mkdir(parents=True)
        (self.web/'index.html').write_text('Existing website')
        with self.assertRaisesRegex(ValueError,'not empty'):
            self.run_publish()
        self.assertEqual((self.web/'index.html').read_text(),'Existing website')
    def test_rejects_concurrent_runs(self):
        with publisher_lock(self.database):
            with self.assertRaisesRegex(ValueError,'already running'):
                self.run_publish()
        self.assertTrue(self.run_publish()[0])
    def test_atomic_failure_preserves_previous_file(self):
        target=self.root/'state.json'
        target.write_text('previous complete content')
        with patch('tracker.publish.os.replace',side_effect=OSError('simulated failure')):
            with self.assertRaises(OSError):atomic_write(target,'new content')
        self.assertEqual(target.read_text(),'previous complete content')
        self.assertFalse(list(self.root.glob('.mdr-*')))


if __name__=='__main__':unittest.main()
