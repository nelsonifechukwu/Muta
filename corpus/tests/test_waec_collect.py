from pathlib import Path

from corpus.waec_collect import (
    FetchResult,
    coverage,
    discover_waec_papers,
    discover_waec_questions,
    element_text,
    extract_cheetah_options,
    extract_options,
    parse_answer_block,
    parse_html,
    parse_waec_question,
    split_observation_and_answer,
    split_pdf_question_entries,
    split_pdf_questions,
    validate_record,
)

SUBJECT_HTML = """
<div class="panel panel-default">
  <div class="panel-heading"><h4><a href="#">WASSCE FOR SCHOOL CANDIDATES 2023</a></h4></div>
  <div class="panel-body">
    <div class="list-group"><a href="Bio240mc.html" class="list-group-item">Paper 2</a></div>
    <div class="list-group"><a href="Bio340mc.html" class="list-group-item">Paper 3</a></div>
  </div>
</div>
"""

PAPER_HTML = """
<ul class="pagenum">
  <li><a href="Biomain.html">Subject Home</a></li>
  <li><a href="Bio240mq1.html">1</a></li>
  <li><a href="Bio240mq2.html">2</a></li>
</ul>
"""

LEGACY_PAPER_HTML = """
<table><tr>
  <td>Questions:</td>
  <td><a href="maths217mq1.html">1</a></td>
  <td><a href="maths217mq2.html">2</a></td>
  <td><a href="mathsmain.html">Main</a></td>
</tr></table>
"""

QUESTION_HTML = """
<div class="TopMenu"><h3>Biology Paper 2, WASSCE (SC), 2023</h3></div>
<div class="topcontent">
  <p><strong>QUESTION 1</strong></p>
  <ol><li>Define osmosis. [2 marks]</li><li>Use the diagram. [3 marks]</li></ol>
  <img src="images/osmosis.png" alt="osmosis diagram">
</div>
<div class="bottomcontent">
  <p>Many candidates omitted the membrane.</p>
  <p><strong>The expected answers are as follows:</strong></p>
  <p>Osmosis is movement of water through a selectively permeable membrane.</p>
</div>
"""

LEGACY_QUESTION_HTML = """
<html><head><title>General Mathematics Paper 2, May/June 2008</title></head><body>
<table><tr><td>Questions:</td><td><a href="maths217mq2.html">2</a></td></tr></table>
<div>Question 1</div>
<p>(a) If x:y = 2:3, evaluate x/y.</p>
<div>Observation</div>
<p>Some candidates substituted directly. They were expected to recognise that x = 2k.</p>
<footer>Copyright © 2012 The West African Examinations Council.</footer>
</body></html>
"""


class FakeFetcher:
    def __init__(self, root: Path):
        self.root = root

    def get(self, url: str) -> FetchResult:
        data = b"\x89PNG\r\nfixture"
        cache = self._cache_path(url)
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(data)
        return FetchResult(data=data, content_type="image/png", cache_path=cache)

    def _cache_path(self, url: str) -> Path:
        return self.root / "raw" / "http" / "fixture.html"


def test_discovers_papers_with_session_and_year():
    papers = discover_waec_papers(SUBJECT_HTML, "https://example.test/Biology/Biomain.html")
    assert [(paper["paper"], paper["year"]) for paper in papers] == [
        ("Paper 2", 2023),
        ("Paper 3", 2023),
    ]
    assert papers[0]["url"] == "https://example.test/Biology/Bio240mc.html"


def test_discovers_only_numbered_question_links():
    assert discover_waec_questions(
        PAPER_HTML, "https://example.test/Biology/Bio240mc.html"
    ) == [
        "https://example.test/Biology/Bio240mq1.html",
        "https://example.test/Biology/Bio240mq2.html",
    ]


def test_discovers_questions_in_legacy_table_menu():
    assert discover_waec_questions(
        LEGACY_PAPER_HTML, "https://example.test/Mathematics/maths217mc.html"
    ) == [
        "https://example.test/Mathematics/maths217mq1.html",
        "https://example.test/Mathematics/maths217mq2.html",
    ]


def test_parses_question_answer_observation_and_asset(tmp_path: Path):
    output = tmp_path / "waec"
    failures = []
    record = parse_waec_question(
        QUESTION_HTML,
        page_url="https://example.test/Biology/Bio240mq1.html",
        paper_url="https://example.test/Biology/Bio240mc.html",
        subject="biology",
        paper="Paper 2",
        session="WASSCE FOR SCHOOL CANDIDATES 2023",
        year=2023,
        fetcher=FakeFetcher(output),
        output_dir=output,
        metadata_only=False,
        failures=failures,
    )
    assert failures == []
    assert record["question_number"] == "1"
    assert "Define osmosis" in record["question_text"]
    assert record["marks"] == 5
    assert "Many candidates" in record["examiner_observation"]
    assert "selectively permeable membrane" in record["worked_solution"]
    assert record["answer_status"] == "published"
    assert record["content_status"] == "needs_visual_review"
    assert record["assets"][0]["local_path"].startswith("assets/biology/")
    assert (output / record["assets"][0]["local_path"]).is_file()
    validate_record(record)


