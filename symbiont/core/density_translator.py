"""
System 9 — DENSITY TRANSLATOR (Semiotic Density Bridge)

Mediates communication between agents operating in different semantic domains.
Inspired by the Semiotic Density principle: terms carry implicit semantic fields,
and translation between domains requires mapping these density profiles.

Key properties:
- High-density terms in domain X are mapped to equivalent high-density terms in domain Y
- Bridge-terms (dense in BOTH domains) are preserved unchanged
- Zero-terms (structural delimiters, metadata, scores) pass through unchanged
- Translation is optional middleware — disabled by default to preserve original behavior

Biological analogy: chemical signal translation at species boundaries in
symbiotic relationships (e.g., mycorrhizal networks translating between
plant root signals and fungal chemical signals).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

logger = logging.getLogger(__name__)


class TermDensity(Enum):
    """Classification of a term's semiotic density."""
    ZERO = auto()      # Structural: delimiters, metadata keys, scores, punctuation
    LOW = auto()       # Generic terms with minimal domain-specific load
    HIGH = auto()      # Domain-specific terms carrying rich implicit meaning
    BRIDGE = auto()    # Dense in BOTH source and target domains — preserved as-is


@dataclass
class DomainDictionary:
    """
    A domain's term inventory with density classification.

    high_terms: terms that carry rich meaning specific to this domain.
    zero_patterns: regex patterns matching structural/zero-density elements.
    """
    domain: str
    high_terms: dict[str, str] = field(default_factory=dict)  # term → description
    zero_patterns: list[str] = field(default_factory=list)


@dataclass
class DomainMapping:
    """Bidirectional mapping between two domains."""
    source_domain: str
    target_domain: str
    term_map: dict[str, str] = field(default_factory=dict)       # source_term → target_term
    bridge_terms: set[str] = field(default_factory=set)          # terms dense in both


# ---------------------------------------------------------------------------
# Built-in domain dictionaries (proof-of-concept)
# ---------------------------------------------------------------------------

_TRIBUTARIO_DICT = DomainDictionary(
    domain="tributario",
    high_terms={
        "fato gerador": "evento que origina a obrigação tributária",
        "base de cálculo": "valor sobre o qual incide a alíquota",
        "alíquota": "percentual aplicado à base de cálculo",
        "sujeito passivo": "pessoa obrigada ao pagamento do tributo",
        "lançamento": "ato administrativo que constitui o crédito tributário",
        "crédito tributário": "direito do fisco de exigir o tributo",
        "imunidade": "limitação constitucional ao poder de tributar",
        "isenção": "exclusão legal do crédito tributário",
        "decadência": "perda do direito de lançar o tributo",
        "prescrição": "perda do direito de cobrar o crédito tributário",
        "compensação": "extinção de obrigações recíprocas entre fisco e contribuinte",
        "elisão fiscal": "planejamento tributário lícito para reduzir a carga tributária",
    },
    zero_patterns=[
        r"^\d+[\.,]\d+$",   # numeric values
        r"^R\$\s*[\d\.,]+$", # currency values
        r"^§\s*\d+",         # paragraph references
        r"^art\.\s*\d+",     # article references
    ],
)

_COMPLIANCE_DICT = DomainDictionary(
    domain="compliance",
    high_terms={
        "triggering event": "event that creates a regulatory obligation",
        "assessment base": "quantified value subject to regulatory calculation",
        "rate": "percentage applied to the assessment base",
        "obligated party": "entity required to fulfill compliance requirements",
        "determination": "formal act establishing the compliance obligation",
        "regulatory credit": "quantified obligation owed to the regulator",
        "constitutional exemption": "fundamental limitation on regulatory power",
        "statutory exemption": "legal exclusion from regulatory obligation",
        "statute of limitations (assessment)": "time limit for regulatory assessment",
        "statute of limitations (enforcement)": "time limit for enforcement action",
        "offset": "mutual extinction of obligations between regulator and entity",
        "tax planning": "lawful structuring to minimize regulatory burden",
    },
    zero_patterns=[
        r"^\d+[\.,]\d+$",
        r"^\$\s*[\d\.,]+$",
        r"^§\s*\d+",
        r"^sec\.\s*\d+",
    ],
)

