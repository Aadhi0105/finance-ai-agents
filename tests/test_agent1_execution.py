"""Execution contracts: adversarial responses, durable checkpoints and isolation."""
from copy import deepcopy
from types import SimpleNamespace
import json
import pytest
from agent.loop import run_agent
from agent.models import ModelResponse, TextBlock, ToolUseBlock, StubModel, AnthropicModel
from agent.state import RunState
from tools.input_validation import validate_input


class Registry:
    def __init__(self, fail=None):
        self.inputs = []
        self.fail = fail

    def schemas(self):
        return [{'name': 'sample', 'input_schema': {'type': 'object', 'properties': {
            'count': {'type': 'integer', 'minimum': 1}}, 'required': ['count'],
            'additionalProperties': False}}]

    def dispatch(self, name, args):
        self.inputs.append(deepcopy(args))
        if self.fail:
            raise self.fail('SECRET provider detail')
        return {'value': args['count']}


def execute(responses, registry=None, **kwargs):
    state = RunState('T')
    model = StubModel([lambda messages, response=r: response for r in responses])
    outcome = run_agent(model=model, registry=registry or Registry(), state=state,
                        system='system', goal='goal', **kwargs)
    return outcome, state


def request(args=None, name='sample', id='call'):
    return ModelResponse('tool_use', [ToolUseBlock(id, name, {'count': 1} if args is None else args)])


def test_completion_preserves_all_text_and_usage():
    outcome, state = execute([ModelResponse('end_turn', [TextBlock('First'), TextBlock('Second')],
                                           {'input_tokens': 12}, 'request-id')])
    assert outcome.status == 'completed'
    assert outcome.text == 'First\nSecond'
    assert state.model_turns[0]['usage'] == {'input_tokens': 12}
    assert state.model_turns[0]['request_id'] == 'request-id'
    assert state.execution_record()['configuration']['system'] == 'system'


@pytest.mark.parametrize('stop,text,reason', [('max_tokens','partial','max_tokens'),
    ('refusal','refused','refusal'), ('end_turn','  ','empty_answer'),
    ('script_exhausted','','script_exhausted')])
def test_noncompletion_is_explicit(stop, text, reason):
    outcome, _ = execute([ModelResponse(stop, [TextBlock(text)])])
    assert (outcome.status, outcome.reason) == ('incomplete', reason)


@pytest.mark.parametrize('args', [{}, {'count': True}, {'count': 0}, {'count': '1'},
                                  {'count': 1, 'extra': 'secret'}, []])
def test_bad_arguments_are_recorded_without_dispatch(args):
    registry = Registry()
    outcome, state = execute([request(args), ModelResponse('end_turn', [TextBlock('done')])], registry)
    assert outcome.status == 'completed'
    assert not registry.inputs
    assert state.calls[0]['status'] == 'error'
    assert state.conversation[2]['content'][0]['is_error'] is True
    json.loads(state.conversation[2]['content'][0]['content'])


def test_nonfinite_arguments_rejected():
    assert validate_input({}, {'value': float('nan')})


@pytest.mark.parametrize('name,fail', [('unknown',None), ('sample',RuntimeError)])
def test_unknown_or_throwing_tool_has_sanitized_failure(name, fail):
    outcome, state = execute([request(name=name)], Registry(fail))
    assert outcome.status == 'incomplete'
    assert state.calls[0]['status'] == 'error'
    assert 'SECRET' not in json.dumps(state.execution_record()) + json.dumps(state.calls)


@pytest.mark.parametrize('response', [ModelResponse('tool_use', []),
    ModelResponse('end_turn', [ToolUseBlock('a','sample',{'count':1})]),
    ModelResponse('tool_use', [ToolUseBlock('a','sample',{}), ToolUseBlock('a','sample',{})])])
def test_invalid_tool_protocol_fails(response):
    outcome, state = execute([response])
    assert outcome.reason == 'invalid_tool_protocol'
    assert outcome.status == 'failed'
    assert not state.calls


def test_iteration_limit_is_not_completion():
    outcome, state = execute([request()], max_iters=1)
    assert (outcome.status, outcome.reason) == ('incomplete', 'iteration_limit')
    assert len(state.calls) == 1


def test_tool_interruption_is_durable():
    checkpoints = []
    outcome, state = execute([request()], Registry(KeyboardInterrupt),
                            checkpoint=lambda s: checkpoints.append(s.execution_record()))
    assert (outcome.status, outcome.reason) == ('incomplete', 'interrupted')
    assert state.calls[0]['output']['error_type'] == 'interrupted'
    assert checkpoints[-1]['conversation'][-1]['content'][0]['is_error']


