"""The eval harness itself: it must pass on the shipped cases and be able to fail."""
import logging

from evals.run import DEFAULT_CASES, load_cases, main


def test_shipped_cases_meet_the_threshold(capsys):
    code = main([])
    out = capsys.readouterr().out
    assert code == 0, out
    assert "FAIL" not in out
    assert "Pass rate: 10/10" in out


def test_cases_file_is_well_formed():
    cases = load_cases(DEFAULT_CASES)
    assert 8 <= len(cases) <= 12
    assert len({c.id for c in cases}) == len(cases)


def test_impossible_threshold_exits_non_zero(capsys):
    assert main(["--threshold", "1.1"]) == 1
    assert "FAILED" in capsys.readouterr().out


BROKEN = """
- id: good_case
  conversation_id: conv_priya
  checks:
    - {type: contains, values: ["2026-11-12"]}
- id: deliberately_wrong_case
  conversation_id: conv_priya
  checks:
    - {type: contains, values: ["2030-01-01"]}
"""


def test_a_failing_case_is_reported_and_lowers_the_pass_rate(tmp_path, capsys):
    cases = tmp_path / "broken.yaml"
    cases.write_text(BROKEN)
    assert main(["--cases", str(cases)]) == 1  # 50% < default 100%
    out = capsys.readouterr().out
    assert "PASS  good_case" in out
    assert "FAIL  deliberately_wrong_case" in out
    assert "missing ['2030-01-01']" in out
    assert "Pass rate: 1/2 = 50%" in out


def test_threshold_decides_the_exit_code(tmp_path):
    cases = tmp_path / "broken.yaml"
    cases.write_text(BROKEN)
    assert main(["--cases", str(cases), "--threshold", "0.5"]) == 0
    assert main(["--cases", str(cases), "--threshold", "0.51"]) == 1


def test_a_crashing_case_is_a_failed_case_not_a_crashed_harness(tmp_path, capsys):
    cases = tmp_path / "crash.yaml"
    cases.write_text("- {id: no_such_conversation, conversation_id: conv_nope, "
                     "checks: [{type: status, equals: awaiting_approval}]}")
    assert main(["--cases", str(cases)]) == 1
    assert "raised RecordNotFoundError" in capsys.readouterr().out


def test_checks_are_not_vacuous_breaking_the_guardrail_fails_the_eval(monkeypatch, capsys):
    monkeypatch.setattr("app.agent.loop.validate_draft", lambda draft, instructions: [])
    assert main(["--threshold", "1.0"]) == 1
    out = capsys.readouterr().out
    assert "FAIL  model_inventing_a_salary_is_stopped_by_guardrail" in out


def test_breaking_the_failure_injection_fails_the_eval(monkeypatch, capsys):
    monkeypatch.setattr("app.services.drafting.FailingTools", lambda inner: inner)
    assert main(["--threshold", "1.0"]) == 1
    assert "FAIL  interview_tool_outage_degrades_gracefully" in capsys.readouterr().out


def test_harness_restores_logging_state():
    main([])
    assert not logging.root.manager.disable


def test_eval_is_hermetic_against_the_environment(monkeypatch, capsys):
    """A developer's env var (the demo flag) must not change eval results."""
    monkeypatch.setenv("INJECT_INTERVIEW_FAILURE_FOR", "cand_priya")
    assert main([]) == 0, capsys.readouterr().out


def test_eval_is_hermetic_against_a_dotenv_file(monkeypatch, tmp_path, capsys):
    """Same for a copied .env.example with the flag turned on (Settings reads ./.env)."""
    (tmp_path / ".env").write_text("INJECT_INTERVIEW_FAILURE_FOR=cand_priya\n")
    monkeypatch.chdir(tmp_path)
    assert main([]) == 0, capsys.readouterr().out


def test_default_threshold_is_all_cases():
    from evals.run import DEFAULT_THRESHOLD
    assert DEFAULT_THRESHOLD == 1.0
