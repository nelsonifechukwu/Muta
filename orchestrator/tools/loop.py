"""The tool loop (TDD §7.4).

The model emits a tool call as JSON under a grammar; the loop runs the tool, appends the
result, and re-enters CORE. Bounded at three rounds per turn — not for safety but for
latency: on a CPU-bound server every extra round is a full prefill, and a tutoring answer
that takes four round trips has already lost the student.

Tools: `verify_answer`, `render_diagram`, `lookup` (RAG), `set_mode` (LoRA adapter).

`set_mode` is the odd one: switching an adapter costs nothing to run but invalidates prompt
cache reuse from wherever it appears in the prompt, so the layout attaches adapters at the
semi-static boundary (§7.3) and this loop only records the choice.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

MAX_ROUNDS = 3

#: The grammar the model emits under (`response_format: json_schema`, §7.4). Kept minimal:
#: every optional field is one more thing a 4B model can get wrong under a grammar.
TOOL_CALL_SCHEMA: dict[str, Any] = {
    "name": "tool_call",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "tool": {"type": "string", "enum": ["verify_answer", "render_diagram", "lookup", "set_mode", "none"]},
            "arguments": {"type": "object"},
            "rationale": {"type": "string"},
        },
        "required": ["tool", "arguments"],
        "additionalProperties": False,
    },
}


class ToolError(Exception):
    """A tool failed in a way the model should see and can act on."""


@dataclass
class ToolCall:
    tool: str
    arguments: dict[str, Any] = field(default_factory=dict)
    rationale: str = ""


@dataclass
class ToolResult:
    call: ToolCall
    ok: bool
    content: Any = None
    error: str = ""

    def as_message(self) -> dict[str, str]:
        """What gets appended to the conversation before re-entering the model."""
        body = json.dumps(self.content, default=str) if self.ok else f"ERROR: {self.error}"
        return {"role": "user", "content": f"[tool:{self.call.tool}] {body}"}


class Tool(Protocol):
    def __call__(self, **kwargs: Any) -> Any: ...


@dataclass
class TurnOutcome:
    reply: str
    rounds: int
    results: list[ToolResult] = field(default_factory=list)
    mode: str | None = None
    truncated: bool = False  # hit MAX_ROUNDS with the model still asking for tools

    @property
    def used_tools(self) -> list[str]:
        return [r.call.tool for r in self.results]


_JSON_BLOCK = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def parse_tool_call(text: str) -> ToolCall | None:
    """Read a tool call out of a model reply.

    Grammar-constrained output is a bare JSON object, but the same parser has to survive an
    un-grammared model wrapping it in a fenced block or prose — a dropped `response_format`
    should degrade to "no tool call", never to a crash mid-turn.
    """
    if not text or not text.strip():
        return None
    candidates: list[str] = []
    stripped = text.strip()
    if stripped.startswith("{"):
        candidates.append(stripped)
    candidates += _JSON_BLOCK.findall(text)
    brace = re.search(r"\{[^{}]*\"tool\"\s*:.*?\}", text, re.DOTALL)
    if brace:
        candidates.append(brace.group(0))

    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        tool = payload.get("tool")
        if not tool or tool == "none":
            return None
        arguments = payload.get("arguments") or {}
        if not isinstance(arguments, dict):
            continue
        return ToolCall(tool=str(tool), arguments=arguments, rationale=str(payload.get("rationale", "")))
    return None


class ToolLoop:
    """Runs one tutoring turn to completion, tools included.

    `generate(messages, *, structured)` is the model call — a callable rather than a client,
    so the loop is testable without an engine and so the caller keeps ownership of sampling
    profiles (§6.5) and prompt layout (§7.3).
    """

    def __init__(
        self,
        generate: Callable[..., str],
        tools: dict[str, Tool],
        *,
        max_rounds: int = MAX_ROUNDS,
    ) -> None:
        self.generate = generate
        self.tools = tools
        self.max_rounds = max_rounds

    def run(self, messages: list[dict[str, str]]) -> TurnOutcome:
        conversation = list(messages)
        results: list[ToolResult] = []
        mode: str | None = None
        reply = ""

        for round_index in range(self.max_rounds + 1):
            reply = self.generate(conversation, structured=round_index < self.max_rounds)
            call = parse_tool_call(reply)
            if call is None:
                return TurnOutcome(reply=reply, rounds=round_index, results=results, mode=mode)
            if round_index >= self.max_rounds:
                break

            if call.tool == "set_mode":
                mode = str(call.arguments.get("adapter") or call.arguments.get("mode") or "")
                result = ToolResult(call, ok=True, content={"mode": mode})
            else:
                result = self._invoke(call)
            results.append(result)
            conversation = conversation + [{"role": "assistant", "content": reply}, result.as_message()]

        # Out of rounds with the model still asking for tools: answer with what we have
        # rather than looping. The student gets a slightly weaker answer instead of a hang.
        return TurnOutcome(reply=reply, rounds=self.max_rounds, results=results, mode=mode, truncated=True)

    def _invoke(self, call: ToolCall) -> ToolResult:
        tool = self.tools.get(call.tool)
        if tool is None:
            return ToolResult(call, ok=False, error=f"unknown tool {call.tool!r}")
        try:
            return ToolResult(call, ok=True, content=tool(**call.arguments))
        except TypeError as e:  # wrong/missing arguments — the model can fix this itself
            return ToolResult(call, ok=False, error=f"bad arguments: {e}")
        except ToolError as e:
            return ToolResult(call, ok=False, error=str(e))
        except Exception as e:  # noqa: BLE001 — a tool crash is a tool result, not a 500
            return ToolResult(call, ok=False, error=f"{type(e).__name__}: {e}")
