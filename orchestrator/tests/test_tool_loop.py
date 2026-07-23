"""Tool loop tests (TDD §7.4)."""

from __future__ import annotations

import json

import pytest

from orchestrator.tools.loop import (
    MAX_ROUNDS,
    TOOL_CALL_SCHEMA,
    ToolCall,
    ToolError,
    ToolLoop,
    parse_tool_call,
)


def call(tool: str, **arguments) -> str:
    return json.dumps({"tool": tool, "arguments": arguments})


# --- parsing -----------------------------------------------------------------------------


def test_parses_a_grammar_constrained_call():
    parsed = parse_tool_call(call("verify_answer", expr="2x", expected="x+x"))
    assert parsed == ToolCall("verify_answer", {"expr": "2x", "expected": "x+x"})


def test_parses_a_fenced_block_when_the_grammar_was_not_applied():
    """A dropped `response_format` should degrade to a working turn, not a crash."""
    text = "Let me check that.\n```json\n" + call("lookup", query="quadratics") + "\n```"
    assert parse_tool_call(text).tool == "lookup"


def test_plain_prose_is_not_a_tool_call():
    assert parse_tool_call("Let's factorise together. What multiplies to 6?") is None
    assert parse_tool_call("") is None


def test_explicit_none_ends_the_loop():
    assert parse_tool_call(json.dumps({"tool": "none", "arguments": {}})) is None


def test_malformed_json_is_not_a_tool_call():
    assert parse_tool_call('{"tool": "lookup", "arguments":') is None


def test_schema_enumerates_exactly_the_four_tools():
    tools = TOOL_CALL_SCHEMA["schema"]["properties"]["tool"]["enum"]
    assert set(tools) == {"verify_answer", "render_diagram", "lookup", "set_mode", "none"}


# --- the loop ----------------------------------------------------------------------------


def scripted(*replies: str):
    """A model that says these things in order, then repeats the last one."""
    queue = list(replies)
    seen: list[list[dict]] = []

    def generate(messages, *, structured=True):
        seen.append(list(messages))
        return queue.pop(0) if len(queue) > 1 else queue[0]

    generate.seen = seen  # type: ignore[attr-defined]
    return generate


def test_a_turn_with_no_tool_call_returns_immediately():
    generate = scripted("The answer is 4.")
    outcome = ToolLoop(generate, {}).run([{"role": "user", "content": "2+2?"}])
    assert outcome.reply == "The answer is 4." and outcome.rounds == 0 and not outcome.results


def test_tool_result_is_appended_and_the_model_re_enters():
    generate = scripted(call("verify_answer", expr="4", expected="4"), "Confirmed: 4.")
    loop = ToolLoop(generate, {"verify_answer": lambda expr, expected: {"equivalent": True}})
    outcome = loop.run([{"role": "user", "content": "2+2?"}])

    assert outcome.reply == "Confirmed: 4." and outcome.rounds == 1
    assert outcome.used_tools == ["verify_answer"]
    second_prompt = generate.seen[1]
    assert "[tool:verify_answer]" in second_prompt[-1]["content"]
    assert "equivalent" in second_prompt[-1]["content"]


def test_rounds_are_bounded():
    """Not a safety bound — a latency one. Every extra round is a full prefill on a
    CPU-bound server, and a four-round answer has already lost the student."""
    generate = scripted(call("lookup", query="x"))  # asks forever
    loop = ToolLoop(generate, {"lookup": lambda query: ["chunk"]})
    outcome = loop.run([{"role": "user", "content": "?"}])
    assert outcome.rounds == MAX_ROUNDS and outcome.truncated
    assert len(outcome.results) == MAX_ROUNDS


def test_a_tool_that_raises_becomes_a_tool_result_not_a_500():
    def explode(**_kw):
        raise ToolError("index not built")

    generate = scripted(call("lookup", query="x"), "I could not look that up, but here is the idea.")
    outcome = ToolLoop(generate, {"lookup": explode}).run([{"role": "user", "content": "?"}])
    assert outcome.results[0].ok is False and "index not built" in outcome.results[0].error
    assert "ERROR" in outcome.results[0].as_message()["content"]
    assert outcome.reply.startswith("I could not")


def test_an_unexpected_exception_is_also_contained():
    generate = scripted(call("lookup", query="x"), "done")
    outcome = ToolLoop(generate, {"lookup": lambda **_k: 1 / 0}).run([{"role": "user", "content": "?"}])
    assert outcome.results[0].ok is False and "ZeroDivisionError" in outcome.results[0].error


def test_wrong_arguments_come_back_to_the_model_in_a_fixable_form():
    generate = scripted(call("lookup", quorry="typo"), "done")
    outcome = ToolLoop(generate, {"lookup": lambda query: []}).run([{"role": "user", "content": "?"}])
    assert "bad arguments" in outcome.results[0].error


def test_unknown_tool_is_named():
    generate = scripted(call("summon_demon"), "done")
    outcome = ToolLoop(generate, {}).run([{"role": "user", "content": "?"}])
    assert "unknown tool 'summon_demon'" in outcome.results[0].error


def test_set_mode_is_recorded_without_calling_a_tool():
    """Adapter switching costs nothing to run but invalidates cache reuse from where it
    appears, which is why the prompt layout attaches it at the semi-static boundary (§7.3)."""
    generate = scripted(call("set_mode", adapter="marking-mode"), "Marking now.")
    outcome = ToolLoop(generate, {}).run([{"role": "user", "content": "mark this"}])
    assert outcome.mode == "marking-mode"
    assert outcome.results[0].ok and outcome.results[0].content == {"mode": "marking-mode"}


def test_the_final_round_asks_for_prose_not_structured_output():
    """The last generate() call must not be grammar-constrained, or the turn ends as JSON on
    the student's screen."""
    generate = scripted(call("lookup", query="x"))
    ToolLoop(generate, {"lookup": lambda query: []}, max_rounds=1).run([{"role": "user", "content": "?"}])
    assert len(generate.seen) == 2


@pytest.mark.parametrize("bad", ['{"tool": "lookup", "arguments": "not-an-object"}', "{}"])
def test_structurally_wrong_calls_are_ignored_rather_than_crashing(bad):
    assert parse_tool_call(bad) is None
