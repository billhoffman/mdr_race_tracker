import unittest
from tracker.server import public_snapshot


class PublicViewTests(unittest.TestCase):
    def test_public_view_omits_operator_details(self):
        original={'source':{'error':'Internal file or login detail'},'history':[{'raw':'operator log'}],
                  'issues':[{'text':'private note'}],'anomalies':[{'message':'review'}],
                  'runners':[{'bib':'101','name':'Alex Demo'}]}
        public=public_snapshot(original)
        self.assertTrue(public['public_view'])
        self.assertEqual(public['history'],[])
        self.assertEqual(public['issues'],[])
        self.assertEqual(public['anomalies'],[])
        self.assertNotIn('Internal',public['source']['error'])
        self.assertEqual(public['runners'],original['runners'])
        self.assertEqual(original['source']['error'],'Internal file or login detail')


if __name__=='__main__':unittest.main()