_LEGAL_DICT = DomainDictionary(
    domain="legal",
    high_terms={
        "petição inicial": "peça inaugural do processo judicial",
        "tutela de urgência": "medida provisória para proteger direito em risco",
        "mérito": "questão central da lide",
        "jurisprudência": "conjunto de decisões reiteradas dos tribunais",
        "ônus da prova": "encargo de demonstrar a veracidade dos fatos alegados",
        "contraditório": "garantia de manifestação sobre os atos processuais",
        "ampla defesa": "garantia de utilizar todos os meios de prova admitidos",
        "sentença": "decisão que resolve o mérito da causa",
        "acórdão": "decisão proferida por órgão colegiado",
        "coisa julgada": "imutabilidade da decisão judicial definitiva",
        "litispendência": "existência de ação idêntica em curso",
        "prescrição": "perda da pretensão pelo decurso do tempo",
    },
    zero_patterns=[
        r"^\d+[\.,]\d+$",
        r"^fls?\.\s*\d+",
        r"^proc\.\s*[\d\.\-/]+",
    ],
)

_TECNICO_DICT = DomainDictionary(
    domain="tecnico",
    high_terms={
        "documento inaugural": "artefato que inicia o fluxo de trabalho",
        "medida emergencial": "intervenção provisória para mitigar risco imediato",
        "questão central": "ponto-chave que define o escopo da análise",
        "precedentes": "casos anteriores utilizados como referência técnica",
        "responsabilidade de evidência": "obrigação de fornecer dados comprobatórios",
        "revisão adversarial": "análise por parte contrária para validação",
        "defesa técnica completa": "apresentação exaustiva de argumentos e evidências",
        "decisão definitiva": "resolução final sem possibilidade de recurso no escopo",
        "decisão colegiada": "resolução tomada por múltiplos avaliadores",
        "resolução imutável": "decisão que não pode ser revertida no escopo",
        "conflito de escopo": "sobreposição entre análises em andamento",
        "prazo de validade": "limite temporal para ação ou recurso",
    },
    zero_patterns=[
        r"^\d+[\.,]\d+$",
        r"^v\d+\.\d+",
        r"^id:\s*\w+",
    ],
)


# ---------------------------------------------------------------------------
# Built-in mappings
# ---------------------------------------------------------------------------

_TRIBUTARIO_COMPLIANCE_MAPPING = DomainMapping(
    source_domain="tributario",
    target_domain="compliance",
    term_map={
        "fato gerador": "triggering event",
        "base de cálculo": "assessment base",
        "alíquota": "rate",
        "sujeito passivo": "obligated party",
        "lançamento": "determination",
        "crédito tributário": "regulatory credit",
        "imunidade": "constitutional exemption",
        "isenção": "statutory exemption",
        "decadência": "statute of limitations (assessment)",
        "prescrição": "statute of limitations (enforcement)",
        "compensação": "offset",
        "elisão fiscal": "tax planning",
    },
    bridge_terms={"compliance", "due diligence", "SPED", "DCTF", "EFD"},
)

_LEGAL_TECNICO_MAPPING = DomainMapping(
    source_domain="legal",
    target_domain="tecnico",
    term_map={
        "petição inicial": "documento inaugural",
        "tutela de urgência": "medida emergencial",
        "mérito": "questão central",
        "jurisprudência": "precedentes",
        "ônus da prova": "responsabilidade de evidência",
        "contraditório": "revisão adversarial",
        "ampla defesa": "defesa técnica completa",
        "sentença": "decisão definitiva",
        "acórdão": "decisão colegiada",
        "coisa julgada": "resolução imutável",
        "litispendência": "conflito de escopo",
        "prescrição": "prazo de validade",
    },
    bridge_terms={"prazo", "notificação", "protocolo", "parecer"},
)


# ---------------------------------------------------------------------------
# Built-in registries
# ---------------------------------------------------------------------------

_BUILTIN_DICTIONARIES: dict[str, DomainDictionary] = {
    "tributario": _TRIBUTARIO_DICT,
    "compliance": _COMPLIANCE_DICT,
    "legal": _LEGAL_DICT,
    "tecnico": _TECNICO_DICT,
}

_BUILTIN_MAPPINGS: list[DomainMapping] = [
    _TRIBUTARIO_COMPLIANCE_MAPPING,
    _LEGAL_TECNICO_MAPPING,
]


# ---------------------------------------------------------------------------
# DensityTranslator
# ---------------------------------------------------------------------------

