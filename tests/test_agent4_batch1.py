"""Independent financial controls and regressions from the Agent 4 audit."""
from copy import deepcopy
from decimal import Decimal, ROUND_HALF_EVEN
import json
import random

import pytest
from agent4.contracts import MAX_CENTS
from agent4.decomposition import _c, decompose_line, decompose_multiproduct
from agent4.hierarchy import rollup, ReconciliationError
from agent4.materiality import classify_variance
from agent4.output import board_pack, exception_view
from agent4.reforecast import reforecast
from agent4.state import VarianceStore


def line(b=100, a=110, kind='revenue', name='Sales'):
    return dict(name=name, type=kind, budget={'amount':b}, actual={'amount':a})


def node(name='Sales', b=100, a=110, kind='revenue', sign='add'):
    return dict(name=name, sign=sign, leaf=line(b,a,kind,name))


@pytest.mark.parametrize('value,expected',[('1.015',102),('-1.015',-102),('1.005',100),('0.005',0),(1.015,102)])
def test_exact_decimal_rounding(value, expected):
    assert _c(value) == expected


@pytest.mark.parametrize('value',[True,False,float('nan'),float('inf'),'NaN','Infinity',10**20,None,'0.0000000000001'])
def test_invalid_money_rejected(value):
    with pytest.raises(ValueError): decompose_line(line(value))


def test_independent_factor_arithmetic_both_conventions():
    rng=random.Random(401)
    for _ in range(200):
        bp=Decimal(rng.randrange(1,10000))/1000
        ap=Decimal(rng.randrange(1,10000))/1000
        bv=rng.randrange(0,500);av=rng.randrange(0,500)
        expected=int((ap*av*100).quantize(Decimal(1),rounding=ROUND_HALF_EVEN))-int((bp*bv*100).quantize(Decimal(1),rounding=ROUND_HALF_EVEN))
        for convention in ('sequential','symmetric'):
            result=decompose_line(dict(name='Sales',type='revenue',budget=dict(price=str(bp),volume=bv),actual=dict(price=str(ap),volume=av)),convention)
            assert result['total_variance_cents']==expected
            assert sum(d['cents'] for d in result['drivers'])+result['residual_cents']==expected
            assert abs(result['residual_cents'])<=2


@pytest.mark.parametrize('side',[{'amount':100,'price':10,'volume':10},{'rate':10,'volume':10},{'price':1},{}])
def test_bad_representation_rejected(side):
    spec=line();spec['budget']=side
    with pytest.raises(ValueError):decompose_line(spec)


def test_mixed_currency_scale_and_representation_rejected():
    for context in [{'currency':'USD'},{'monetary_unit':'thousands'}]:
        with pytest.raises(ValueError):decompose_line({**line(),'context':context})
    spec=line();spec['actual']={'price':10,'volume':11}
    with pytest.raises(ValueError):decompose_line(spec)
    with pytest.raises(ValueError):decompose_line({**line(),'currency':'USD'})


def test_rate_basket_end_to_end_and_undefined_mix():
    products=[dict(name='Steel',budget=dict(rate=8,volume=100),actual=dict(rate=9,volume=110))]
    tree=dict(name='Profit',children=[dict(name='Cost',sign='subtract',leaf=dict(name='Cost',type='variable_cost',products=products))])
    result=rollup(tree)
    assert result['total_variance_cents']==-19000
    assert result['materiality']['base_cents']==80000
    assert board_pack(result)['reconciles']
    with pytest.raises(ValueError):decompose_multiproduct('Sales','revenue',[])
    products[0]['budget']['volume']=0
    with pytest.raises(ValueError,match='undefined'):decompose_multiproduct('Cost','variable_cost',products)


def test_zero_net_joint_is_visible():
    r=decompose_line(dict(name='Sales',type='revenue',budget=dict(price=10,volume=10),actual=dict(price=20,volume=5)))
    assert r['total_variance_cents']==0 and r['joint_term_cents']==-5000


def test_tree_identity_shape_and_cycles():
    with pytest.raises(ReconciliationError):rollup({**node(),'children':[node('Ignored')]})
    with pytest.raises(ReconciliationError):rollup(dict(name='Profit',children=[node(),node()]))
    tree=dict(name='Profit',children=[]);tree['children'].append(tree)
    with pytest.raises(ReconciliationError):rollup(tree)
    with pytest.raises(ReconciliationError):rollup(dict(name='Profit',children=[{**node(),'leaf':line(name='Different')}]))


