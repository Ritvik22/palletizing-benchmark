import pytest
from competition.evaluator import normalize_lve, summarize, VERSION

def test_legacy_conversion_is_per_pack_idempotent_and_read_only():
    a=dict(evaluator_version='rigid-static-v1.0.0', lve=2.,complete=True,valid=True,accepted_boxes=1)
    b=dict(a,lve=4.)
    converted=normalize_lve(a)
    assert converted['lve']==.5 and a['lve']==2
    assert normalize_lve(converted)==converted
    benchmark=dict(evaluator_version='rigid-static-v1.0.0',orders={'a':{'instances':[1]},'b':{'instances':[1]}})
    s=summarize(benchmark,{'a':a,'b':b})
    assert s['lve_complete_mean']==.375  # Not 1 / mean(2,4).
    assert s['evaluator_version']=='rigid-static-v1.0.0'  # No new physical certification.
    assert s['lve_version']=='pallet-volume-efficiency-v2'

def test_current_values_are_not_reciprocated():
    assert normalize_lve(dict(evaluator_version=VERSION,lve=.25))['lve']==.25
    with pytest.raises(ValueError):
        normalize_lve(dict(evaluator_version='unknown',lve=.25))
