"""Deterministic benchmark evaluator. Never execute a competitor's code.

The stability gate solves nonnegative vertical reactions at contact corners,
with force and x/y moment equilibrium for EVERY box simultaneously. Shared
supports therefore do not double-count weight. This is ideal rigid-body static
gravity equilibrium, not friction, tipping-angle, deformation or robot safety.
"""
import hashlib
import json
import math
from collections import Counter

from .models import Pack

VERSION = 'rigid-static-v1.0.0'
TOL = 1e-6  # metres; part of this evaluator version


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def materialize(benchmark, pack: Pack):
    """Reconstruct dimensions and mass ONLY from the immutable item master."""
    order = benchmark['orders'].get(pack.order_id)
    if order is None:
        raise ValueError('Order does not belong to this benchmark.')
    expected = {b['id']: b['sku_id'] for b in order['instances']}
    boxes, errors, seen = [], [], set()
    for b in pack.boxes:
        if b.id in seen:
            errors.append(f'Duplicate box ID: {b.id}')
            continue
        seen.add(b.id)
        if expected.get(b.id) != b.sku_id:
            errors.append(f'Box/SKU identity mismatch: {b.id}')
            continue
        s = benchmark['skus'][b.sku_id]
        w, d = (s['length'], s['width']) if b.rotation == 0 else (s['width'], s['length'])
        boxes.append({'id': b.id, 'sku_id': b.sku_id, 'weight': s['weight'],
                      'dimensions': {'width': w, 'depth': d, 'height': s['height']},
                      'position': b.position.model_dump(), 'rotation': b.rotation})
    return boxes, errors, len(expected), len(set(expected) & seen)


def extent(b):
    p, d = b['position'], b['dimensions']
    return tuple((p[a] - d[k] / 2, p[a] + d[k] / 2)
                 for a, k in zip(('x', 'y', 'z'), ('width', 'depth', 'height')))


def equilibrium(boxes, extents):
    """Return a status and contact graph using a global contact-force LP."""
    import numpy as np
    from scipy.optimize import linprog
    from scipy.sparse import coo_matrix

    edges, rows, cols, values, rhs = [], [], [], [], np.zeros(3 * len(boxes))
    variable = 0
    max_weight = max(b['weight'] for b in boxes)
    for i, (b, e) in enumerate(zip(boxes, extents)):
        p = b['position']
        rhs[3*i:3*i+3] = [b['weight']/max_weight, 0, 0]
        contacts = []
        if abs(e[2][0]) <= TOL:
            contacts.append((-1, e[0], e[1]))
        for j, f in enumerate(extents):
            if i == j or abs(e[2][0] - f[2][1]) > TOL:
                continue
            xr = (max(e[0][0], f[0][0]), min(e[0][1], f[0][1]))
            yr = (max(e[1][0], f[1][0]), min(e[1][1], f[1][1]))
            if xr[1] - xr[0] > TOL and yr[1] - yr[0] > TOL:
                contacts.append((j, xr, yr))
        if not contacts:
            return 'unsupported', edges
        for j, xr, yr in contacts:
            edges.append({'upper': b['id'], 'lower': boxes[j]['id'] if j >= 0 else 'pallet',
                          'area_m2': (xr[1]-xr[0])*(yr[1]-yr[0])})
            if len(edges) > 5000:
                return 'evaluation-limit', edges
            for x in xr:
                for y in yr:
                    for body, sign in ((i, 1), (j, -1)):
                        if body < 0:
                            continue
                        q = boxes[body]['position']
                        for axis, value in enumerate((1, x-q['x'], y-q['y'])):
                            rows.append(3*body+axis); cols.append(variable); values.append(sign*value)
                    variable += 1
    matrix = coo_matrix((values, (rows, cols)), shape=(len(rhs), variable)).tocsr()
    result = linprog(np.zeros(variable), A_eq=matrix, b_eq=rhs, bounds=(0, None),
                     method='highs', options={'time_limit': 3.0})
    if result.status == 2:
        return 'unstable', edges
    if not result.success or np.max(np.abs(matrix @ result.x - rhs)) > 1e-7:
        return 'evaluation-limit', edges
    return 'balanced', edges


def evaluate(benchmark, pack: Pack):
    if benchmark['evaluator_version'] != VERSION:
        raise ValueError('This evaluator cannot score that benchmark version.')
    boxes, errors, expected, known = materialize(benchmark, pack)
    extents = [extent(b) for b in boxes]
    container = benchmark['container']
    sizes = [container[k] for k in ('width', 'depth', 'height')]
    for i, (b, e) in enumerate(zip(boxes, extents)):
        if any(lo < -TOL or hi > size + TOL for (lo, hi), size in zip(e, sizes)):
            errors.append(f'Outside pallet/container: {b["id"]}')
        for j in range(i):
            if all(min(e[k][1], extents[j][k][1])-max(e[k][0], extents[j][k][0]) > TOL for k in range(3)):
                errors.append(f'Overlap: {boxes[j]["id"]} / {b["id"]}')
                if len(errors) >= 100:
                    break
        if len(errors) >= 100:
            break
    status, graph = ('not-evaluated', []) if errors or not boxes else equilibrium(boxes, extents)
    if status not in ('not-evaluated', 'balanced'):
        errors.append('Static support: ' + status)
    # Optional, explicit benchmark rule; weight proxy is not material crush strength.
    if benchmark.get('stacking_rule') == 'heavy-not-on-light':
        by_id = {b['id']: b for b in boxes}
        for edge in graph:
            if edge['lower'] == 'pallet':
                continue
            upper, lower = (benchmark['skus'][by_id[edge[k]]['sku_id']] for k in ('upper', 'lower'))
            if upper['stack_class'] == 'heavy' and lower['stack_class'] == 'light':
                errors.append(f'Weight-class rule: {edge["upper"]} on {edge["lower"]}')
    valid = not errors
    volume = sum(math.prod(b['dimensions'].values()) for b in boxes)
    top = max((e[2][1] for e in extents), default=0)
    complete = valid and expected > 0 and len(boxes) == expected
    lve = sizes[0] * sizes[1] * top / volume if complete and volume else None
    return {'evaluator_version': VERSION, 'valid': valid, 'complete': complete,
            'expected': expected, 'submitted': len(pack.boxes),
            'accepted_boxes': len(boxes) if valid else 0,
            'remaining': expected-len(boxes) if valid else expected,
            'height_m': top if valid else None, 'volume_m3': volume if valid else None,
            'weight_kg': sum(b['weight'] for b in boxes) if valid else None,
            'lve': lve, 'static_equilibrium': status, 'errors': errors[:100],
            'support_contacts': graph if valid else [], 'artifact_sha256': digest(pack.model_dump())}


def summarize(benchmark, reports):
    """Fixed denominators; invalid and missing orders cannot improve coverage."""
    n = len(benchmark['orders'])
    wanted = sum(len(o['instances']) for o in benchmark['orders'].values())
    reports = {oid: r for oid, r in reports.items() if oid in benchmark['orders']}
    complete = [r for r in reports.values() if r['complete']]
    return {'orders_expected': n, 'orders_submitted': len(reports),
            'orders_missing': n-len(reports), 'orders_invalid': sum(not r['valid'] for r in reports.values()),
            'orders_complete': len(complete), 'completion_fraction': len(complete)/n if n else 0,
            'boxes_expected': wanted, 'boxes_accepted': sum(r['accepted_boxes'] for r in reports.values()),
            'lve_complete_mean': sum(r['lve'] for r in complete)/len(complete) if complete else None,
            'lve_n': len(complete), 'evaluator_version': VERSION}
