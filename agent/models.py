"""
Model clients for the agent loop.

Design principle: the orchestrator (agent/loop.py) is model-agnostic. It only
knows that a model, given (messages, tools), returns a response object with:
    .stop_reason   -> "tool_use" | "end_turn"
    .content       -> list of blocks, each with .type in {"text","tool_use"}
                      tool_use blocks additionally carry .id, .name, .input
                      text blocks carry .text

Both StubModel and AnthropicModel return objects of exactly this shape, so the
loop code in loop.py is identical regardless of which one is plugged in. That is
the whole point: we can prove the loop mechanics offline with a scripted model,
then swap in the real API by changing one factory call.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable
import os


# --- minimal response shape shared by both models -------------------------

@dataclass
class TextBlock:
    text: str
    type: str = "text"


@dataclass
class ToolUseBlock:
    id: str
    name: str
    input: dict
    type: str = "tool_use"


@dataclass
class ThinkingBlock:
    """A thinking or redacted_thinking block, kept opaque.

    Models with always-on thinking return these alongside text and tool_use
    blocks. The API requires them to be sent back unchanged on the next turn of
    a tool loop, so the loop replays `raw` verbatim and never reads or edits it.
    """
    type: str
    raw: dict


@dataclass
class ModelResponse:
    stop_reason: str          # "tool_use" or "end_turn"
    content: list             # list[TextBlock | ToolUseBlock]
    usage: dict = field(default_factory=dict)
    request_id: str | None = None


THINKING_TYPES = ("thinking", "redacted_thinking")
SUPPORTED_TYPES = ("text", "tool_use") + THINKING_TYPES


# --- interface ------------------------------------------------------------

class ModelClient:
    """A model the loop can drive. Implement .respond()."""

    def respond(self, system: str, messages: list, tools: list) -> ModelResponse:
        raise NotImplementedError


# --- offline: scripted model, proves the loop with no key / no network ----

class StubModel(ModelClient):
    """
    A model whose turns are scripted, not inferred. Used to prove the loop's
    plumbing deterministically: it emits a fixed sequence of tool calls, then a
    final text answer. It never touches the network and needs no API key.

    `script` is a list of callables. Each callable receives the current
    `messages` list and returns a ModelResponse. This lets a scripted turn read
    prior tool results if we want it to, while staying fully deterministic.
    """

    def __init__(self, script: list[Callable[[list], ModelResponse]]):
        self._script = list(script)
        self._i = 0

    def respond(self, system: str, messages: list, tools: list) -> ModelResponse:
        if self._i >= len(self._script):
            # Exhaustion is an explicit incomplete run, never a fabricated answer.
            return ModelResponse(
                stop_reason="script_exhausted",
                content=[],
            )
        step = self._script[self._i]
        self._i += 1
        return step(messages)


# --- live: real Anthropic tool-use API ------------------------------------

class AnthropicModel(ModelClient):
    """
    Live model over the raw Anthropic Messages API. Imports the SDK lazily so
    this module still imports fine in an environment where `anthropic` isn't
    installed (e.g. the offline scaffold). On your Mac: `pip install anthropic`
    and set ANTHROPIC_API_KEY, and this path lights up with zero loop changes.
    """

    def __init__(self, model: str | None = None, max_tokens: int = 4000):
        # Model string is read from AGENT_MODEL so you never hardcode a value
        # that goes stale on the next release. Confirm the exact string your key
        # can call with:  curl https://api.anthropic.com/v1/models -H "x-api-key: $ANTHROPIC_API_KEY" -H "anthropic-version: 2023-06-01"
        # Claude Opus 5.5 always thinks: responses can include thinking blocks,
        # which are carried as opaque ThinkingBlocks and replayed unchanged.
        self.model = model or os.environ.get("AGENT_MODEL", "claude-opus-5-5")
        self.max_tokens = max_tokens
        self._client = None

    def _lazy_client(self):
        if self._client is None:
            import anthropic  # lazy: only needed on the live path
            # 60s timeout: a bad model / network stall FAILS FAST with a clear error
            # instead of hanging silently.
            self._client = anthropic.Anthropic(
                api_key=os.environ["ANTHROPIC_API_KEY"], timeout=60.0, max_retries=0)
        return self._client

    def respond(self, system: str, messages: list, tools: list) -> ModelResponse:
        from keystone.budget import reserve, report
        reservation = reserve(self.model, self.max_tokens, system, messages, tools)
        client = self._lazy_client()
        resp = client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            tools=tools,
            messages=messages,
        )
        report(reservation, resp.usage.model_dump() if resp.usage else {})
        # The real SDK blocks already expose .type/.id/.name/.input/.text, so we
        # can hand them straight to the loop. We normalise into our own dataclasses
        # to keep a single, explicit shape the loop depends on.
        blocks = []
        for b in resp.content:
            if b.type == "tool_use":
                blocks.append(ToolUseBlock(id=b.id, name=b.name, input=dict(b.input)))
            elif b.type == "text":
                blocks.append(TextBlock(text=b.text))
            elif b.type in THINKING_TYPES:
                blocks.append(ThinkingBlock(type=b.type, raw=b.model_dump(exclude_none=True)))
            # Reject unsupported blocks below, including mixed responses.
        if any(getattr(b, "type", None) not in SUPPORTED_TYPES for b in resp.content):
            kinds = sorted({getattr(b, "type", "?") for b in resp.content})
            raise RuntimeError(
                f"model returned unsupported block types {kinds}; set AGENT_MODEL "
                f"to a model that returns only text, tool_use and thinking blocks.")
        return ModelResponse(stop_reason=resp.stop_reason, content=blocks,
                             usage=resp.usage.model_dump() if resp.usage else {},
                             request_id=getattr(resp, "_request_id", None) or getattr(resp, "id", None))
