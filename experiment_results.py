"""Read-only visualization of a pinned research archive, never leaderboard data.

This module deliberately does not import the legacy backend or open its database.
The frozen teacher inventory supplies the catalogue and order denominators.
"""
import gzip
import hashlib
import json
import re
from collections import Counter
from functools import cached_property
from pathlib import Path

from fastapi import APIRouter, HTTPException

DATASET = "baseline-library-20260910-2m"


class ExperimentResults:
    def __init__(self, root: Path):
        self.root = root.resolve()

    @cached_property
    def metadata(self):
        return json.loads((self.root / "viewer.json").read_text(encoding="utf-8"))

    @cached_property
    def teachers(self):
        path = self.root / "teacher" / "orders-audited.jsonl.gz"
        if hashlib.sha256(path.read_bytes()).hexdigest() != self.metadata["teacher_sha256"]:
            raise ValueError("Teacher archive does not match its recorded revision")
        orders = {}
        with gzip.open(path, "rt", encoding="utf-8") as records:
            for line in records:
                record = json.loads(line)
                oid = record["order_id"]
                if oid in orders:
                    raise ValueError("Duplicate teacher order")
                orders[oid] = {key: record[key] for key in ("container", "boxes", "expert")}
        return orders

    @staticmethod
    def _check_id(order_id):
        if not re.fullmatch(r"ORD-[0-9]{8}", order_id):
            raise HTTPException(status_code=400, detail="Invalid order ID")

    def skus(self):
        catalogue = {}
        for order in self.teachers.values():
            for _, sku, w, d, h, mass, *_ in order["boxes"]:
                item = dict(sku_id=sku, name=sku, length=w, width=d, height=h, weight=mass)
                if sku in catalogue and catalogue[sku] != item:
                    raise ValueError("Inconsistent frozen SKU dimensions or weight")
                catalogue[sku] = item
        return [catalogue[sku] for sku in sorted(catalogue)]

    def orders(self):
        return [dict(order_id=oid, sku_count=len({b[1] for b in order["boxes"]}),
                     total_boxes=len(order["boxes"]))
                for oid, order in sorted(self.teachers.items())]

    def order(self, order_id: str):
        self._check_id(order_id)
        record = self.teachers.get(order_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Order not in this experiment")
        counts = Counter(b[1] for b in record["boxes"])
        return dict(order_id=order_id, items=[dict(sku_id=sku, quantity=n)
                                            for sku, n in sorted(counts.items())])

    def _provenance(self, subject):
        return dict(code_commit=self.metadata["suite_commit"],
                    code_repository=self.metadata["suite_repository"], subject=subject,
                    experiment=DATASET, training_approved=False, leaderboard=False)

    def teacher_result(self, order_id: str):
        self._check_id(order_id)
        order = self.teachers.get(order_id)
        if order is None:
            return dict(available=False, order_id=order_id)
        master = {b[0]: b for b in order["boxes"]}
        if len(master) != len(order["boxes"]):
            raise ValueError("Duplicate master box identity")
        placed, used = [], set()

        def box(bid, x, y, z, yaw):
            if yaw not in (0, 90):
                raise ValueError("Unsupported teacher orientation")
            _, sku, w, d, h, mass, *_ = master[bid]
            if yaw == 90:
                w, d = d, w
            return dict(id=bid, sku_id=sku, weight=mass, rotation=yaw,
                        position=dict(x=x, y=y, z=z),
                        dimensions=dict(width=w, depth=d, height=h))

        for bid, x, y, z, yaw in order["expert"]:
            if bid in used:
                raise ValueError("Duplicate teacher identity")
            used.add(bid)
            placed.append(box(bid, x, y, z, yaw))
        container = dict(zip(("width", "depth", "height"), order["container"]))
        common = dict(order_id=order_id, container=container)
        # Placeholder positions are only consumed by the schematic remainder view.
        remainder = [box(bid, 0., 0., 0., 0) for bid in master if bid not in used]
        return dict(available=True, order_id=order_id,
                    placed=dict(**common, kind="placed", boxes=placed),
                    remainder=dict(**common, kind="remainder", boxes=remainder),
                    teacher_empty=not placed,
                    provenance=self._provenance(
                        "Certified P1+2 teacher audit; 4096 global / 1 local candidate. "
                        "Not the EP run foundation or training approval."))

    def ep_result(self, order_id: str):
        self._check_id(order_id)
        path = self.root / "packs" / (order_id + ".packformation.json")
        if path.resolve().parent != (self.root / "packs").resolve():
            raise HTTPException(status_code=400, detail="Invalid pack path")
        if not path.is_file():
            return dict(available=False, order_id=order_id)
        return dict(available=True, order_id=order_id,
                    pack=json.loads(path.read_text(encoding="utf-8")),
                    provenance=self._provenance(
                        "Experimental validated grid EP; not a leaderboard replacement."))


def result_router(root: Path):
    library = ExperimentResults(root)
    router = APIRouter(prefix="/viz-api/experiments/" + DATASET)
    for path, handler in (("/skus", library.skus), ("/orders", library.orders),
                          ("/orders/{order_id}", library.order),
                          ("/result/{order_id}", library.teacher_result),
                          ("/ep-result/{order_id}", library.ep_result)):
        router.add_api_route(path, handler, methods=["GET"])
    return router
