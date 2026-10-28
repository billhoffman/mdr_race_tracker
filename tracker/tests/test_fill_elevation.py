import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tracker.fill_elevation import elevation_value,fill_course
from tracker.core import load_config


class FillElevationTests(unittest.TestCase):
    def test_rejects_no_data(self):
        for value in ['NaN','-1000000',None]:
            with self.assertRaises(ValueError):elevation_value({'value':value})
    def test_fill_preserves_positions_existing_elevations_and_backup(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'course.json';cache=Path(temp)/'cache'
            course={'route':{'coordinates':[[1,2,100],[2,3,0],[3,4,200]],'elevation_zero_is_missing':True}}
            original=json.dumps(course);path.write_text(original)
            with patch('tracker.fill_elevation.time.sleep'):
                self.assertEqual(fill_course(path,cache,lambda x,y:{'value':'150.5'}),1)
            result=json.loads((Path(temp)/'course.elevation.local.json').read_text())
            self.assertEqual(path.read_text(),original)
            self.assertEqual(result['elevation_backfill']['points'][0]['original_m'],0)
            self.assertEqual(result['elevation_backfill']['points'][0]['elevation_m'],150.5)
            self.assertEqual(next(cache.glob('course-original-*')).read_text(),original)
            config={'course_file':'course.json','roster':[{'bib':'101','name':'Alex Demo'}],'start_time':'2026-10-31T08:00:00-04:00'}
            course['checkpoints']=[]
            path.write_text(json.dumps(course))
            config_path=Path(temp)/'race.json';config_path.write_text(json.dumps(config))
            loaded=load_config(config_path)
            self.assertEqual(loaded['course']['route']['coordinates'],[[1,2,100],[2,3,150.5],[3,4,200]])
    def test_partial_failure_does_not_modify_course_and_can_resume(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'course.json';cache=Path(temp)/'cache'
            original=json.dumps({'route':{'coordinates':[[1,2,0],[2,3,0]],'elevation_zero_is_missing':True}})
            path.write_text(original)
            def failing(x,y):
                if x==2:raise ValueError('simulated network failure')
                return {'value':'100'}
            with patch('tracker.fill_elevation.time.sleep'),self.assertRaises(ValueError):fill_course(path,cache,failing)
            self.assertEqual(path.read_text(),original)
            requests=[]
            with patch('tracker.fill_elevation.time.sleep'):
                fill_course(path,cache,lambda x,y:requests.append(x) or {'value':'200'})
            self.assertEqual(requests,[2])
