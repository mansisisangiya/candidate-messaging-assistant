"""Rule checks on a finished draft. Pure function: no I/O, easy to test."""
import re

MAX_DRAFT_CHARS = 1200

PLACEHOLDER_PATTERN = re.compile(r"\[[A-Za-z][^\]]*\]|\{\{|\}\}")
COMPENSATION_PATTERN = re.compile(
    r"\b(salary|salaries|compensation|bonus|bonuses|equity|stock options?)\b|[£$€]\s?\d",
    re.IGNORECASE)


def validate_draft(draft: str, instructions: str | None) -> list[str]:
    """Return a list of violations (empty = the draft is acceptable).

    Compensation talk is allowed only if the recruiter's own instructions mention it.
    """
    violations: list[str] = []
    if not draft.strip():
        violations.append("draft is empty")
    if len(draft) > MAX_DRAFT_CHARS:
        violations.append(f"draft is {len(draft)} characters (maximum {MAX_DRAFT_CHARS})")
    if PLACEHOLDER_PATTERN.search(draft):
        violations.append("draft contains a placeholder such as [Name] or {{...}}")
    if COMPENSATION_PATTERN.search(draft) and not COMPENSATION_PATTERN.search(instructions or ""):
        violations.append("draft discusses compensation, which the recruiter did not ask for")
    return violations
