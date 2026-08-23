from orchestrator.gateway.resource_citations import (
    finalize_resource_reply,
    retain_persisted_resource_sources,
)


def _sources(count: int) -> list[dict]:
    return [
        {
            "resource_id": f"{index:032x}",
            "title": "book.pdf",
            "page": index,
            "chunk_index": index - 1,
            "excerpt": f"evidence {index}",
        }
        for index in range(1, count + 1)
    ]


def test_sparse_reference_forms_are_canonicalized_and_renumbered_by_first_use():
    reply, sources = finalize_resource_reply(
        "First claim (R5). Second claim uses [R3]. Repeat [R5].", _sources(5)
    )

    assert reply == "First claim [R1]. Second claim uses [R2]. Repeat [R1]."
    assert [source["page"] for source in sources] == [5, 3]


def test_every_returned_source_has_an_inline_marker_and_unused_hits_are_not_claimed():
    reply, sources = finalize_resource_reply("Supported claim [R2].", _sources(3))

    assert reply == "Supported claim [R1]."
    assert [source["page"] for source in sources] == [2]
    assert all(f"[R{index}]" in reply for index in range(1, len(sources) + 1))


def test_unknown_references_never_create_destinations_or_leak_raw_codes():
    reply, sources = finalize_resource_reply(
        "A claim [R9]. Connect resistor R1 to resistor R2. Another (R7).", _sources(2)
    )

    assert reply == "A claim. Connect resistor R1 to resistor R2. Another."
    assert sources == []
    assert "R9" not in reply and "R7" not in reply


def test_model_citation_self_check_is_removed_before_persistence():
    reply, sources = finalize_resource_reply(
        "Grounded answer [R3]. *(Self-check: Is this based on R3? Yes.)*", _sources(3)
    )

    assert reply == "Grounded answer [R1]."
    assert [source["page"] for source in sources] == [3]
    assert "Self-check" not in reply


def test_omitted_marker_is_recovered_only_for_an_exact_supporting_sentence():
    sources = _sources(2)
    sources[0]["excerpt"] = "Applicants should demonstrate leadership experience."
    sources[1]["excerpt"] = "An unrelated discussion of engineering jobs."

    reply, cited = finalize_resource_reply(
        "Applicants should demonstrate leadership experience.", sources
    )

    assert reply == "Applicants should demonstrate leadership experience [R1]."
    assert [source["page"] for source in cited] == [1]


def test_generic_exact_fragments_do_not_gain_citation_authority():
    for text in ("It is possible.", "The cat is red."):
        source = _sources(1)
        source[0]["excerpt"] = text
        reply, cited = finalize_resource_reply(text, source)
        assert reply == text
        assert cited == []


def test_structural_markdown_prefixes_do_not_hide_exact_support():
    source = _sources(1)
    source[0]["excerpt"] = "Applicants should demonstrate leadership experience."
    for prefix in ("- ", "+ ", "> ", "## "):
        reply, cited = finalize_resource_reply(
            f"{prefix}Applicants should demonstrate leadership experience.", source
        )
        assert "[R1]" in reply
        assert [item["page"] for item in cited] == [1]


def test_combining_script_evidence_matches_browser_threshold():
    text = "कैफीन बच्चों के लिए सुरक्षित है।"
    source = _sources(1)
    source[0]["excerpt"] = text
    reply, cited = finalize_resource_reply(text, source)
    assert reply == "कैफीन बच्चों के लिए सुरक्षित है [R1]।"
    assert [item["page"] for item in cited] == [1]


def test_supported_terminal_bare_reference_is_canonical_but_resistor_ids_are_not():
    source = _sources(1)
    source[0]["excerpt"] = "Applicants should demonstrate leadership experience."
    reply, cited = finalize_resource_reply(
        "Applicants should demonstrate leadership experience R1.", source
    )
    assert reply == "Applicants should demonstrate leadership experience [R1]."
    assert [item["page"] for item in cited] == [1]

    reply, cited = finalize_resource_reply(
        "Applicants should demonstrate leadership experience R1", source
    )
    assert reply == "Applicants should demonstrate leadership experience [R1]"
    assert [item["page"] for item in cited] == [1]


def test_supported_based_on_phrases_become_inline_markers_and_unknown_phrases_are_removed():
    source = _sources(1)
    source[0]["excerpt"] = "Applicants should demonstrate leadership experience."
    variants = [
        "Applicants should demonstrate leadership experience, based on R1.",
        "Based on R1, Applicants should demonstrate leadership experience.",
    ]
    for variant in variants:
        reply, cited = finalize_resource_reply(variant, source)
        assert reply == "Applicants should demonstrate leadership experience [R1]."
        assert [item["page"] for item in cited] == [1]

    reply, cited = finalize_resource_reply(
        "Applicants should demonstrate leadership experience, based on R9.", source
    )
    assert reply == "Applicants should demonstrate leadership experience [R1]."
    assert [item["page"] for item in cited] == [1]


def test_later_markdown_link_does_not_protect_an_earlier_citation():
    reply, cited = finalize_resource_reply(
        "Supported claim [R1]. Read [more](https://example.test).", _sources(1)
    )
    assert reply == "Supported claim [R1]. Read [more](https://example.test)."
    assert [item["page"] for item in cited] == [1]


def test_self_check_variants_are_removed_without_authorizing_their_labels():
    variants = [
        "Answer. Self-check: [R1] is present and supported.",
        "Answer. **Self-check:** [R1] is present.",
        "Answer. (Self-check: claim 1 (R1) is covered.)",
        "Answer.\nCitation check:\n- R1 is present.",
        "Answer. [Self-check: [R1] is present.]",
    ]
    for variant in variants:
        reply, cited = finalize_resource_reply(variant, _sources(1))
        assert reply == "Answer."
        assert cited == []


