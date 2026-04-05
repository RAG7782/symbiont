"""
Tests for the DensityTranslator — System 9 (Semiotic Density Bridge).

Tests verify:
1. Term classification (zero, low, high, bridge)
2. Term-level translation between domain pairs
3. Text-level translation (multi-word, longest-match)
4. Payload translation (str, dict, list, pass-through)
5. Middleware integration with Mycelium messages
6. Domain and mapping registration
7. Reverse mapping auto-generation
8. Disabled state (pass-through behavior)
"""

import asyncio
import pytest

from symbiont.core.density_translator import (
    DensityTranslator,
    DomainDictionary,
    DomainMapping,
    TermDensity,
)
from symbiont.core.mycelium import Mycelium
from symbiont.types import Message


# ======================================================================
# Term Classification
# ======================================================================

class TestTermClassification:

    def test_high_density_term(self):
        t = DensityTranslator()
        assert t.classify_term("fato gerador", "tributario") == TermDensity.HIGH

    def test_high_density_case_insensitive(self):
        t = DensityTranslator()
        assert t.classify_term("Fato Gerador", "tributario") == TermDensity.HIGH

    def test_zero_term_numeric(self):
        t = DensityTranslator()
        assert t.classify_term("1.234,56", "tributario") == TermDensity.ZERO

    def test_zero_term_currency(self):
        t = DensityTranslator()
        assert t.classify_term("R$ 1.000,00", "tributario") == TermDensity.ZERO

    def test_zero_term_article_ref(self):
        t = DensityTranslator()
        assert t.classify_term("art. 150", "tributario") == TermDensity.ZERO

    def test_low_density_generic_term(self):
        t = DensityTranslator()
        assert t.classify_term("empresa", "tributario") == TermDensity.LOW

    def test_unknown_domain_returns_low(self):
        t = DensityTranslator()
        assert t.classify_term("anything", "unknown_domain") == TermDensity.LOW

    def test_bridge_term_classification(self):
        t = DensityTranslator()
        assert t.classify_term_pair(
            "compliance", "tributario", "compliance"
        ) == TermDensity.BRIDGE

    def test_bridge_term_case_insensitive(self):
        t = DensityTranslator()
        assert t.classify_term_pair(
            "SPED", "tributario", "compliance"
        ) == TermDensity.BRIDGE


# ======================================================================
# Term Translation
# ======================================================================

class TestTermTranslation:

    def test_translate_high_density_term(self):
        t = DensityTranslator(use_density_translation=True)
        result = t.translate_term("fato gerador", "tributario", "compliance")
        assert result == "triggering event"

    def test_translate_reverse_direction(self):
        t = DensityTranslator(use_density_translation=True)
        result = t.translate_term("triggering event", "compliance", "tributario")
        assert result == "fato gerador"

    def test_bridge_term_preserved(self):
        t = DensityTranslator(use_density_translation=True)
        result = t.translate_term("SPED", "tributario", "compliance")
        assert result == "SPED"

    def test_zero_term_passes_through(self):
        t = DensityTranslator(use_density_translation=True)
        result = t.translate_term("R$ 1.000,00", "tributario", "compliance")
        assert result == "R$ 1.000,00"

    def test_low_density_passes_through(self):
        t = DensityTranslator(use_density_translation=True)
        result = t.translate_term("empresa", "tributario", "compliance")
        assert result == "empresa"

    def test_same_domain_no_translation(self):
        t = DensityTranslator(use_density_translation=True)
        result = t.translate_term("fato gerador", "tributario", "tributario")
        assert result == "fato gerador"

    def test_no_mapping_passes_through(self):
        t = DensityTranslator(use_density_translation=True)
        result = t.translate_term("fato gerador", "tributario", "unknown")
        assert result == "fato gerador"

    def test_legal_to_tecnico_translation(self):
        t = DensityTranslator(use_density_translation=True)
        result = t.translate_term("petição inicial", "legal", "tecnico")
        assert result == "documento inaugural"

    def test_tecnico_to_legal_reverse(self):
        t = DensityTranslator(use_density_translation=True)
        result = t.translate_term("documento inaugural", "tecnico", "legal")
        assert result == "petição inicial"


# ======================================================================
# Text Translation
# ======================================================================

