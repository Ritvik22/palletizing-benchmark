"""Integrity, counts, and endpoint isolation for the fresh 1000-order EP run."""
import hashlib
import json
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from experiment_results import LATEST_EP_DATASET, LatestEPExperimentResults, order_revisions, result_router


class LatestEPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[1] / "experiments" / LATEST_EP_DATASET
        cls.library = LatestEPExperimentResults(cls.root)

    def test_hashes_counts_and_no_teacher(self):
        verification = json.loads((self.root / "verification.json").read_text())
        self.assertTrue(verification["fresh_generation_verified"])
        for name, expected in verification["files_sha256"].items():
            path = (self.root / name).resolve()
            self.assertTrue(path.is_relative_to(self.root.resolve()))
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), expected, name)
        audit = json.loads((self.root / "competition-audit.json").read_text())
        orders = self.library.orders()
        self.assertEqual((len(orders), sum(o["total_boxes"] for o in orders)), (1000, 155904))
        placed = complete = 0
        for order in orders:
            oid = order["order_id"]
            result = self.library.ep_result(oid)
            count = len(result["pack"]["boxes"])
            self.assertTrue(audit["orders"][oid]["valid"])
            self.assertEqual(count, audit["orders"][oid]["accepted_boxes"])
            self.assertFalse(self.library.teacher_result(oid)["available"])
            self.assertFalse(result["provenance"]["leaderboard"])
            placed += count
            complete += count == order["total_boxes"]
        self.assertEqual((placed, complete), (155607, 953))

    def test_router_and_revision_picker(self):
        class Baseline:
            teachers = {}
            _check_id = staticmethod(LatestEPExperimentResults._check_id)
        app = FastAPI()
        app.include_router(result_router(self.root, self.library))
        with TestClient(app) as client:
            oid = "ORD-08511033"
            result = client.get(f"/viz-api/experiments/{LATEST_EP_DATASET}/ep-result/{oid}")
            self.assertEqual(result.status_code, 200)
            self.assertTrue(result.json()["available"])
            revisions = order_revisions(oid, Baseline(), self.root, lambda *_: None, [self.library])
            self.assertEqual(revisions[0]["dataset"], LATEST_EP_DATASET)
            self.assertEqual(revisions[0]["date_kind"], "run_completed")
            self.assertFalse(client.get(f"/viz-api/experiments/{LATEST_EP_DATASET}/result/{oid}").json()["available"])
            self.assertEqual(client.get(f"/viz-api/experiments/{LATEST_EP_DATASET}/rl-result/{oid}").status_code, 404)