def test_cost_root_signed_base_and_provenance():
    r=rollup(node(kind='fixed_cost'))
    assert not r['favourable'] and r['profit_impact_cents']==-1000
    tree=dict(name='Profit',children=[dict(name='Net',sign='add',children=[node('Gross',100,110),node('Deduction',90,95,sign='subtract')])])
    r=rollup(tree)
    assert r['materiality']['base_cents']==1000
    assert r['source_reconciliation']=='not_provided'
    tree['budget_cents']=1000;tree['actual_cents']=1500
    assert rollup(tree)['source_reconciliation']=='matched'
    tree['actual_cents']=1499
    with pytest.raises(ReconciliationError):rollup(tree)


@pytest.mark.parametrize('exporter',[board_pack,exception_view])
@pytest.mark.parametrize('field',['actual_cents','profit_impact_cents','total_variance_cents'])
def test_publication_recomputes_accounting(exporter,field):
    r=rollup(dict(name='Profit',children=[node()]))
    r[field]+=10000000
    with pytest.raises(ReconciliationError):exporter(r)


def test_residual_tolerance_checked():
    r=rollup(node());r['residual_cents']=10;r['drivers'][0]['cents']-=10
    with pytest.raises(ReconciliationError):board_pack(r)


def test_zero_and_tiny_materiality_base():
    for base in (0,1,10):
        r=classify_variance({'name':'X','total_variance_cents':0},0,base)
        assert not r['materiality']['material']
        assert r['materiality']['relative_pct'] is None
    with pytest.raises(ValueError):classify_variance({'name':'X','total_variance_cents':100},100,-1)


def test_dated_history_is_prior_only_and_context_consistent():
    tree=dict(name='Profit',context={'currency':'EUR','close_date':'2026-03-31'},children=[node()])
    tree['children'][0]['observation_history']=[{'period':'2026-01-31','variance_cents':100}]
    assert rollup(tree)['children'][0]['node_id']=='Profit/Sales'
    tree['children'][0]['observation_history'].append({'period':'2026-03-31','variance_cents':200})
    with pytest.raises(ValueError):rollup(tree)
    del tree['children'][0]['observation_history']
    tree['children'][0]['leaf']['context']={'close_date':'2026-02-28'}
    with pytest.raises(ReconciliationError):rollup(tree)


@pytest.mark.parametrize('direction,expected',[('higher_is_better',0.0),('lower_is_better',1.0)])
def test_closed_year_without_history_is_actual(direction,expected):
    r=reforecast(600,1200,4,4,direction=direction,budget_phasing_cents=[300]*4)
    assert r['projected_landing_cents']==600 and r['band_cents']==[600,600]
    assert r['prob_hit_target']==expected


def test_closed_year_inconsistent_phasing_rejected():
    assert 'error' in reforecast(600,1200,4,4,budget_phasing_cents=[150]*4,variance_history_cents=[-10,10]*3)


def test_no_elapsed_never_publishes_forecast_probability():
    r=reforecast(0,1200,0,4,variance_history_cents=[-10,10]*3)
    assert r['projected_landing_cents'] is None and r['prob_hit_target'] is None
    assert 'error' in reforecast(1,1200,0,4)


@pytest.mark.parametrize('kwargs',[{'ytd_cents':True},{'ytd_cents':100.9},{'elapsed_periods':1.5},
    {'total_periods':True},{'budget_phasing_cents':[300,300]},{'persistence':'banana'},
    {'variance_history_cents':[float('nan')]*6},{'actual_history_cents':[True]*8}])
def test_invalid_forecast_contract(kwargs):
    args=dict(ytd_cents=300,full_year_budget_cents=1200,elapsed_periods=1,total_periods=4)
    args.update(kwargs)
    assert 'error' in reforecast(**args)


def test_state_rejects_fractional_and_out_of_range_cents_before_writing(tmp_path):
    s=VarianceStore(str(tmp_path/'state.db'))
    try:
        for value in (300.9,True,MAX_CENTS+1):
            with pytest.raises(ValueError):s.set_budget('v1',[dict(line='A',period='2026-03-31',amount_cents=100),dict(line='B',period='2026-03-31',amount_cents=value)])
            assert s.versions('budget')==[]
        with pytest.raises(ValueError):s.record_reforecast('2026-03-31',[dict(line='A',landing_cents=10.9)])
    finally:s.close()


def test_materiality_exact_relative_boundary_and_invalid_history():
    from agent4.materiality import _is_material
    # Below big-money floor but exactly on the custom relative threshold.
    r=_is_material(300,1000,1000000,rel_pct=0.3,abs_min_frac=0.0001)
    assert r['material'] and r['cleared']=='relative % (non-trivial)'
    with pytest.raises(ValueError):classify_variance({'name':'X','total_variance_cents':100},100,1000,[True]*6)


def test_context_is_retained_and_export_is_json_serializable():
    context={'currency':'EUR','entity':'Example','source_version':'v1','close_date':'2026-03-31'}
    r=rollup({**node(),'leaf':{**line(),'context':context}})
    assert r['context']==context
    json.dumps(board_pack(r),allow_nan=False)