class TestTextTranslation:

    def test_translate_text_basic(self):
        t = DensityTranslator(use_density_translation=True)
        text = "O fato gerador ocorreu quando a alíquota foi aplicada."
        result = t.translate_text(text, "tributario", "compliance")
        assert "triggering event" in result
        assert "rate" in result

    def test_translate_text_preserves_structure(self):
        t = DensityTranslator(use_density_translation=True)
        text = "A base de cálculo do crédito tributário."
        result = t.translate_text(text, "tributario", "compliance")
        assert "assessment base" in result
        assert "regulatory credit" in result
        # Structure words preserved
        assert "A " in result or "a " in result
        assert "do" in result

    def test_translate_text_disabled(self):
        t = DensityTranslator(use_density_translation=False)
        text = "O fato gerador ocorreu."
        result = t.translate_text(text, "tributario", "compliance")
        assert result == text  # Unchanged

    def test_translate_text_same_domain(self):
        t = DensityTranslator(use_density_translation=True)
        text = "O fato gerador ocorreu."
        result = t.translate_text(text, "tributario", "tributario")
        assert result == text

    def test_translate_text_multiword_longest_match(self):
        t = DensityTranslator(use_density_translation=True)
        # "base de cálculo" should match as a unit, not "base" alone
        text = "Sobre a base de cálculo incide a alíquota."
        result = t.translate_text(text, "tributario", "compliance")
        assert "assessment base" in result

    def test_translate_legal_text(self):
        t = DensityTranslator(use_density_translation=True)
        text = "A tutela de urgência foi concedida com base na jurisprudência."
        result = t.translate_text(text, "legal", "tecnico")
        assert "medida emergencial" in result
        assert "precedentes" in result


# ======================================================================
# Payload Translation
# ======================================================================

class TestPayloadTranslation:

    def test_translate_string_payload(self):
        t = DensityTranslator(use_density_translation=True)
        result = t.translate_payload(
            "O fato gerador", "tributario", "compliance"
        )
        assert "triggering event" in result

    def test_translate_dict_payload(self):
        t = DensityTranslator(use_density_translation=True)
        payload = {
            "analysis": "O fato gerador é relevante.",
            "score": 0.95,
            "tags": ["urgente"],
        }
        result = t.translate_payload(payload, "tributario", "compliance")
        assert "triggering event" in result["analysis"]
        assert result["score"] == 0.95  # Numeric zero-term
        assert result["tags"] == ["urgente"]  # Low-density pass-through

    def test_translate_list_payload(self):
        t = DensityTranslator(use_density_translation=True)
        payload = ["fato gerador", "alíquota"]
        result = t.translate_payload(payload, "tributario", "compliance")
        assert "triggering event" in result
        assert "rate" in result

    def test_translate_nested_payload(self):
        t = DensityTranslator(use_density_translation=True)
        payload = {
            "level1": {
                "text": "O sujeito passivo deve comprovar.",
            }
        }
        result = t.translate_payload(payload, "tributario", "compliance")
        assert "obligated party" in result["level1"]["text"]

    def test_none_payload_passes_through(self):
        t = DensityTranslator(use_density_translation=True)
        assert t.translate_payload(None, "tributario", "compliance") is None

    def test_numeric_payload_passes_through(self):
        t = DensityTranslator(use_density_translation=True)
        assert t.translate_payload(42, "tributario", "compliance") == 42

    def test_disabled_payload_unchanged(self):
        t = DensityTranslator(use_density_translation=False)
        payload = {"text": "fato gerador"}
        result = t.translate_payload(payload, "tributario", "compliance")
        assert result["text"] == "fato gerador"


# ======================================================================
# Middleware Integration
# ======================================================================