@pytest.mark.parametrize('error,status', [(RuntimeError,'failed'), (KeyboardInterrupt,'incomplete')])
def test_model_failure_is_durable(error, status):
    def respond(**kwargs):
        raise error('SECRET')
    state = RunState('T')
    saved = []
    outcome = run_agent(model=SimpleNamespace(respond=respond), registry=Registry(), state=state,
                        system='s',goal='g',checkpoint=lambda s: saved.append(s.execution_record()))
    assert outcome.status == status
    assert saved[-1]['status'] == status
    assert 'SECRET' not in json.dumps(saved)


def test_checkpoint_failure_prevents_model_call():
    calls = []
    def checkpoint(state):
        raise OSError('disk full')
    with pytest.raises(OSError):
        run_agent(model=SimpleNamespace(respond=lambda **kw: calls.append(kw)), registry=Registry(),
                  state=RunState('T'), system='s', goal='g', checkpoint=checkpoint)
    assert not calls


def test_audit_snapshots_are_detached_and_dependencies_invalidated():
    state = RunState('T')
    args, output = {'ticker':'T'}, {'value':[1]}
    state.record_tool('get_prices', args, output)
    args['ticker'] = 'other'; output['value'].append(2)
    state.results['get_prices']['value'].append(3)
    exposed = state.calls; exposed[0]['output']['value'].append(4)
    assert state.calls[0]['input'] == {'ticker':'T'}
    assert state.calls[0]['output'] == {'value':[1]}
    for name in ['compute_ratios','run_dcf','peer_outlier_check','compute_derived']:
        state.record_tool(name, {}, {'value':1})
    state.record_tool('get_prices', {}, {'error':'unavailable'})
    assert set(state.results) == {'get_prices'}
    assert len(state.calls) == 6
    assert len(state.invalidations[-1]['removed']) == 4


def test_terminal_checkpoint_preserves_note(tmp_path):
    import run
    state = RunState('T'); state.finish('completed','saved answer','end_turn')
    path = run._snapshot('T','offline','',state,str(tmp_path))
    assert json.loads(open(path).read())['note_template'] == 'saved answer'


def test_model_adapter_metadata_and_unsupported_blocks():
    model = AnthropicModel(model='test')
    response = SimpleNamespace(content=[TextBlock('done')],stop_reason='end_turn',
        usage=SimpleNamespace(model_dump=lambda: {'output_tokens':3}), id='id')
    model._client = SimpleNamespace(messages=SimpleNamespace(create=lambda **kw: response))
    result = model.respond('s',[],[])
    assert result.usage == {'output_tokens':3} and result.request_id == 'id'
    response.content.append(SimpleNamespace(type='thinking'))
    with pytest.raises(RuntimeError):
        model.respond('s',[],[])


def test_shared_triage_interface_stays_string(monkeypatch):
    from monitoring import triage
    from agent.state import RunOutcome
    rows = [{'status':'watch','item_id':'a','entity':'A','metric':'ratio'}]
    monkeypatch.setattr(triage,'run_agent',lambda **kw: RunOutcome('completed','triage note'))
    assert triage.run_triage(None,rows) == 'triage note'
    monkeypatch.setattr(triage,'run_agent',lambda **kw: RunOutcome('incomplete','partial','max_tokens'))
    assert triage.run_triage(None,rows) == '[triage incomplete: max_tokens] partial'


def test_registry_blocks_subject_change_before_provider(monkeypatch):
    from tools.registry import ToolRegistry
    registry = ToolRegistry(RunState('T'))
    schema, _ = registry._reg['get_prices']
    registry._reg['get_prices'] = (schema, lambda *args: pytest.fail('provider called'))
    assert registry.dispatch('get_prices', {'ticker':'OTHER'})['error_type'] == 'ticker_mismatch'
    assert registry.dispatch('get_prices', {'ticker':'../T'})['error_type'] == 'invalid_arguments'


def test_second_tool_checkpoint_keeps_first_result():
    saved = []
    response = ModelResponse('tool_use', [ToolUseBlock('a','sample',{'count':1}),
                                        ToolUseBlock('b','sample',{'count':2})])
    execute([response], checkpoint=lambda s: saved.append(s.execution_record()))
    second = next(s for s in saved if (s['in_flight'] or {}).get('tool_use_id') == 'b')
    assert second['conversation'][-1]['content'][0]['tool_use_id'] == 'a'
