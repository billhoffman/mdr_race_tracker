import csv
import json
from pathlib import Path
import tempfile
import unittest

from tracker.core import load_config
from tracker.import_roster import import_roster


class RosterTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=Path(self.temp.name)/'export.csv'
    def tearDown(self):
        self.temp.cleanup()
    def write(self,rows):
        with self.path.open('w',newline='') as f:
            writer=csv.writer(f)
            writer.writerow(['Bib','First Name','Last Name','Removed','Email','emergency_phone'])
            writer.writerows(rows)
    def test_import_skips_unassigned_removed_and_duplicates(self):
        self.write([['101','Alex','Demo','','private@example.test','123'],
                    ['101','Alex','Demo','','private@example.test','123'],
                    ['','Blair','Demo','','',''],['103','Casey','Demo','TRUE','','']])
        roster,skipped=import_roster(self.path)
        self.assertEqual(roster,[{'bib':'101','name':'Alex Demo'}])
        self.assertEqual(skipped,{'no_bib':1,'removed':1,'duplicates':1})
    def test_conflicting_bib_rejected(self):
        self.write([['101','Alex','Demo','','',''],['101','Casey','Demo','','','']])
        with self.assertRaisesRegex(ValueError,'more than one name'):import_roster(self.path)
    def test_roster_override_does_not_change_test_configuration(self):
        root=Path(__file__).resolve().parents[2]
        path=Path(self.temp.name)/'roster.json'
        path.write_text(json.dumps([{'bib':'200','name':'Other Demo'}]))
        config=load_config(root/'races/moreau-test/race.json',path)
        self.assertEqual(list(config['runners']),['200'])
        original=load_config(root/'races/moreau-test/race.json')
        self.assertEqual(len(original['runners']),6)


if __name__=='__main__':unittest.main()

class RosterUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'roster.json'
    def tearDown(self):self.temp.cleanup()
    def test_reimport_keeps_late_additions_and_has_backup(self):
        from tracker.roster import update_roster
        update_roster(self.path,[{'bib':'101','name':'Alex Demo'}])
        update_roster(self.path,[{'bib':'107','name':'Late Runner'}],require_existing=True)
        result=update_roster(self.path,[{'bib':'101','name':'Alex Demo'},{'bib':'108','name':'New Export'}])
        self.assertEqual(result['total'],3)
        self.assertEqual(result['retained'],1)
        self.assertEqual({r['bib'] for r in json.loads(self.path.read_text())},{'101','107','108'})
        self.assertEqual(len(json.loads(Path(str(self.path)+'.bak').read_text())),2)
    def test_reassignment_and_missing_initial_roster_are_rejected(self):
        from tracker.roster import update_roster
        with self.assertRaisesRegex(ValueError,'initial UltraSignup'):
            update_roster(self.path,[{'bib':'107','name':'Late Runner'}],require_existing=True)
        update_roster(self.path,[{'bib':'101','name':'Alex Demo'}])
        before=self.path.read_text()
        with self.assertRaisesRegex(ValueError,'assignments changed'):
            update_roster(self.path,[{'bib':'101','name':'Other Runner'}])
        self.assertEqual(self.path.read_text(),before)
    def test_failed_write_keeps_previous_roster_valid(self):
        from tracker.roster import update_roster
        from unittest.mock import patch
        update_roster(self.path,[{'bib':'101','name':'Alex Demo'}])
        before=self.path.read_text()
        with patch('tracker.roster.os.replace',side_effect=OSError('simulated disk failure')):
            with self.assertRaises(OSError):update_roster(self.path,[{'bib':'107','name':'Late Runner'}])
        self.assertEqual(self.path.read_text(),before)
