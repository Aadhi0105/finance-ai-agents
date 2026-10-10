"""Acceptance harness checks; expected financial answers are not engine outputs."""
from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path

import pytest
from scripts import check_keystone_financial as acceptance


def plan():return acceptance.read(acceptance.PLAN)


def test_frozen_plan_and_sources():
    p=plan()
    assert acceptance.sha(acceptance.PLAN)==acceptance.FROZEN_SHA
    for name,digest in p['source_hashes'].items():assert acceptance.sha(acceptance.ROOT/name)==digest


def test_decimal_oracle_single_period_hand_calculation():
    case=dict(horizon_years=1,discount_rate=.1,terminal_growth=0,high_growth=.1)
    # Base cash 935; terminal 9,350; discount 10,285 / 1.1 = 9,350.
    assert acceptance.discounted_oracle(850,case)['base']==Decimal(9350)


def test_retained_agent1_and_negative_boundaries():
    assert acceptance.agent1(plan())['status']=='passed'


def test_agent1_oracle_detects_wrong_engine_value(monkeypatch):
    from tools import analytical
    original=analytical.run_dcf
    def damaged(*args,**kwargs):
        result=original(*args,**kwargs)
        if result.get('enterprise_value'):result['enterprise_value']['base']+=100
        return result
    monkeypatch.setattr(analytical,'run_dcf',damaged)
    with pytest.raises(AssertionError,match='numerical mismatch'):acceptance.agent1(plan())


def test_monitoring_reference_and_controlled_correction(tmp_path):
    assert acceptance.agent2(plan(),tmp_path)['status']=='passed'


def test_news_boundary_benchmark():
    result=acceptance.news(plan())
    assert result['status']=='passed' and result['mismatches']==[]
    assert result['human_reviewed'] is False and result['production_quality_accepted'] is False


def test_news_evaluator_reports_false_inclusion(monkeypatch):
    from agent3 import news_funnel
    original=news_funnel.relevance_filter
    def broken(items,*args,**kwargs):
        actual=original(items,*args,**kwargs)
        if not actual and items:
            return [{**items[0],'entities':['ASML.AS']}]
        return actual
    monkeypatch.setattr(news_funnel,'relevance_filter',broken)
    result=acceptance.news(plan())
    assert result['status']=='failed' and result['entity_label_confusion_counts']['fp']>0


def test_tolerance_comparison_refuses_missing_value():
    with pytest.raises(AssertionError):acceptance.close(None,0,.01)