def test_visual_answer_asset_counts_as_published_answer(tmp_path: Path):
    output = tmp_path / "waec"
    document = """
    <div class="topcontent"><p>Question 1</p><p>Calculate x.</p></div>
    <div class="bottomcontent"><p>See the worked response.</p>
      <img src="images/solution.png" alt="worked solution">
    </div>
    """
    record = parse_waec_question(
        document,
        page_url="https://example.test/Mathematics/q1.html",
        paper_url="https://example.test/Mathematics/paper.html",
        subject="mathematics",
        paper="Paper 2",
        session="WASSCE 2023",
        year=2023,
        fetcher=FakeFetcher(output),
        output_dir=output,
        metadata_only=False,
        failures=[],
    )
    assert record["answer_status"] == "published"
    assert record["worked_solution"].startswith("Publisher-provided visual answer:")
    assert "published_answer_is_visual_asset" in record["extraction_warnings"]


def test_parses_legacy_question_layout(tmp_path: Path):
    output = tmp_path / "waec"
    record = parse_waec_question(
        LEGACY_QUESTION_HTML,
        page_url="https://example.test/Mathematics/maths217mq1.html",
        paper_url="https://example.test/Mathematics/maths217mc.html",
        subject="mathematics",
        paper="Paper 2",
        session="MAY/JUN. WASSCE 2008",
        year=2008,
        fetcher=FakeFetcher(output),
        output_dir=output,
        metadata_only=False,
        failures=[],
    )
    assert record["question_number"] == "1"
    assert record["question_text"] == "(a) If x:y = 2:3, evaluate x/y."
    assert record["examiner_observation"] == "Some candidates substituted directly."
    assert record["worked_solution"] == "recognise that x = 2k."
    assert record["answer_status"] == "published"


def test_parses_nested_legacy_table_without_duplicate_content(tmp_path: Path):
    output = tmp_path / "waec"
    document = """
    <table><tr><td>Navigation<table><tr><td>Weakness | Question 1</td></tr>
    <tr><td>Find x when x + 2 = 5.</td></tr>
    <tr><td>OBSERVATION</td></tr>
    <tr><td>Candidates guessed. Expected answer: x = 3.</td></tr>
    </table></td></tr></table>
    """
    rendered = element_text(parse_html(document))
    assert rendered.count("Find x when x + 2 = 5.") == 1
    record = parse_waec_question(
        document,
        page_url="https://example.test/Mathematics/maths217mq1.html",
        paper_url="https://example.test/Mathematics/maths217mc.html",
        subject="mathematics",
        paper="Paper 2",
        session="MAY/JUN. WASSCE 2008",
        year=2008,
        fetcher=FakeFetcher(output),
        output_dir=output,
        metadata_only=False,
        failures=[],
    )
    assert record["question_text"] == "Find x when x + 2 = 5."
    assert record["worked_solution"] == "x = 3."


def test_legacy_assets_are_classified_around_observation(tmp_path: Path):
    output = tmp_path / "waec"
    document = """
    <div>Question 1</div><p>Use this diagram.</p><img src="question.png">
    <div>OBSERVATION</div><p>The result is shown.</p><img src="answer.png">
    """
    record = parse_waec_question(
        document,
        page_url="https://example.test/Mathematics/maths217mq1.html",
        paper_url="https://example.test/Mathematics/maths217mc.html",
        subject="mathematics",
        paper="Paper 2",
        session="MAY/JUN. WASSCE 2008",
        year=2008,
        fetcher=FakeFetcher(output),
        output_dir=output,
        metadata_only=False,
        failures=[],
    )
    assert [asset["role"] for asset in record["assets"]] == ["question", "answer"]
    assert record["answer_status"] == "published"


def test_observation_without_published_answer_stays_missing():
    observation, answer = split_observation_and_answer("Candidates found the item difficult.")
    assert observation == "Candidates found the item difficult."
    assert answer is None


def test_splits_expected_to_solve_wording():
    observation, answer = split_observation_and_answer(
        "Most candidates interpreted the item. They were expected to solve as shown:\n"
        "x = 4. Therefore the answer is 4."
    )
    assert observation == "Most candidates interpreted the item."
    assert answer == "x = 4. Therefore the answer is 4."


def test_splits_generic_expected_guidance():
    observation, answer = split_observation_and_answer(
        "Some candidates substituted directly. They were expected to recognise that x = 2k."
    )
    assert observation == "Some candidates substituted directly."
    assert answer == "recognise that x = 2k."


