"""Archived pack fidelity and HTTP checks; no legacy backend/database import."""
import copy
import json
import sqlite3
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from experiment_results import DATASET, ExperimentResults, result_router

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "experiments" / DATASET


class ExperimentResultTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.library = ExperimentResults(ARCHIVE)

    def test_all_ep_artifacts_are_exact(self):
        boxes = complete = 0
        for oid, order in self.library.teachers.items():
            data = self.library.ep_result(oid)
            original = json.loads((ARCHIVE / "packs" / (oid + ".packformation.json")).read_text())
            self.assertTrue(data["available"])
            self.assertEqual(data["pack"], original)
            boxes += len(original["boxes"])
            complete += len(original["boxes"]) == len(order["boxes"])
        self.assertEqual(len(self.library.teachers), 1000)
        self.assertEqual((boxes, complete), (128533, 305))

    def test_all_teacher_partitions_preserve_ids_and_poses(self):
        placed_total = empty = 0
        for oid, order in self.library.teachers.items():
            data = self.library.teacher_result(oid)
            placed, remainder = data["placed"]["boxes"], data["remainder"]["boxes"]
            used, left = {b["id"] for b in placed}, {b["id"] for b in remainder}
            master = {b[0]: b for b in order["boxes"]}
            self.assertFalse(used & left)
            self.assertEqual(used | left, set(master))
            self.assertEqual(len(placed) + len(remainder), len(master))
            self.assertEqual([[b["id"], b["position"]["x"], b["position"]["y"], b["position"]["z"], b["rotation"]]
                              for b in placed], order["expert"])
            for b in placed + remainder:
                spec = master[b["id"]]
                w, d = (spec[3], spec[2]) if b["rotation"] == 90 else (spec[2], spec[3])
                self.assertEqual(b["dimensions"], dict(width=w, depth=d, height=spec[4]))
                self.assertEqual((b["sku_id"], b["weight"]), (spec[1], spec[5]))
            self.assertEqual(data["teacher_empty"], not placed)
            self.assertFalse(data["provenance"]["training_approved"])
            self.assertNotIn("commit", data["provenance"])  # Code revision is not publication date.
            placed_total += len(placed)
            empty += not placed
        self.assertEqual((placed_total, empty), (29643, 7))

    def test_frozen_inventory_agrees_with_published_master(self):
        with sqlite3.connect((ROOT / "backend" / "palletizer.db").as_uri() + "?mode=ro", uri=True) as db:
            skus = {r[0]: tuple(r[1:]) for r in db.execute("SELECT sku_id,length,width,height,weight FROM skus")}
            orders = {}
            for oid, sku, quantity in db.execute("SELECT order_id,sku_id,quantity FROM order_items"):
                orders.setdefault(oid, Counter())[sku] += quantity
        self.assertEqual(set(orders), set(self.library.teachers))
        self.assertEqual(sum(o["total_boxes"] for o in self.library.orders()), 155904)
        self.assertEqual({s["sku_id"]: (s["length"], s["width"], s["height"], s["weight"])
                          for s in self.library.skus()}, skus)
        for oid in orders:
            self.assertEqual({i["sku_id"]: i["quantity"] for i in self.library.order(oid)["items"]}, orders[oid])

    def test_router_without_backend_or_database(self):
        app = FastAPI()
        app.include_router(result_router(ARCHIVE))
        with TestClient(app) as client:
            prefix = "/viz-api/experiments/" + DATASET
            self.assertEqual(len(client.get(prefix + "/orders").json()), 1000)
            self.assertEqual(len(client.get(prefix + "/skus").json()), 500)
            ep = client.get(prefix + "/ep-result/ORD-08511033").json()
            self.assertEqual(len(ep["pack"]["boxes"]), 133)
            teacher = client.get(prefix + "/result/ORD-08511033").json()
            self.assertEqual(len(teacher["placed"]["boxes"]), 21)
            self.assertEqual(len(teacher["remainder"]["boxes"]), 154)
            for endpoint in ("result", "ep-result"):
                self.assertFalse(client.get(prefix + "/" + endpoint + "/ORD-00000000").json()["available"])
                for invalid in ("inputs", "..%5Cinputs", "ORD-123"):
                    self.assertEqual(client.get(prefix + "/" + endpoint + "/" + invalid).status_code, 400)
            self.assertEqual(client.get(prefix + "/orders/ORD-00000000").status_code, 404)
            self.assertEqual(client.get(prefix + "/neat-result/ORD-08511033").status_code, 404)

    def test_teacher_integrity_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            (path / "teacher").mkdir()
            (path / "teacher" / "orders-audited.jsonl.gz").write_bytes(b"invalid")
            library = ExperimentResults(path)
            library.metadata = self.library.metadata
            with self.assertRaisesRegex(ValueError, "recorded revision"):
                _ = library.teachers

    def test_bad_identity_or_rotation_is_not_silently_rendered(self):
        oid = "ORD-08511033"
        for failure in ("master", "expert", "yaw"):
            with self.subTest(failure=failure):
                library = ExperimentResults(ARCHIVE)
                record = copy.deepcopy(self.library.teachers[oid])
                library.teachers = {oid: record}
                if failure == "master":
                    record["boxes"].append(record["boxes"][0])
                elif failure == "expert":
                    record["expert"].append(record["expert"][0])
                else:
                    record["expert"][0][4] = 45
                with self.assertRaises(ValueError):
                    library.teacher_result(oid)


if __name__ == "__main__":
    unittest.main(verbosity=2)
