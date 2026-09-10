import copy
import pytest
from competition.audit_ep_experiment import benchmark_from_inputs, convert
from competition.evaluator import evaluate, summarize


def fixture():
    specs = [dict(sku_id='A', width=.4, depth=.2, height=.1, weight=2)]
    doc = dict(order_id='O', boxes=[dict(id=0, sku_id='A', rotation=90, weight=2,
               position=dict(x=.1, y=.2, z=.05), dimensions=dict(width=.2, depth=.4, height=.1))])
    benchmark = benchmark_from_inputs({'O': specs}, dict(width=.8, depth=1.2, height=1.875))
    return specs, doc, benchmark


def test_valid_rotation_and_floor():
    specs, doc, benchmark = fixture()
    report = evaluate(benchmark, convert(doc, specs))
    assert report['valid'] and report['complete']


@pytest.mark.parametrize('key,value', [('weight', 3), ('rotation', 0), ('id', -1), ('sku_id', 'B')])
def test_reject_master_mismatch(key, value):
    specs, doc, _ = fixture()
    doc['boxes'][0][key] = value
    with pytest.raises(ValueError):
        convert(doc, specs)


def test_near_level_assumption_does_not_weaken_competition_gate():
    specs, doc, benchmark = fixture()
    doc['boxes'][0]['position']['z'] += .005
    report = evaluate(benchmark, convert(doc, specs))
    assert not report['valid']
    assert report['static_equilibrium'] == 'unsupported'


def test_duplicate_id_rejected_and_missing_denominator_preserved():
    specs, doc, benchmark = fixture()
    doc['boxes'].append(copy.deepcopy(doc['boxes'][0]))
    report = evaluate(benchmark, convert(doc, specs))
    assert not report['valid']
    totals = summarize(benchmark, {})
    assert totals['orders_missing'] == 1 and totals['boxes_expected'] == 1


def test_conflicting_sku_masters_rejected():
    specs, _, benchmark = fixture()
    with pytest.raises(ValueError):
        benchmark_from_inputs({'a': specs, 'b': [dict(specs[0], weight=5)]}, benchmark['container'])