def test_splits_multiline_expected_response_heading():
    observation, answer = split_observation_and_answer(
        "Most candidates did well. The expected\nresponses were as follows:\n"
        "x = 4."
    )
    assert observation == "Most candidates did well."
    assert answer == "x = 4."


def test_splits_examiner_description_of_correct_response():
    observation, answer = split_observation_and_answer(
        "Performance was good. Candidates correctly defined osmosis as movement of water."
    )
    assert observation == "Performance was good."
    assert answer == "defined osmosis as movement of water."


def test_extracts_multiple_choice_options():
    question, options = extract_options("Find x.\nA. 1\nB. 2\nC. 3\nD. 4")
    assert question == "Find x."
    assert options == [
        {"label": "A", "text": "1"},
        {"label": "B", "text": "2"},
        {"label": "C", "text": "3"},
        {"label": "D", "text": "4"},
    ]


def test_extracts_options_without_space_after_period():
    question, options = extract_options(
        "Find the intersection.\nPossible Answers:\nA.{1, 2}\nB.{2, 3}\nC.{3}\nD.{}"
    )
    assert question == "Find the intersection."
    assert options[1] == {"label": "B", "text": "{2, 3}"}


def test_extracts_inline_pdf_options_after_possible_answers_heading():
    question, options = extract_options("Evaluate 2 + 2. Possible answers: A. 2;B. 3;C. 4;D. 5")
    assert question == "Evaluate 2 + 2."
    assert options == [
        {"label": "A", "text": "2"},
        {"label": "B", "text": "3"},
        {"label": "C", "text": "4"},
        {"label": "D", "text": "5"},
    ]


def test_cheetah_unheaded_multipart_question_is_not_treated_as_mcq():
    text = (
        "Use the data below.\n"
        "A. Find the range.\n"
        "B. Draw a frequency table.\n"
        "C. Find the median.\n"
        "D. Calculate the mean."
    )
    question, options = extract_cheetah_options(text, question_kind=None)
    assert question == text
    assert options == []


def test_cheetah_explicit_frq_marker_overrides_option_like_subparts():
    text = "Calculate each value.\nA. 2 + 2\nB. 3 + 3\nC. 4 + 4\nD. 5 + 5"
    question, options = extract_cheetah_options(text, question_kind="frq")
    assert question == text
    assert options == []


def test_answer_block_uses_unlabelled_trailing_explanation_as_solution():
    answer, solution, question = parse_answer_block(
        "Find the value of x.\nAnswer: D\n"
        "Substitute the known values, then simplify to obtain x = 4."
    )
    assert answer == "D"
    assert solution == "Substitute the known values, then simplify to obtain x = 4."
    assert question == "Find the value of x."


def test_answer_block_does_not_truncate_textual_answer_starting_with_choice_letter():
    answer, solution, _question = parse_answer_block(
        "Prepare the cumulative frequency table.\n"
        "Answer: Cumulative frequencies: 2, 5, 9.\n"
        "Add each frequency to the running total."
    )
    assert answer == "Cumulative frequencies: 2, 5, 9."
    assert solution == "Add each frequency to the running total."


def test_pdf_question_split_accepts_question_and_problem_labels():
    blocks = split_pdf_questions(
        "Header\nProblem 1\nFind x.\nA. 1\nB. 2\nQuestion 2 (FRQ)\nExplain why.\n"
    )
    assert blocks == {
        "1": "Find x.\nA. 1\nB. 2",
        "2": "Explain why.",
    }


def test_pdf_question_split_preserves_explicit_mcq_and_frq_markers():
    entries = split_pdf_question_entries(
        "Problem 1 (MCQ)\nChoose one.\nQuestion 2 (FRQ)\nShow your work."
    )
    assert entries == {
        "1": ("Choose one.", "mcq"),
        "2": ("Show your work.", "frq"),
    }


def test_tree_parser_recovers_from_malformed_html():
    root = parse_html("<div class='topcontent'><p>Question 1<br>Text</div>")
    assert root.find_first("div", class_name="topcontent") is not None


def test_coverage_tracks_status_and_answer_counts():
    records = [
        {
            "subject": "biology",
            "year": 2023,
            "content_status": "complete",
            "answer_status": "published",
            "assets": [],
            "source": {"source_type": "waec_html"},
        },
        {
            "subject": "mathematics",
            "year": 2024,
            "content_status": "needs_visual_review",
            "answer_status": "published",
            "assets": [{}],
            "source": {"source_type": "cheetah_pdf"},
        },
    ]
    summary = coverage(records)
    assert summary["total_records"] == 2
    assert summary["with_published_answer"] == 2
    assert summary["with_assets"] == 1