def test_terminal_citation_audit_conclusions_are_removed_without_reference_labels():
    variants = [
        "Answer. Citation check: all sources are cited.",
        "Answer. Self-check: all citations are present.",
        "Answer. Citation check: complete.",
    ]
    for variant in variants:
        reply, cited = finalize_resource_reply(variant, [])
        assert reply == "Answer."
        assert cited == []


def test_references_in_literal_markdown_never_authorize_a_source():
    variants = [
        "Use `[R1]` as a literal.",
        "```text\n[R1]\n```",
        "Read [[R1]](https://example.test).",
        "The expression is $[R1]$.",
        "<code>[R1]</code>",
        "See [document][R1].\n\n[R1]: https://example.test",
        '<span title="[R1]">Claim</span>',
        "    [R1]\n",
        r"\begin{equation}[R1]\end{equation}",
        r"\begin{align*}x &= [R1]\end{align*}",
        "```text\n[R1]",
        "<code>[R1]",
        "<a href='https://evil.test'>[R1]",
        "$$\n[R1]",
        r"Write \[R1] to show the syntax.",
        r"Write \(R1) to show the syntax.",
        "[Use `[R1]`](https://example.test)",
        "<code>$[R1]$</code>",
        '<a href="https://example.test">`[R1]`</a>',
        "`example\n[R1]\ncontinued`",
        "``x[R1]`y``",
        "`x```[R1]y`",
        "[[R1] label][id]\n\n[id]: https://evil.test",
        "[label [R1]][id]\n\n[id]: https://evil.test",
        "Claim [R1].\n\n[R1]: https://evil.test",
        "Claim [R1][].\n\n[R1]: https://evil.test",
        "Claim [R1].\n\n> [R1]: https://evil.test",
        "Claim [R1].\n\n>   [R1]: https://evil.test",
        "Claim [R1].\n\n> >   [R1]: https://evil.test",
        "Claim [R1].\n\n- [R1]: https://evil.test",
    ]
    for variant in variants:
        reply, cited = finalize_resource_reply(variant, _sources(1))
        assert reply == variant
        assert cited == []


def test_citation_before_a_later_nested_link_remains_authoritative():
    text = "Claim [R1]. Read [[R1]](https://example.test) literally."
    reply, cited = finalize_resource_reply(text, _sources(1))
    assert reply == text
    assert [item["page"] for item in cited] == [1]


def test_citation_audit_words_inside_literals_do_not_truncate_the_answer():
    variants = [
        "Use `Self-check: [R1]` as a literal.",
        "```text\nCitation check: [R1]\n```\nContinue.",
        "<code>Self-check: [R1]</code> then explain.",
    ]
    for variant in variants:
        reply, cited = finalize_resource_reply(variant, _sources(1))
        assert reply == variant
        assert cited == []


def test_all_renderer_excluded_subtrees_keep_reference_examples_literal():
    variants = [
        "<kbd>[R1]</kbd>",
        "<samp>[R1]</samp>",
        "<button>[R1]</button>",
        '<span class="katex">[R1]</span>',
        '<span class="math-source">[R1]</span>',
    ]
    for variant in variants:
        reply, cited = finalize_resource_reply(variant, _sources(1))
        assert reply == variant
        assert cited == []


def test_legitimate_pedagogical_self_check_is_not_truncated():
    text = "A useful self-check: compute the dimensions. Then compare the units."
    reply, cited = finalize_resource_reply(text, _sources(1))
    assert reply == text
    assert cited == []


def test_legitimate_self_check_before_a_cited_claim_is_not_mistaken_for_an_audit():
    source = _sources(1)
    source[0]["excerpt"] = "The document recommends leadership."
    text = "A useful self-check: compute the dimensions. The document recommends leadership [R1]."
    reply, cited = finalize_resource_reply(text, source)
    assert reply == text
    assert [item["page"] for item in cited] == [1]


def test_legitimate_citation_check_instructions_are_not_model_audits():
    variants = [
        "In academic writing, perform a citation check: verify author and year. Then submit.",
        "A useful self-check: verify each citation against the bibliography. Then submit.",
    ]
    for text in variants:
        reply, cited = finalize_resource_reply(text, _sources(1))
        assert reply == text
        assert cited == []


def test_zero_hit_rag_cleanup_removes_unknown_markers_and_printed_audits():
    reply, cited = finalize_resource_reply(
        "Unsupported (R1). **Self-check:** citation check complete.", []
    )
    assert reply == "Unsupported."
    assert cited == []


def test_deleted_persisted_source_removes_and_renumbers_its_markers():
    sources = _sources(3)
    reply, retained = retain_persisted_resource_sources(
        "First [R1]. Second [R2]. Third [R3].",
        sources,
        [sources[1], sources[2]],
    )
    assert reply == "First. Second [R1]. Third [R2]."
    assert [item["page"] for item in retained] == [2, 3]


def test_persistence_remap_never_changes_literal_reference_examples():
    sources = _sources(5)
    finalized, candidates = finalize_resource_reply(
        "Supported [R5]. Use `[R2]` literally and $[R3]$ in math.", sources
    )
    reply, retained = retain_persisted_resource_sources(finalized, candidates, candidates)
    assert reply == "Supported [R1]. Use `[R2]` literally and $[R3]$ in math."
    assert [item["page"] for item in retained] == [5]

    deleted_reply, deleted_sources = retain_persisted_resource_sources(
        finalized, candidates, []
    )
    assert deleted_reply == "Supported. Use `[R2]` literally and $[R3]$ in math."
    assert deleted_sources == []
