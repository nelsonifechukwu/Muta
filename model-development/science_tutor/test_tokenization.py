"""Boundary tests plus a real local upstream-Qwen tokenizer integration test."""

import copy
import hashlib
import os
import sys
from collections.abc import Mapping
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from science_tutor.tokenization import TokenizationError, tokenize_messages


class TinyTokenizer:
    chat_template = "tiny-explicit-role-header-template-v1"
    eos_token_id = 3
    pad_token_id = 0
    all_special_tokens = ("<EOS>",)

    def apply_chat_template(
        self, messages, *, tokenize, add_generation_prompt, truncation, padding
    ):
        assert tokenize and not truncation and not padding
        roles = {"system": 10, "user": 11, "assistant": 12}
        tokens = []
        for message in messages:
            tokens += [roles[message["role"]], 13]
            tokens += [100 + ord(c) for c in message["content"]]
            tokens += [self.eos_token_id, 14]
        if add_generation_prompt:
            tokens += [roles["assistant"], 13]
        return tokens


def conversation():
    return [
        {"role": "system", "content": "Explain carefully."},
        {"role": "user", "content": "Why?"},
        {"role": "assistant", "content": "First answer."},
        {"role": "user", "content": "What about the exception?"},
        {"role": "assistant", "content": "Second answer: α = ½."},
    ]


def test_every_assistant_turn_headers_eos_and_history():
    messages = conversation()
    original = copy.deepcopy(messages)
    tokenizer = TinyTokenizer()
    result = tokenize_messages(messages, tokenizer=tokenizer)
    assert messages == original
    assert result["assistant_turns"] == 2
    wanted = []
    for index, message in enumerate(messages):
        if message["role"] == "assistant":
            wanted += [100 + ord(c) for c in message["content"]] + [3, 14]
    assert [x for x in result["labels"] if x != -100] == wanted
    for role in (10, 11, 12, 13):
        assert all(
            label == -100
            for token, label in zip(result["input_ids"], result["labels"])
            if token == role
        )
    assert result["trainable_tokens"] == len(wanted)
    assert result["sequence_tokens"] == len(result["input_ids"])
    assert result["attention_mask"] == [1] * result["sequence_tokens"]


def test_system_optional_and_one_turn():
    result = tokenize_messages(conversation()[1:3], tokenizer=TinyTokenizer())
    assert result["assistant_turns"] == 1


@pytest.mark.parametrize(
    "messages",
    [
        [],
        [{"role": "system", "content": "s"}],
        [{"role": "user", "content": "u"}],
        [{"role": "assistant", "content": "a"}, {"role": "user", "content": "u"}],
        [{"role": "user", "content": "u"}, {"role": "system", "content": "s"}],
        [{"role": "user", "content": "u"}, {"role": "assistant", "content": ""}],
        [{"role": "user", "content": ["image"]}, {"role": "assistant", "content": "a"}],
        [{"role": "user", "content": "u", "name": "hidden"}, {"role": "assistant", "content": "a"}],
        [{"role": "user", "content": "u"}, {"role": "tool", "content": "a"}],
    ],
)
def test_invalid_roles_partial_turns_and_hidden_fields_rejected(messages):
    with pytest.raises(TokenizationError):
        tokenize_messages(messages, tokenizer=TinyTokenizer())


def test_repeated_system_and_control_tokens_rejected():
    messages = conversation()
    messages[3]["role"] = "system"
    with pytest.raises(TokenizationError):
        tokenize_messages(messages, tokenizer=TinyTokenizer())
    messages = conversation()
    messages[2]["content"] = "literal <EOS> control token"
    with pytest.raises(TokenizationError, match="control token"):
        tokenize_messages(messages, tokenizer=TinyTokenizer())


def test_no_silent_truncation_exact_limit_or_one_less():
    messages = conversation()
    count = tokenize_messages(messages, tokenizer=TinyTokenizer())["sequence_tokens"]
    assert (
        tokenize_messages(messages, tokenizer=TinyTokenizer(), max_length=count)["sequence_tokens"]
        == count
    )
    with pytest.raises(TokenizationError, match="no truncation"):
        tokenize_messages(messages, tokenizer=TinyTokenizer(), max_length=count - 1)


def test_prefix_instability_fails_closed_not_longest_common_prefix():
    class Unstable(TinyTokenizer):
        def apply_chat_template(self, messages, **kwargs):
            result = super().apply_chat_template(messages, **kwargs)
            if kwargs["add_generation_prompt"]:
                result[-1] = 999
            return result

    with pytest.raises(TokenizationError, match="prefix-stable"):
        tokenize_messages(conversation(), tokenizer=Unstable())


def test_missing_eos_or_template_rejected():
    tokenizer = TinyTokenizer()
    tokenizer.chat_template = None
    with pytest.raises(TokenizationError, match="template"):
        tokenize_messages(conversation(), tokenizer=tokenizer)

    class WrongEOS(TinyTokenizer):
        def apply_chat_template(self, messages, **kwargs):
            return [99 if x == 3 else x for x in super().apply_chat_template(messages, **kwargs)]

    with pytest.raises(TokenizationError, match="EOS"):
        tokenize_messages(conversation(), tokenizer=WrongEOS())


def test_actual_common_qwen_tokenizer_multiturn_integration():
    default = Path(__file__).resolve().parents[2] / "data/muta-science-tutor-20260919/tokenizer"
    path = Path(os.environ.get("SCIENCE_TUTOR_TOKENIZER", default))
    if not path.is_dir():
        pytest.skip("set SCIENCE_TUTOR_TOKENIZER to the staged common upstream tokenizer")
    from science_tutor.train import TOKENIZER_FILES
    from transformers import AutoTokenizer

    for name, sha in TOKENIZER_FILES.items():
        assert hashlib.sha256((path / name).read_bytes()).hexdigest() == sha
    tokenizer = AutoTokenizer.from_pretrained(path, local_files_only=True, trust_remote_code=False)
    messages = conversation()
    result = tokenize_messages(messages, tokenizer=tokenizer, max_length=4096)
    direct = tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=False)
    if isinstance(direct, Mapping):
        direct = direct["input_ids"]
    assert result["input_ids"] == direct
    assert result["assistant_turns"] == 2
    for span, expected in zip(result["assistant_spans"], (messages[2], messages[4])):
        start, stop = span["start"], span["stop"]
        text = tokenizer.decode(result["labels"][start:stop], skip_special_tokens=False)
        assert text == expected["content"] + "<|im_end|>\n"
        assert result["labels"][start - 1] == -100
        assert tokenizer.eos_token_id in result["input_ids"][start:stop]
    supervised = tokenizer.decode([x for x in result["labels"] if x != -100])
    assert "Explain carefully" not in supervised and "What about" not in supervised
    assert "First answer." in supervised and "Second answer" in supervised
    with pytest.raises(TokenizationError, match="no truncation"):
        tokenize_messages(messages, tokenizer=tokenizer, max_length=result["sequence_tokens"] - 1)
