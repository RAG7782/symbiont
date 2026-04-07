"""Tests for @Sentinel audit (R8 — compact summary validation)."""

import pytest

from symbiont.sentinel import (
    audit_summary,
    AuditLevel,
    AuditResult,
    _heuristic_audit,
    _parse_audit_response,
)


class TestHeuristicAudit:
    def test_ok_for_good_summary(self):
        original = "The worker implemented auth module and ran tests successfully."
        summary = "Worker implemented auth module and tests passed successfully."
        result = _heuristic_audit(original, summary)
        assert result.level == AuditLevel.OK
        assert result.recommendation == "accept"

    def test_alucinacao_for_empty_summary(self):
        original = "A long description of work done with errors and decisions."
        summary = "ok"
        result = _heuristic_audit(original, summary)
        assert result.level == AuditLevel.ALUCINACAO
        assert result.recommendation == "re_compact"

    def test_detects_missing_error_signals(self):
        original = "Step 1 worked. Step 2 had a critical error. Step 3 failed. Decision: rollback."
        summary = "Steps were completed and work progressed."
        result = _heuristic_audit(original, summary)
        assert len(result.issues) > 0
        assert any("missing" in i.lower() for i in result.issues)

    def test_norma_ok_for_mild_issues(self):
        original = "x" * 200
        summary = "x"  # Extreme compression but passes length check
        # This will detect extreme compression ratio
        result = _heuristic_audit(original, summary)
        assert result.level in (AuditLevel.NORMA_OK, AuditLevel.ALUCINACAO)

    def test_ok_when_no_signal_words(self):
        original = "Simple routine work was completed."
        summary = "Routine work completed."
        result = _heuristic_audit(original, summary)
        assert result.level == AuditLevel.OK


class TestParseAuditResponse:
    def test_parses_ok(self):
        response = (
            "LEVEL: OK\n"
            "ISSUES: none\n"
            "RECOMMENDATION: accept\n"
            "REASONING: Summary is accurate\n"
        )
        result = _parse_audit_response(response)
        assert result.level == AuditLevel.OK
        assert result.recommendation == "accept"

    def test_parses_alucinacao(self):
        response = (
            "LEVEL: ALUCINACAO\n"
            "ISSUES: Fabricated a database migration that never happened\n"
            "- Missing error from step 3\n"
            "RECOMMENDATION: re_compact\n"
            "REASONING: Summary contains information not in original\n"
        )
        result = _parse_audit_response(response)
        assert result.level == AuditLevel.ALUCINACAO
        assert len(result.issues) == 2
        assert result.recommendation == "re_compact"

    def test_parses_norma_ok(self):
        response = (
            "LEVEL: NORMA_OK\n"
            "ISSUES: Missing timing details\n"
            "RECOMMENDATION: accept_with_caveats\n"
            "REASONING: Directionally correct\n"
        )
        result = _parse_audit_response(response)
        assert result.level == AuditLevel.NORMA_OK


class _MockLLM:
    def __init__(self, response):
        self.response = response

    async def complete(self, prompt, context, model_tier, images=None):
        return self.response


@pytest.mark.asyncio
class TestAuditSummary:
    async def test_with_llm(self):
        llm = _MockLLM(
            "LEVEL: OK\n"
            "ISSUES: none\n"
            "RECOMMENDATION: accept\n"
            "REASONING: Good summary\n"
        )
        result = await audit_summary("original content", "summary", llm_backend=llm)
        assert result.level == AuditLevel.OK

    async def test_without_llm_uses_heuristics(self):
        result = await audit_summary(
            "original with decision and error handling",
            "summary with decision and error handling",
        )
        assert isinstance(result, AuditResult)

    async def test_alucinacao_triggers_recompact(self):
        llm = _MockLLM(
            "LEVEL: ALUCINACAO\n"
            "ISSUES: Fabricated information\n"
            "RECOMMENDATION: re_compact\n"
            "REASONING: Bad summary\n"
        )
        result = await audit_summary("original", "bad summary", llm_backend=llm)
        assert result.level == AuditLevel.ALUCINACAO
        assert result.recommendation == "re_compact"
