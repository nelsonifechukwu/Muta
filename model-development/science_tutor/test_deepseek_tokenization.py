"""Native DeepSeek masking tests using the pinned public tokenizer files."""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOKENIZER = ROOT / "data/muta-science-tutor-20260919/deepseek-tokenizer"
sys.path.insert(0, str(ROOT / "model-development"))


@pytest.fixture(scope="module")
def tokenizer():
    transformers = pytest.importorskip("transformers")
    return transformers.AutoTokenizer.from_pretrained(
        TOKENIZER, local_files_only=True, trust_remote_code=False
    )


def test_direct_and_multi_turn_native_spans(tokenizer):
    from science_tutor.deepseek_tokenization import tokenize_messages

    messages = [
        {"role": "user", "content": "What is 2 plus 2?"},
        {"role": "assistant", "content": "4."},
        {"role": "user", "content": "What if one more is added?"},
        {"role": "assistant", "content": "5."},
    ]
    result = tokenize_messages(messages, tokenizer=tokenizer)
    assert result["assistant_turns"] == 2
    assert result["trainable_tokens"] > 0
    assert all(x == -100 for x in result["labels"][: result["assistant_spans"][0]["start"]])


def test_system_and_think_markers_fail_closed(tokenizer):
    from science_tutor.deepseek_tokenization import tokenize_messages
    from science_tutor.tokenization import TokenizationError

    with pytest.raises(TokenizationError, match="system"):
        tokenize_messages(
            [
                {"role": "system", "content": "Be helpful."},
                {"role": "user", "content": "What is 2 plus 2?"},
                {"role": "assistant", "content": "4."},
            ],
            tokenizer=tokenizer,
        )
    with pytest.raises(TokenizationError, match="control"):
        tokenize_messages(
            [
                {"role": "user", "content": "What is 2 plus 2?"},
                {"role": "assistant", "content": "<think>2+2</think>4."},
            ],
            tokenizer=tokenizer,
        )


def test_current_pilot_rows_have_no_native_control_and_are_admissible(tokenizer):
    from science_tutor.deepseek_tokenization import tokenize_messages

    path = ROOT / "data/muta-science-tutor-20260919/pilot-v1/train.jsonl"
    with path.open(encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle]
    counts = [tokenize_messages(row["messages"], tokenizer=tokenizer) for row in rows]
    assert len(counts) == 8002
    assert max(item["sequence_tokens"] for item in counts) <= 4096
    assert sum(item["trainable_tokens"] for item in counts) == 247128
