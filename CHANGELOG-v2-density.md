# CHANGELOG — SYMBIONT v2-density

## v2.0.0-density (2026-04-05)

### Added: System 9 — DensityTranslator (Semiotic Density Bridge)

New optional middleware that mediates communication between agents operating in
different semantic domains. Inspired by the Semiotic Density principle from
Artesanato Digital: terms carry implicit semantic fields, and cross-domain
communication requires mapping these density profiles.

**Biological analogy**: chemical signal translation at species boundaries in
symbiotic relationships (mycorrhizal networks translating plant root signals
into fungal chemical signals and vice-versa).

#### Architecture

- `DensityTranslator` class in `symbiont/core/density_translator.py`
- Integrates as **optional middleware** on the Mycelium message bus
- Default: `use_density_translation=False` (preserves original behavior — zero breaking changes)
- When enabled, translates message payloads based on sender/receiver domain metadata

#### Term Classification (4 density levels)

| Level | Behavior | Example |
|-------|----------|---------|
| ZERO | Pass through unchanged | `R$ 1.000,00`, `art. 150`, numeric scores |
| LOW | Pass through unchanged | Generic words not domain-specific |
| HIGH | Mapped to target domain equivalent | `fato gerador` -> `triggering event` |
| BRIDGE | Preserved as-is (dense in both domains) | `SPED`, `compliance`, `prazo` |

#### Built-in Domain Dictionaries (4)

1. **tributario** — Brazilian tax law terms (12 high-density terms)
2. **compliance** — Regulatory compliance terms (12 high-density terms)
3. **legal** — Brazilian procedural law terms (12 high-density terms)
4. **tecnico** — Technical/operational equivalents (12 high-density terms)

#### Built-in Mappings (2 pairs, 4 directions)

1. `tributario <-> compliance` (12 term pairs, 5 bridge terms)
2. `legal <-> tecnico` (12 term pairs, 4 bridge terms)

Reverse mappings auto-generated automatically.

#### Features

- **Term-level translation**: `translate_term(term, source, target)`
- **Text-level translation**: `translate_text(text, source, target)` with longest-match-first
- **Payload translation**: `translate_payload(payload, source, target)` handles str/dict/list/primitives recursively
- **Middleware factory**: `create_middleware()` wraps Mycelium message handlers
- **Custom domain registration**: `register_domain()` + `register_mapping()`
- **Introspection**: `summary()`, `get_mapping_coverage()`, `get_available_domains()`

#### Middleware Integration Pattern

```python
from symbiont.core.density_translator import DensityTranslator

translator = DensityTranslator(use_density_translation=True)
middleware = translator.create_middleware()

# Wrap any message handler with domain-aware translation
wrapped_handler = middleware(original_handler, target_domain="compliance")

# Messages with metadata={"domain": "tributario"} will be auto-translated
mycelium.subscribe("channel", "agent-id", wrapped_handler)

# Sender must include domain in metadata:
await mycelium.publish("channel", payload="O fato gerador...",
                       sender_id="trib-agent",
                       metadata={"domain": "tributario"})
```

#### Test Coverage

- `tests/test_density_translator.py` — 32 tests covering:
  - Term classification (zero, low, high, bridge)
  - Term translation (forward, reverse, bridge preservation, zero pass-through)
  - Text translation (multi-word, longest-match, disabled state)
  - Payload translation (str, dict, list, nested, None, numeric)
  - Middleware integration (with and without domain metadata, disabled state)
  - Full Mycelium integration (publish -> middleware -> translated delivery)
  - Domain/mapping registration and introspection

### Modified

- `symbiont/core/__init__.py` — Added `DensityTranslator` to exports

### Connection to Semiotic Density Theory

This implementation operationalizes the 7th foundation of Artesanato Digital:

> "Terms carry implicit semantic fields. A Framework Injection is a composition
> of semiotic densities."

In multi-agent systems, agents operating in different domains use terms that
carry domain-specific density. Without translation, a `fato gerador` sent from
a tax-law agent to a compliance agent carries zero usable density for the
receiver. The DensityTranslator preserves the *semantic load* across domain
boundaries while respecting the structural invariants (zero-terms) that hold
messages together.
