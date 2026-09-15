"""Published data integrity, fixed denominators, and revision isolation."""
import hashlib
import json
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from experiment_results import ZIP1_DATASET, Zip1ExperimentResults, order_revisions, result_router


class Zip1ArchiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root=Path(__file__).resolve().parents[1]/'experiments'/ZIP1_DATASET
        if not (cls.root/'verification.json').is_file():
            raise unittest.SkipTest('ZIP 1 archive not hydrated')
        cls.library=Zip1ExperimentResults(cls.root)

    def test_every_published_file_matches_its_hash(self):
        verification=json.loads((self.root/'verification.json').read_text())
        for name,expected in verification['files_sha256'].items():
            path=(self.root/name).resolve()
            self.assertTrue(path.is_relative_to(self.root.resolve()))
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),expected,name)

    def test_all_500_outcomes_are_accounted_for(self):
        summary=json.loads((self.root/'summary.json').read_text())
        audit=json.loads((self.root/'competition-audit.json').read_text())
        count=summary['totals']
        self.assertEqual(len(self.library.orders()),500)
        self.assertEqual(sum(r['total_boxes'] for r in self.library.orders()),77950)
        self.assertEqual(count['orders_valid'],484)
        self.assertEqual(count['orders_complete'],214)
        self.assertEqual(count['orders_partial'],270)
        self.assertEqual(len(summary['failures']),16)
        self.assertEqual(audit['totals']['orders_missing'],16)
        self.assertEqual(audit['totals']['orders_invalid'],0)
        self.assertEqual(audit['totals']['orders_expected'],500)
        placed=complete=0
        for order in self.library.orders():
            oid=order['order_id']; result=self.library.ep_result(oid)
            self.assertFalse(self.library.teacher_result(oid)['available'])
            if oid in summary['failures']:
                self.assertFalse(result['available']); continue
            pack=result['pack']; report=audit['orders'][oid]
            self.assertTrue(report['valid'])
            self.assertEqual(len(pack['boxes']),report['accepted_boxes'])
            self.assertEqual(report['complete'],len(pack['boxes'])==order['total_boxes'])
            self.assertEqual(result['provenance']['experiment'],ZIP1_DATASET)
            self.assertFalse(result['provenance']['leaderboard'])
            placed+=len(pack['boxes']); complete+=report['complete']
        self.assertEqual(placed,65496); self.assertEqual(complete,214)

    def test_actual_router_and_revisions_exclude_failed_packs(self):
        class EmptyBaseline:
            teachers={}
            _check_id=staticmethod(Zip1ExperimentResults._check_id)
        app=FastAPI(); app.include_router(result_router(self.root,self.library))
        base='/viz-api/experiments/'+ZIP1_DATASET
        with TestClient(app) as client:
            result=client.get(base+'/ep-result/ORD-08511033').json()
            self.assertEqual(len(result['pack']['boxes']),175)
            self.assertFalse(client.get(base+'/ep-result/ORD-10118492').json()['available'])
            self.assertFalse(client.get(base+'/result/ORD-08511033').json()['available'])
            self.assertEqual(client.get(base+'/rl-result/ORD-08511033').status_code,404)
        def revisions(oid):
            return order_revisions(oid,EmptyBaseline(),self.root,lambda *_:None,[self.library])
        self.assertEqual(revisions('ORD-08511033')[0]['dataset'],ZIP1_DATASET)
        self.assertNotIn(ZIP1_DATASET,[r['dataset'] for r in revisions('ORD-10118492')])


if __name__=='__main__': unittest.main()
