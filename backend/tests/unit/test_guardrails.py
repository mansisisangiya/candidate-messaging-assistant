import pytest

from app.agent.guardrails import MAX_DRAFT_CHARS, validate_draft


def test_good_draft_has_no_violations():
    assert validate_draft("Hi Priya, your interview is on 2026-11-12.", None) == []


@pytest.mark.parametrize("draft", ["", "   \n"])
def test_empty_draft_is_a_violation(draft):
    assert any("empty" in v for v in validate_draft(draft, None))


def test_length_limit_is_inclusive():
    assert validate_draft("x" * MAX_DRAFT_CHARS, None) == []
    assert any("maximum" in v for v in validate_draft("x" * (MAX_DRAFT_CHARS + 1), None))


@pytest.mark.parametrize("draft", ["Hi [Name], hello", "Hi {{first_name}}", "Hello [Candidate Name]!"])
def test_placeholders_are_violations(draft):
    assert any("placeholder" in v for v in validate_draft(draft, None))


@pytest.mark.parametrize("draft", [
    "The salary is fixed.", "Compensation is competitive.", "There is a Bonus.",
    "You get equity.", "We offer stock options.", "It pays £90,000.", "About $120k."])
def test_compensation_words_are_violations(draft):
    assert any("compensation" in v for v in validate_draft(draft, None))


def test_compensation_is_allowed_when_instructions_mention_it():
    draft = "Happy to discuss the salary range on a call."
    assert validate_draft(draft, "Tell her we can discuss salary") == []


def test_unrelated_instructions_do_not_unlock_compensation():
    assert validate_draft("The salary is 90k.", "Keep it short") != []


def test_all_violations_are_reported_together():
    assert len(validate_draft("[Name] salary " + "x" * MAX_DRAFT_CHARS, None)) == 3