class DensityTranslator:
    """
    Mediates communication between agents in different semantic domains.

    When agent-A (domain X) sends a message to agent-B (domain Y),
    the translator:
    1. Identifies high-density terms from domain X
    2. Maps to equivalent high-density terms in domain Y
    3. Preserves bridge-terms (dense in BOTH domains)
    4. Passes zero-terms unchanged (delimiters, metadata, scores)

    The translator acts as optional middleware on the Mycelium.
    When disabled (default), messages flow unchanged.
    """

    def __init__(self, use_density_translation: bool = False) -> None:
        self.enabled = use_density_translation
        self._dictionaries: dict[str, DomainDictionary] = dict(_BUILTIN_DICTIONARIES)
        self._mappings: list[DomainMapping] = list(_BUILTIN_MAPPINGS)
        # Precomputed lookup: (source, target) → DomainMapping
        self._mapping_index: dict[tuple[str, str], DomainMapping] = {}
        self._rebuild_index()

    # ------------------------------------------------------------------
    # Registry management
    # ------------------------------------------------------------------

    def register_domain(self, dictionary: DomainDictionary) -> None:
        """Register a new domain dictionary."""
        self._dictionaries[dictionary.domain] = dictionary
        logger.info("density: registered domain '%s' (%d terms)",
                     dictionary.domain, len(dictionary.high_terms))

    def register_mapping(self, mapping: DomainMapping) -> None:
        """Register a domain-to-domain mapping."""
        self._mappings.append(mapping)
        self._rebuild_index()
        logger.info("density: registered mapping '%s' → '%s' (%d terms)",
                     mapping.source_domain, mapping.target_domain,
                     len(mapping.term_map))

    def _rebuild_index(self) -> None:
        """Rebuild the (source, target) → mapping lookup."""
        self._mapping_index.clear()
        for m in self._mappings:
            self._mapping_index[(m.source_domain, m.target_domain)] = m
            # Build reverse mapping automatically
            reverse_key = (m.target_domain, m.source_domain)
            if reverse_key not in self._mapping_index:
                reverse = DomainMapping(
                    source_domain=m.target_domain,
                    target_domain=m.source_domain,
                    term_map={v: k for k, v in m.term_map.items()},
                    bridge_terms=set(m.bridge_terms),
                )
                self._mapping_index[reverse_key] = reverse

    # ------------------------------------------------------------------
    # Term classification
    # ------------------------------------------------------------------

    def classify_term(self, term: str, domain: str) -> TermDensity:
        """Classify a term's semiotic density within a domain."""
        dictionary = self._dictionaries.get(domain)
        if not dictionary:
            return TermDensity.LOW

        # Check zero-term patterns
        for pattern in dictionary.zero_patterns:
            if re.match(pattern, term, re.IGNORECASE):
                return TermDensity.ZERO

        # Check if it's a high-density term
        term_lower = term.lower()
        for high_term in dictionary.high_terms:
            if high_term.lower() == term_lower:
                return TermDensity.HIGH

        return TermDensity.LOW

    def classify_term_pair(
        self, term: str, source_domain: str, target_domain: str
    ) -> TermDensity:
        """
        Classify considering both domains. A term dense in both is a BRIDGE term.
        """
        mapping = self._mapping_index.get((source_domain, target_domain))
        if mapping and term.lower() in {bt.lower() for bt in mapping.bridge_terms}:
            return TermDensity.BRIDGE

        return self.classify_term(term, source_domain)

    # ------------------------------------------------------------------
    # Translation
    # ------------------------------------------------------------------

    def translate_term(
        self, term: str, source_domain: str, target_domain: str
    ) -> str:
        """
        Translate a single term from source to target domain.

        Rules:
        - ZERO terms → pass through unchanged
        - BRIDGE terms → preserved as-is
        - HIGH density → mapped to target domain equivalent
        - LOW density → pass through unchanged
        """
        if source_domain == target_domain:
            return term

        mapping = self._mapping_index.get((source_domain, target_domain))
        if not mapping:
            return term

        # Check bridge terms first
        if term.lower() in {bt.lower() for bt in mapping.bridge_terms}:
            return term

        # Check zero patterns in source domain
        src_dict = self._dictionaries.get(source_domain)
        if src_dict:
            for pattern in src_dict.zero_patterns:
                if re.match(pattern, term, re.IGNORECASE):
                    return term

        # Check term map (case-insensitive lookup, preserve original case style)
        term_lower = term.lower()
        for src_term, tgt_term in mapping.term_map.items():
            if src_term.lower() == term_lower:
                # Preserve capitalization style of the original
                if term[0].isupper():
                    return tgt_term.capitalize()
                return tgt_term

        return term

    def translate_text(
        self, text: str, source_domain: str, target_domain: str
    ) -> str:
        """
        Translate all high-density terms in a text from source to target domain.

        Uses longest-match-first to handle multi-word terms correctly.
        Zero-terms and bridge-terms pass through unchanged.
        """
        if not self.enabled:
            return text

        if source_domain == target_domain:
            return text

        mapping = self._mapping_index.get((source_domain, target_domain))
        if not mapping:
            logger.debug("density: no mapping for '%s' → '%s'",
                         source_domain, target_domain)
            return text

        # Sort terms by length (longest first) for greedy matching
        sorted_terms = sorted(mapping.term_map.keys(), key=len, reverse=True)

        result = text
        for src_term in sorted_terms:
            tgt_term = mapping.term_map[src_term]
            # Case-insensitive replacement preserving boundaries
            pattern = re.compile(re.escape(src_term), re.IGNORECASE)
            result = pattern.sub(tgt_term, result)

        return result

    def translate_payload(
        self, payload: Any, source_domain: str, target_domain: str
    ) -> Any:
        """
        Translate a message payload. Handles:
        - str: direct text translation
        - dict: recursive translation of string values (keys are zero-terms)
        - list: recursive translation of each element
        - other types: pass through (zero-term behavior)
        """
        if not self.enabled:
            return payload

        if isinstance(payload, str):
            return self.translate_text(payload, source_domain, target_domain)

        if isinstance(payload, dict):
            return {
                k: self.translate_payload(v, source_domain, target_domain)
                for k, v in payload.items()
            }

        if isinstance(payload, list):
            return [
                self.translate_payload(item, source_domain, target_domain)
                for item in payload
            ]

        # Numeric, bool, None, etc. — zero-terms, pass through
        return payload

    # ------------------------------------------------------------------
    # Mycelium middleware integration
    # ------------------------------------------------------------------

    def create_middleware(self):
        """
        Return a message handler wrapper that translates messages.

        Usage with Mycelium:
            translator = DensityTranslator(use_density_translation=True)
            middleware = translator.create_middleware()

            # Wrap an existing handler:
            original_handler = agent._handle_message
            agent._handle_message = middleware(
                original_handler,
                target_domain="tecnico",
            )
        """
        translator = self

        def middleware_factory(handler, target_domain: str):
            async def wrapped_handler(msg):
                source_domain = msg.metadata.get("domain", "")
                if (
                    translator.enabled
                    and source_domain
                    and source_domain != target_domain
                ):
                    msg.payload = translator.translate_payload(
                        msg.payload, source_domain, target_domain
                    )
                    msg.metadata["_density_translated"] = True
                    msg.metadata["_density_source_domain"] = source_domain
                    msg.metadata["_density_target_domain"] = target_domain
                    logger.debug(
                        "density: translated message %s from '%s' to '%s'",
                        msg.id, source_domain, target_domain,
                    )
                await handler(msg)
            return wrapped_handler

        return middleware_factory

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def get_available_domains(self) -> list[str]:
        """Return list of registered domains."""
        return list(self._dictionaries.keys())

    def get_available_mappings(self) -> list[tuple[str, str]]:
        """Return list of available (source, target) mapping pairs."""
        return list(self._mapping_index.keys())

    def get_mapping_coverage(
        self, source_domain: str, target_domain: str
    ) -> dict[str, Any]:
        """Return coverage statistics for a domain pair."""
        mapping = self._mapping_index.get((source_domain, target_domain))
        if not mapping:
            return {"exists": False}

        src_dict = self._dictionaries.get(source_domain)
        src_terms = len(src_dict.high_terms) if src_dict else 0

        return {
            "exists": True,
            "source_domain": source_domain,
            "target_domain": target_domain,
            "mapped_terms": len(mapping.term_map),
            "bridge_terms": len(mapping.bridge_terms),
            "source_high_terms": src_terms,
            "coverage": len(mapping.term_map) / max(1, src_terms),
        }

    def summary(self) -> dict[str, Any]:
        """Return a summary of the translator state."""
        return {
            "enabled": self.enabled,
            "domains": len(self._dictionaries),
            "domain_names": list(self._dictionaries.keys()),
            "mappings": len(self._mapping_index),
            "mapping_pairs": [
                f"{s}→{t}" for s, t in self._mapping_index.keys()
            ],
        }
