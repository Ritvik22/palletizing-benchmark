"""Publication integrity and honest completion counts for the accepted collection."""
import hashlib
import json
import unittest
from pathlib import Path
from fastapi import FastAPI
from fastapi.testclient import TestClient
from experiment_results import BEST_KNOWN_DATASET, BestKnownExperimentResults, order_revisions, result_router


class BestKnownTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[1]/'experiments'/BEST_KNOWN_DATASET
        cls.library = BestKnownExperimentResults(cls.root)

    def test_hashes_counts_and_no_teacher(self):
        verification = json.loads((self.root/'verification.json').read_text())
        self.assertFalse(verification['fresh_generation_verified'])
        for name, expected in verification['files_sha256'].items():
            path = (self.root/name).resolve()
            self.assertTrue(path.is_relative_to(self.root.resolve()))
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), expected, name)
        audit = json.loads((self.root/'competition-audit.json').read_text())
        placed = complete = 0
        orders = self.library.orders()
        self.assertEqual(len(orders), 1000)
        self.assertEqual(sum(o['total_boxes'] for o in orders), 155904)
        for o in orders:
            oid = o['order_id']; result = self.library.ep_result(oid)
            n = len(result['pack']['boxes'])
            self.assertTrue(audit['orders'][oid]['valid'])
            self.assertEqual(n, audit['orders'][oid]['accepted_boxes'])
            self.assertFalse(self.library.teacher_result(oid)['available'])
            self.assertFalse(result['provenance']['leaderboard'])
            self.assertEqual(result['provenance']['date_kind'], 'collection_created')
            placed += n; complete += n == o['total_boxes']
        self.assertEqual((placed, complete), (155901, 998))

    def test_router_and_revision_picker(self):
        class Baseline:
            teachers = {}
            _check_id = staticmethod(BestKnownExperimentResults._check_id)
        app = FastAPI(); app.include_router(result_router(self.root, self.library))
        with TestClient(app) as client:
            base = '/viz-api/experiments/'+BEST_KNOWN_DATASET
            for oid, expected in [('ORD-48034965',219),('ORD-65995248',198)]:
                result = client.get(base+'/ep-result/'+oid).json()
                self.assertEqual(len(result['pack']['boxes']), expected)
                revisions = order_revisions(oid, Baseline(), self.root, lambda *_:None, [self.library])
                self.assertEqual(revisions[0]['dataset'], BEST_KNOWN_DATASET)
                self.assertEqual(revisions[0]['date_kind'], 'collection_created')
            self.assertFalse(client.get(base+'/result/ORD-48034965').json()['available'])
            self.assertEqual(client.get(base+'/rl-result/ORD-48034965').status_code, 404)
