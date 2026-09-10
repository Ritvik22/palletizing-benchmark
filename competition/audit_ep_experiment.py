"""Audit a frozen local EP experiment without publishing a leaderboard revision.

python -m competition.audit_ep_experiment --experiment experiments/<run-id>
The competition's unchanged exact-contact model is intentionally stricter than
the EP experiment's 10 mm assumed-settling model. Neither is a transport test.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

from .evaluator import VERSION, digest, evaluate, summarize
from .models import Pack


def benchmark_from_inputs(inputs, container):
    skus, orders = {}, {}
    for oid, specs in inputs.items():
        instances = []
        for i, spec in enumerate(specs):
            sku = dict(length=spec['width'], width=spec['depth'],
                       height=spec['height'], weight=spec['weight'])
            if spec['sku_id'] in skus and skus[spec['sku_id']] != sku:
                raise ValueError('Conflicting item master: ' + spec['sku_id'])
            skus[spec['sku_id']] = sku
            instances.append(dict(id=str(i), sku_id=spec['sku_id']))
        orders[oid] = dict(instances=instances)
    return dict(evaluator_version=VERSION, container=container, orders=orders, skus=skus,
                stacking_rule=None)


def convert(document, specs):
    """Reject forged dimensions rather than quietly repairing a submitted pack."""
    rows = []
    for b in document['boxes']:
        i, rotation = b['id'], b['rotation']
        if type(i) is not int or not 0 <= i < len(specs) or rotation not in (0, 90, 180, 270):
            raise ValueError('Invalid box ID or rotation')
        s = specs[i]
        expected = (s['width'], s['depth'], s['height']) if rotation % 180 == 0 else (s['depth'], s['width'], s['height'])
        if (b['sku_id'] != s['sku_id'] or
                not math.isclose(b['weight'], s['weight'], rel_tol=0, abs_tol=1e-9) or
                any(not math.isclose(b['dimensions'][k], v, rel_tol=0, abs_tol=1e-9)
                    for k, v in zip(('width', 'depth', 'height'), expected))):
            raise ValueError('Export does not match frozen item master: ' + str(i))
        rows.append(dict(id=str(i), sku_id=b['sku_id'], rotation=rotation % 180,
                         position=b['position']))
    return Pack(order_id=document['order_id'], boxes=rows)


def audit(experiment):
    manifest = json.loads((experiment/'manifest.json').read_text(encoding='utf-8'))
    inputs = json.loads((experiment/'inputs.json').read_text(encoding='utf-8'))
    if digest(inputs) != manifest['input_sha256']:
        raise ValueError('Frozen input hash mismatch')
    benchmark = benchmark_from_inputs(inputs, manifest['container'])
    reports = {}
    for oid, specs in inputs.items():
        path = experiment/'packs'/(oid + '.packformation.json')
        # Order IDs are local artifact basenames, never arbitrary paths.
        if path.resolve().parent != (experiment/'packs').resolve():
            raise ValueError('Unsafe order ID')
        if not path.exists():
            continue  # summarize keeps missing orders in the denominator
        try:
            document = json.loads(path.read_text(encoding='utf-8'))
            if document['order_id'] != oid or document['container'] != manifest['container']:
                raise ValueError('Order/container mismatch')
            report = evaluate(benchmark, convert(document, specs))
            # Graph data can be reconstructed; keep this review compact.
            report['support_contact_count'] = len(report.pop('support_contacts'))
        except (ValueError, KeyError, TypeError) as exc:
            report = dict(valid=False, complete=False, accepted_boxes=0,
                          errors=[str(exc)], evaluator_version=VERSION)
        report['source_pack_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        reports[oid] = report
    return dict(publication='experimental audit only; not submitted or published',
                evaluator_source_sha256={name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                                         for name in ('evaluator.py', 'models.py', 'audit_ep_experiment.py')},
                model='Exact-contact rigid-body static gravity equilibrium, 1 micrometre tolerance; no wrap, friction, settling or robot reach model.',
                stacking_rule=None, input_sha256=manifest['input_sha256'],
                totals=summarize(benchmark, reports), orders=reports)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--experiment', type=Path, required=True)
    a = ap.parse_args()
    result = audit(a.experiment.resolve())
    target = a.experiment/'competition-audit.json'
    with target.open('x', encoding='utf-8') as f:
        json.dump(result, f, indent=2, allow_nan=False)
        f.write('\n')
    print(json.dumps(result['totals'], indent=2))
    return 0 if result['totals']['orders_invalid'] == result['totals']['orders_missing'] == 0 else 2


if __name__ == '__main__':
    raise SystemExit(main())
