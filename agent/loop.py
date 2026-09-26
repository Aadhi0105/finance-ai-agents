"""Bounded shared model/tool loop with explicit completion and checkpointing."""
from __future__ import annotations

from copy import deepcopy
import json
import time
from agent.state import RunOutcome, utc_now
from tools.input_validation import validate_input

MAX_ITERS = 12


def run_agent(*, model, registry, state, system: str, goal: str, checkpoint=None,
              max_iters: int = MAX_ITERS, final_feedback=None) -> RunOutcome:
    """Only end_turn with nonempty text completes. All other exits are explicit.

    Checkpoint errors deliberately propagate: never continue a paid run after
    losing the ability to save its audit record. Tool/model errors are recorded
    without exception messages, which can expose credentials or response bodies.
    """
    if type(max_iters) is not int or max_iters < 1:
        raise ValueError('max_iters must be a positive integer')
    messages = [{'role': 'user', 'content': goal}]
    schemas = registry.schemas()
    menu = {s['name']: s['input_schema'] for s in schemas}
    state.configuration.update(system=system, goal=goal, tools=deepcopy(schemas),
                               model_id=getattr(model, 'model', type(model).__name__),
                               max_tokens=getattr(model, 'max_tokens', None), max_iters=max_iters)

    def save():
        state.conversation = deepcopy(messages)
        if checkpoint:
            checkpoint(state)

    def finish(status, text, reason, iterations):
        result = state.finish(status, text, reason, iterations)
        save()
        return result

    save()
    partial = ''
    revision_requested = False
    state.configuration['max_narrative_revisions'] = 1 if final_feedback else 0
    seen_ids = set()
    for iteration in range(max_iters):
        state.record_note(f'iteration {iteration}: asking model')
        state.in_flight = {'kind': 'model', 'iteration': iteration, 'started_at': utc_now()}
        save()
        started = time.perf_counter()
        try:
            response = model.respond(system=system, messages=deepcopy(messages), tools=deepcopy(schemas))
        except KeyboardInterrupt:
            return finish('incomplete', partial, 'interrupted', iteration + 1)
        except Exception as exc:
            state.model_turns.append({'iteration': iteration, 'error_type': type(exc).__name__,
                                      'duration_ms': round((time.perf_counter() - started) * 1000, 2)})
            return finish('failed', partial, 'model_error', iteration + 1)
        state.in_flight = None
        try:
            blocks = _blocks_to_api(response.content)
            stop = response.stop_reason
            usage = deepcopy(getattr(response, 'usage', {}))
            json.dumps({'blocks': blocks, 'usage': usage}, allow_nan=False)
        except Exception:
            return finish('failed', partial, 'invalid_model_response', iteration + 1)
        state.model_turns.append({'iteration': iteration, 'stop_reason': stop,
                                  'request_id': getattr(response, 'request_id', None), 'usage': usage,
                                  'duration_ms': round((time.perf_counter() - started) * 1000, 2)})
        messages.append({'role': 'assistant', 'content': blocks})
        partial = '\n'.join(b['text'] for b in blocks if b['type'] == 'text')
        requested = [b for b in blocks if b['type'] == 'tool_use']
        save()
        if revision_requested and requested:
            return finish('incomplete', partial, 'narrative_revision_requested_tools', iteration + 1)
        if stop == 'end_turn' and not requested:
            if partial.strip() and final_feedback and not revision_requested:
                feedback = final_feedback(partial, state.results)
                if feedback and iteration + 1 < max_iters:
                    revision_requested = True
                    messages.append({'role': 'user', 'content': feedback})
                    state.record_note('narrative validation failed; requested the single allowed revision')
                    save()
                    continue
            return finish('completed' if partial.strip() else 'incomplete', partial,
                          'end_turn' if partial.strip() else 'empty_answer', iteration + 1)
        if stop == 'end_turn' and requested:
            return finish('failed', partial, 'invalid_tool_protocol', iteration + 1)
        if stop != 'tool_use':
            return finish('incomplete', partial, str(stop or 'unknown_stop_reason'), iteration + 1)
        if not requested or any(not isinstance(b['id'], str) or not b['id'] or b['id'] in seen_ids for b in requested) or len({b['id'] for b in requested}) != len(requested):
            return finish('failed', partial, 'invalid_tool_protocol', iteration + 1)
        tool_results = []
        for block in requested:
            seen_ids.add(block['id'])
            name, arguments = block['name'], block['input']
            state.in_flight = {'kind': 'tool', 'name': name, 'input': deepcopy(arguments),
                               'tool_use_id': block['id'], 'started_at': utc_now()}
            state.conversation = deepcopy(messages + ([{'role': 'user', 'content': tool_results}] if tool_results else []))
            if checkpoint:
                checkpoint(state)
            started = time.perf_counter()
            interrupted = False
            try:
                error = validate_input(menu[name], arguments) if name in menu else 'unknown tool'
                output = {'error': error, 'error_type': 'invalid_arguments'} if error else registry.dispatch(name, deepcopy(arguments))
                if not isinstance(output, dict):
                    output = {'error': 'tool must return an object', 'error_type': 'invalid_output'}
                json.dumps(output, allow_nan=False)
            except KeyboardInterrupt:
                output = {'error': 'tool interrupted', 'error_type': 'interrupted'}
                interrupted = True
            except Exception as exc:
                output = {'error': 'tool execution failed', 'error_type': type(exc).__name__}
            state.record_tool(name, arguments, output,
                              duration_ms=round((time.perf_counter() - started) * 1000, 2), tool_use_id=block['id'])
            state.in_flight = None
            tool_results.append({'type': 'tool_result', 'tool_use_id': block['id'],
                                 'content': json.dumps(output, allow_nan=False), 'is_error': bool(output.get('error'))})
            # Include partial tool results in the checkpoint, without sending an
            # incomplete batch back to the model if execution is interrupted.
            state.conversation = deepcopy(messages + [{'role': 'user', 'content': tool_results}])
            if checkpoint:
                checkpoint(state)
            if interrupted:
                messages.append({'role': 'user', 'content': tool_results})
                return finish('incomplete', partial, 'interrupted', iteration + 1)
        messages.append({'role': 'user', 'content': tool_results})
    return finish('incomplete', partial, 'iteration_limit', max_iters)


def _blocks_to_api(blocks):
    out = []
    for b in blocks:
        if b.type == 'tool_use':
            if not isinstance(b.name, str):
                raise ValueError('invalid tool name')
            out.append({'type': 'tool_use', 'id': b.id, 'name': b.name, 'input': deepcopy(b.input)})
        elif b.type == 'text' and isinstance(b.text, str):
            out.append({'type': 'text', 'text': b.text})
        else:
            raise ValueError('unsupported content block')
    return out