class TestMiddleware:

    @pytest.mark.asyncio
    async def test_middleware_translates_message(self):
        t = DensityTranslator(use_density_translation=True)
        middleware = t.create_middleware()

        received = []

        async def handler(msg: Message):
            received.append(msg)

        wrapped = middleware(handler, target_domain="compliance")

        msg = Message(
            channel="analysis",
            sender_id="agent-trib",
            payload="O fato gerador ocorreu.",
            metadata={"domain": "tributario"},
        )
        await wrapped(msg)

        assert len(received) == 1
        assert "triggering event" in received[0].payload
        assert received[0].metadata.get("_density_translated") is True
        assert received[0].metadata.get("_density_source_domain") == "tributario"

    @pytest.mark.asyncio
    async def test_middleware_no_source_domain(self):
        """When message has no domain metadata, it passes through unchanged."""
        t = DensityTranslator(use_density_translation=True)
        middleware = t.create_middleware()

        received = []

        async def handler(msg: Message):
            received.append(msg)

        wrapped = middleware(handler, target_domain="compliance")

        msg = Message(
            channel="general",
            sender_id="agent-x",
            payload="O fato gerador ocorreu.",
            metadata={},  # No domain
        )
        await wrapped(msg)

        assert len(received) == 1
        assert received[0].payload == "O fato gerador ocorreu."  # Unchanged

    @pytest.mark.asyncio
    async def test_middleware_same_domain(self):
        """Same source and target domain: no translation."""
        t = DensityTranslator(use_density_translation=True)
        middleware = t.create_middleware()

        received = []

        async def handler(msg: Message):
            received.append(msg)

        wrapped = middleware(handler, target_domain="tributario")

        msg = Message(
            channel="tax",
            sender_id="agent-trib",
            payload="O fato gerador ocorreu.",
            metadata={"domain": "tributario"},
        )
        await wrapped(msg)

        assert len(received) == 1
        assert received[0].payload == "O fato gerador ocorreu."  # Unchanged

    @pytest.mark.asyncio
    async def test_middleware_disabled(self):
        """When translator is disabled, messages pass through."""
        t = DensityTranslator(use_density_translation=False)
        middleware = t.create_middleware()

        received = []

        async def handler(msg: Message):
            received.append(msg)

        wrapped = middleware(handler, target_domain="compliance")

        msg = Message(
            channel="analysis",
            sender_id="agent-trib",
            payload="O fato gerador ocorreu.",
            metadata={"domain": "tributario"},
        )
        await wrapped(msg)

        assert len(received) == 1
        assert received[0].payload == "O fato gerador ocorreu."  # Unchanged

    @pytest.mark.asyncio
    async def test_middleware_with_mycelium(self):
        """Full integration: Mycelium publish → middleware → translated delivery."""
        mycelium = Mycelium()
        t = DensityTranslator(use_density_translation=True)
        middleware = t.create_middleware()

        received = []

        async def raw_handler(msg: Message):
            received.append(msg)

        wrapped = middleware(raw_handler, target_domain="compliance")

        mycelium.subscribe("tax-channel", "compliance-agent", wrapped)

        await mycelium.publish(
            channel="tax-channel",
            payload="O lançamento e a base de cálculo foram revisados.",
            sender_id="trib-agent",
            metadata={"domain": "tributario"},
        )

        assert len(received) == 1
        translated = received[0].payload
        assert "determination" in translated
        assert "assessment base" in translated


# ======================================================================
# Domain Registration
# ======================================================================

class TestDomainRegistration:

    def test_register_custom_domain(self):
        t = DensityTranslator()
        custom = DomainDictionary(
            domain="fintech",
            high_terms={
                "smart contract": "self-executing agreement on blockchain",
                "yield farming": "strategy to maximize DeFi returns",
            },
        )
        t.register_domain(custom)
        assert "fintech" in t.get_available_domains()
        assert t.classify_term("smart contract", "fintech") == TermDensity.HIGH

    def test_register_custom_mapping(self):
        t = DensityTranslator(use_density_translation=True)
        custom = DomainDictionary(
            domain="fintech",
            high_terms={"smart contract": "..."},
        )
        t.register_domain(custom)

        mapping = DomainMapping(
            source_domain="fintech",
            target_domain="legal",
            term_map={"smart contract": "contrato autoexecutável"},
            bridge_terms={"blockchain"},
        )
        t.register_mapping(mapping)

        result = t.translate_term("smart contract", "fintech", "legal")
        assert result == "contrato autoexecutável"

        # Reverse should also work
        result = t.translate_term("contrato autoexecutável", "legal", "fintech")
        assert result == "smart contract"

    def test_builtin_domains_present(self):
        t = DensityTranslator()
        domains = t.get_available_domains()
        assert "tributario" in domains
        assert "compliance" in domains
        assert "legal" in domains
        assert "tecnico" in domains

    def test_builtin_mappings_present(self):
        t = DensityTranslator()
        mappings = t.get_available_mappings()
        assert ("tributario", "compliance") in mappings
        assert ("compliance", "tributario") in mappings  # Auto-reverse
        assert ("legal", "tecnico") in mappings
        assert ("tecnico", "legal") in mappings  # Auto-reverse


# ======================================================================
# Introspection
# ======================================================================

class TestIntrospection:

    def test_mapping_coverage(self):
        t = DensityTranslator()
        coverage = t.get_mapping_coverage("tributario", "compliance")
        assert coverage["exists"] is True
        assert coverage["mapped_terms"] == 12
        assert coverage["coverage"] == 1.0  # All 12 terms mapped

    def test_mapping_coverage_nonexistent(self):
        t = DensityTranslator()
        coverage = t.get_mapping_coverage("tributario", "unknown")
        assert coverage["exists"] is False

    def test_summary(self):
        t = DensityTranslator(use_density_translation=True)
        s = t.summary()
        assert s["enabled"] is True
        assert s["domains"] == 4
        assert s["mappings"] > 0
