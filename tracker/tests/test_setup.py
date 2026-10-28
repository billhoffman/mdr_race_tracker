import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tracker.setup_race import create_config, main, race_start


class SetupTests(unittest.TestCase):
    def test_common_time_formats_and_timezone(self):
        for time in ['8:00 AM','08:00','8am','8 AM']:
            self.assertEqual(race_start('2026-10-31',time).isoformat(),'2026-10-31T08:00:00-04:00')
        self.assertEqual(race_start('2026-01-31','8 AM').isoformat(),'2026-01-31T08:00:00-05:00')
    def test_invalid_time_rejected(self):
        with self.assertRaises(ValueError):race_start('2026-10-31','25:30')
    def test_configuration_and_declining_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp)
            (directory/'course.json').write_text(json.dumps({'name':'Moreau Half','race_id':'moreau-half-2026'}))
            config=create_config(directory,race_start('2026-10-31','8 AM'))
            self.assertEqual(config['roster_file'],'roster.json')
            self.assertFalse(config['test_mode'])
            self.assertEqual(config['clock_mode'],'live')
            with patch('sys.argv',['setup','--race-dir',temp]),patch('builtins.input',side_effect=['','8 AM','n']),patch('builtins.print'):
                main()
            self.assertFalse((directory/'race.local.json').exists())
    def test_existing_config_is_backed_up(self):
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp)
            (directory/'course.json').write_text(json.dumps({'name':'Moreau Half'}))
            old=json.dumps({'date':'2026-10-31','start_time':'previous'})
            (directory/'race.local.json').write_text(old)
            with patch('sys.argv',['setup','--race-dir',temp]),patch('builtins.input',side_effect=['','8 AM','y']),patch('builtins.print'):
                main()
            self.assertEqual((directory/'race.local.json.bak').read_text(),old)
            self.assertEqual(json.loads((directory/'race.local.json').read_text())['start_time'],'2026-10-31T08:00:00-04:00')
