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
