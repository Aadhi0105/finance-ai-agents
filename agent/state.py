"""Run state with detached audit snapshots and dependency invalidation."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any

DEPENDENCIES = {
    'compute_ratios': ('get_financials', 'get_prices'),
    'run_dcf': ('get_financials', 'get_prices'),
    'peer_outlier_check': ('get_financials', 'get_prices'),
    'compute_derived': ('get_consensus', 'run_dcf', 'get_historical_trend'),
}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class RunOutcome:
    status: str  # completed, incomplete, failed
    text: str = ''
    reason: str = ''
    iterations: int = 0


@dataclass
class RunState:
    ticker: str
    results: dict[str, Any] = field(default_factory=dict)
    _calls: list[dict] = field(default_factory=list, repr=False)
    trace: list[str] = field(default_factory=list)
    configuration: dict = field(default_factory=dict)
    conversation: list = field(default_factory=list)
    model_turns: list = field(default_factory=list)
    in_flight: dict | None = None
    started_at: str = field(default_factory=utc_now)
    finished_at: str | None = None
    outcome: RunOutcome | None = None
    invalidations: list = field(default_factory=list)

    @property
    def calls(self):
        # Consumers may inspect/serialize, but cannot mutate the stored audit trail.
        return deepcopy(self._calls)

    def record_tool(self, name: str, tool_input: Any, output: Any,
                    duration_ms: float | None = None, tool_use_id: str | None = None):
        changed = {name}
        while True:
            affected = {tool for tool, deps in DEPENDENCIES.items() if changed.intersection(deps)}
            if affected <= changed:
                break
            changed |= affected
        removed = sorted(k for k in changed - {name} if k in self.results)
        for key in removed:
            del self.results[key]
        if removed:
            self.invalidations.append({'after_call': len(self._calls), 'trigger': name, 'removed': removed})
        self.results[name] = deepcopy(output)
        status = 'error' if isinstance(output, dict) and output.get('error') else 'success'
        self._calls.append({'call_index': len(self._calls), 'tool': name,
                            'input': deepcopy(tool_input), 'output': deepcopy(output),
                            'duration_ms': duration_ms, 'tool_use_id': tool_use_id,
                            'recorded_at': utc_now(), 'status': status})
        self.record_note(f'tool {name}: {status}')

    def finish(self, status, text='', reason='', iterations=0):
        self.outcome = RunOutcome(status, text, reason, iterations)
        self.finished_at = utc_now()
        self.in_flight = None
        return self.outcome

    def execution_record(self):
        return deepcopy({'status': self.outcome.status if self.outcome else 'running',
                         'outcome': asdict(self.outcome) if self.outcome else None,
                         'started_at': self.started_at, 'finished_at': self.finished_at,
                         'configuration': self.configuration, 'conversation': self.conversation,
                         'model_turns': self.model_turns, 'in_flight': self.in_flight,
                         'invalidations': self.invalidations, 'trace': self.trace})

    def record_note(self, text):
        self.trace.append(f'NOTE  {text}')

    def print_trace(self):
        print('\n----- RUN TRACE -----')
        print('\n'.join(self.trace))
        print('----- END TRACE -----\n')
