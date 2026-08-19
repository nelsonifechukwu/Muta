from __future__ import annotations

import pytest

from bench.ppl_bakeoff import parse_ppl


def test_parse_ppl_accepts_llama_cpp_final_line():
    output = "4.35.590 I Final estimate: PPL = 10.5814 +/- 0.50993\n"
    assert parse_ppl(output) == (10.5814, 0.50993)


def test_parse_ppl_fails_closed_without_final_line():
    with pytest.raises(ValueError, match="no final estimate"):
        parse_ppl("loading model then crashed")
