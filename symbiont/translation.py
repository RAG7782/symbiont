"""
symbiont/translation.py — TranslationLayer

Pipeline de tradução seletiva PT↔EN para ampliar acesso a modelos
sem suporte robusto a português.

Arquitetura:
    PT input
        → [tradutor rápido: PT→EN]  (llama-3.1-8b-instant via Groq)
        → [processador EN]           (qualquer modelo — callback)
        → [tradutor rápido: EN→PT]  (llama-3.1-8b-instant via Groq)
        → [refinador jurídico PT]    (callback — ex: glm-5-turbo)
        → PT output de alta qualidade

Uso no OXÉ bridge:
    layer = TranslationLayer(groq_key=os.environ["GROQ_API_KEY"])
    result = layer.juridical_pipeline(
        text=query_pt,
        processor_fn=lambda en: bridge.chat(en, tier="high"),
        refiner_fn=lambda pt: bridge.chat(pt, tier="medium"),
    )

Seletividade por wave (configurável):
    TRANSLATION_WAVES = {
        "wave2a_jurimetria": True,   # análise → beneficia de EN
        "wave2b_persuasao":  True,   # argumentação → beneficia de EN
        "wave2c_rascunho":   False,  # forma brasileira → manter PT
        "wave2d_revisao":    False,  # revisão de forma → manter PT
        "wave3_formato":     False,  # formatação ABNT → manter PT
    }
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Callable

logger = logging.getLogger(__name__)

# ── Configuração padrão de waves ──────────────────────────────────────────────

TRANSLATION_WAVES: dict[str, bool] = {
    "wave2a_jurimetria": True,   # raciocínio analítico — beneficia de EN
    "wave2b_persuasao":  True,   # argumentação estrutural — beneficia de EN
    "wave2c_rascunho":   False,  # forma jurídica brasileira — NÃO traduzir
    "wave2d_revisao":    False,  # revisão de forma — NÃO traduzir
    "wave3_formato":     False,  # formatação ABNT — NÃO traduzir
}

# ── Glossário jurídico bidirecional ───────────────────────────────────────────

_GLOSSARIO_PT_EN: dict[str, str] = {
    # Instâncias e recursos
    "acórdão": "court decision (collegiate ruling)",
    "agravo regimental": "internal appeal (regimento)",
    "agravo de instrumento": "interlocutory appeal",
    "embargos de declaração": "motion for clarification",
    "embargos de divergência": "divergence appeal",
    "recurso especial": "special appeal (STJ)",
    "recurso extraordinário": "extraordinary appeal (STF)",
    "mandado de segurança": "writ of mandamus",
    "habeas corpus": "habeas corpus",
    "ação declaratória": "declaratory action",
    "ação anulatória": "annulment action",
    "ação de repetição de indébito": "tax refund action",
    "tutela antecipada": "preliminary injunction",
    "liminar": "ex parte injunction",
    "sentença": "judgment",
    "trânsito em julgado": "res judicata",
    "petição inicial": "initial petition/complaint",
    "contestação": "statement of defense",
    "réu": "defendant",
    "autor": "plaintiff",
    # Direito tributário
    "fato gerador": "taxable event",
    "contribuinte": "taxpayer",
    "base de cálculo": "tax base",
    "alíquota": "tax rate",
    "crédito tributário": "tax credit",
    "lançamento tributário": "tax assessment",
    "prescrição tributária": "tax prescription",
    "decadência tributária": "tax lapse",
    "compensação tributária": "tax offset/compensation",
    "restituição tributária": "tax refund",
    "autuação fiscal": "tax audit assessment",
    "auto de infração": "notice of tax violation",
    "ICMS": "ICMS (state VAT on goods and services)",
    "ISS": "ISS (municipal services tax)",
    "IPI": "IPI (federal excise tax)",
    "PIS": "PIS (social contribution on revenue)",
    "COFINS": "COFINS (social contribution on revenue)",
    "IRPJ": "IRPJ (corporate income tax)",
    "CSLL": "CSLL (social contribution on net income)",
    "IOF": "IOF (financial transactions tax)",
    "contribuição previdenciária": "social security contribution",
    "Simples Nacional": "Simples Nacional (simplified tax regime)",
    "Lucro Real": "Lucro Real (actual profit tax regime)",
    "Lucro Presumido": "Lucro Presumido (presumed profit tax regime)",
    # Súmulas e jurisprudência
    "súmula vinculante": "binding precedent (súmula vinculante)",
    "súmula": "precedent ruling",
    "ementa": "headnote/syllabus",
    "tese jurídica": "legal thesis",
    "leading case": "leading case",
    "repercussão geral": "general repercussion (constitutional relevance)",
    "recurso repetitivo": "repetitive appeal (representative case)",
    "tema": "theme/topic (STF/STJ numbered precedent)",
    # Tribunais
    "STF": "STF (Brazilian Supreme Court)",
    "STJ": "STJ (Superior Court of Justice)",
    "TRF": "TRF (Federal Regional Court)",
    "TJ": "TJ (State Court of Justice)",
    "CARF": "CARF (Administrative Tax Appeals Council)",
    "TJSP": "TJSP (São Paulo State Court)",
    "TJRJ": "TJRJ (Rio de Janeiro State Court)",
    # Software e tecnologia (relevante para ICMS/ISS SaaS)
    "software como serviço": "software as a service (SaaS)",
    "licenciamento de software": "software licensing",
    "download de software": "software download",
    "circulação de mercadoria": "circulation of goods",
    "prestação de serviço": "service provision",
    "estabelecimento": "establishment/business location",
    # Processo administrativo
    "Fazenda Pública": "Public Treasury / Tax Authority",
    "Procuradoria": "Attorney General's Office / Tax Counsel",
    "execução fiscal": "tax enforcement action",
    "certidão negativa": "tax clearance certificate",
    "parcelamento": "tax installment program",
    "REFIS": "REFIS (tax debt restructuring program)",
}

# Inverso automático (EN→PT) — termos principais
_GLOSSARIO_EN_PT: dict[str, str] = {v: k for k, v in _GLOSSARIO_PT_EN.items()}


# ── Métricas de chamada ───────────────────────────────────────────────────────

@dataclass
class TranslationMetrics:
    wave: str = ""
    translation_applied: bool = False
    model_used: str = ""
    input_chars: int = 0
    output_chars: int = 0
    cache_hit: bool = False
    latency_ms: float = 0.0


# ── TranslationLayer ──────────────────────────────────────────────────────────

class TranslationLayer:
    """
    Camada de tradução seletiva PT↔EN para pipelines jurídicos.

    Thread-safe. Cache por (conv_id, hash(text)).
    Fallback gracioso: retorna PT original se tradução falha.
    """

    _GROQ_TRANSLATE_MODEL = "llama-3.3-70b-versatile"   # 70B melhor que 8B para juridiquês
    _GROQ_TRANSLATE_FAST  = "llama-3.1-8b-instant"      # ultra-rápido para textos simples
    _MAX_CHARS_FAST        = 600                          # abaixo disso, usar modelo rápido

    def __init__(
        self,
        groq_key: str,
        zai_key: str = "",
        wave_config: dict[str, bool] | None = None,
    ) -> None:
        self._groq_key  = groq_key
        self._zai_key   = zai_key
        self._wave_cfg  = wave_config or TRANSLATION_WAVES.copy()
        self._cache: dict[str, str] = {}
        self._cache_lock = Lock()
        self._metrics: list[TranslationMetrics] = []

    # ── API pública ───────────────────────────────────────────────────────────

    def should_translate(self, wave: str) -> bool:
        """Retorna True se a wave deve usar pipeline de tradução."""
        return self._wave_cfg.get(wave, False)

    def translate_pt_en(
        self,
        text: str,
        conv_id: str = "",
        context: str = "juridico",
    ) -> str:
        """Traduz PT→EN com glossário jurídico injetado. Cache por conv_id+hash."""
        return self._translate(text, "pt_to_en", conv_id, context)

    def translate_en_pt(
        self,
        text: str,
        conv_id: str = "",
        context: str = "juridico",
    ) -> str:
        """Traduz EN→PT com glossário jurídico injetado."""
        return self._translate(text, "en_to_pt", conv_id, context)

    def juridical_pipeline(
        self,
        text: str,
        processor_fn: Callable[[str], str],
        refiner_fn: Callable[[str], str],
        conv_id: str = "",
        wave: str = "",
    ) -> tuple[str, TranslationMetrics]:
        """
        Pipeline completo: PT → EN → processador → EN→PT → refinador jurídico.

        Args:
            text:         Texto em PT para processar
            processor_fn: Função que recebe texto EN e retorna resultado EN
                          (ex: lambda en: bridge.chat(en, tier="high"))
            refiner_fn:   Função que recebe texto PT e retorna texto PT refinado
                          (ex: lambda pt: bridge.chat(pt, tier="medium"))
            conv_id:      ID da conversa (para cache)
            wave:         Nome da wave (para logging e decisão de uso)

        Returns:
            (texto_refinado_pt, métricas)
        """
        t0 = time.time()
        metrics = TranslationMetrics(wave=wave, input_chars=len(text))

        try:
            # Passo 1: PT → EN
            text_en = self.translate_pt_en(text, conv_id)
            metrics.translation_applied = True
            metrics.model_used = self._GROQ_TRANSLATE_MODEL

            # Passo 2: processar em EN (modelo potente)
            result_en = processor_fn(text_en)
            if not result_en:
                logger.warning("translation: processor_fn retornou vazio — usando fallback PT")
                result_pt_raw = processor_fn(text)   # tenta direto em PT
                metrics.translation_applied = False
            else:
                # Passo 3: EN → PT
                result_pt_raw = self.translate_en_pt(result_en, conv_id)

            # Passo 4: refinamento jurídico PT
            result_final = refiner_fn(result_pt_raw) if result_pt_raw else ""

            metrics.output_chars = len(result_final)
            metrics.latency_ms   = (time.time() - t0) * 1000

            # Warning se output muito menor que input (possível truncagem)
            if result_final and len(result_final) < len(text) * 0.5:
                logger.warning(
                    "translation: output (%d chars) < 50%% do input (%d chars) — "
                    "possível truncagem na tradução",
                    len(result_final), len(text),
                )

            self._metrics.append(metrics)
            logger.info(
                "translation[%s]: %d→EN→PT→refinado=%d chars em %.0fms (cache=%s)",
                wave, len(text), len(result_final), metrics.latency_ms, metrics.cache_hit,
            )
            return result_final, metrics

        except Exception as exc:
            logger.warning("translation[%s]: pipeline falhou (%s) — fallback direto PT", wave, exc)
            metrics.translation_applied = False
            metrics.latency_ms = (time.time() - t0) * 1000
            # Fallback gracioso: processar em PT diretamente
            result = refiner_fn(processor_fn(text))
            metrics.output_chars = len(result)
            self._metrics.append(metrics)
            return result, metrics

    def cache_stats(self) -> dict:
        """Retorna estatísticas do cache."""
        hits = sum(1 for m in self._metrics if m.cache_hit)
        total = len(self._metrics)
        return {
            "total_calls": total,
            "cache_hits": hits,
            "hit_rate": hits / total if total else 0.0,
            "cache_size": len(self._cache),
        }

    # ── Internos ──────────────────────────────────────────────────────────────

    def _translate(self, text: str, direction: str, conv_id: str, context: str) -> str:
        """Traduz com cache, glossário e fallback."""
        if not text.strip():
            return text

        cache_key = hashlib.md5(f"{conv_id}:{direction}:{text}".encode()).hexdigest()

        with self._cache_lock:
            if cache_key in self._cache:
                logger.debug("translation cache hit: %s", cache_key[:8])
                return self._cache[cache_key]

        # Dividir em parágrafos (preservar coerência)
        paragraphs = [p for p in text.split("\n\n") if p.strip()]
        if len(paragraphs) == 1 and len(text) > 1500:
            # Texto longo sem parágrafos: dividir em sentenças
            paragraphs = re.split(r"(?<=[.!?])\s+", text)
            paragraphs = self._merge_chunks(paragraphs, max_chars=1200)

        translated_parts: list[str] = []
        for chunk in paragraphs:
            result = self._translate_chunk(chunk, direction, context)
            translated_parts.append(result)

        result = "\n\n".join(translated_parts)

        with self._cache_lock:
            self._cache[cache_key] = result

        return result

    def _translate_chunk(self, text: str, direction: str, context: str) -> str:
        """Traduz um chunk único via Groq, com fallback Z.ai."""
        is_fast = len(text) <= self._MAX_CHARS_FAST
        model   = self._GROQ_TRANSLATE_FAST if is_fast else self._GROQ_TRANSLATE_MODEL

        if direction == "pt_to_en":
            glossario_str = "\n".join(
                f"  '{pt}' → '{en}'" for pt, en in list(_GLOSSARIO_PT_EN.items())[:40]
            )
            system = (
                "You are a legal translator specializing in Brazilian law. "
                "Translate the following Portuguese legal text to English. "
                "Preserve markdown formatting (headers, bullets, bold). "
                "Use these mandatory term translations:\n" + glossario_str +
                "\n\nReturn ONLY the translated text, no explanations."
            )
            user = f"Translate to English:\n\n{text}"
        else:
            glossario_str = "\n".join(
                f"  '{en}' → '{pt}'" for en, pt in list(_GLOSSARIO_EN_PT.items())[:40]
            )
            system = (
                "Você é um tradutor jurídico especializado em direito brasileiro. "
                "Traduza o seguinte texto jurídico em inglês para português brasileiro formal. "
                "Preserve formatação markdown (cabeçalhos, listas, negrito). "
                "Use estas traduções obrigatórias:\n" + glossario_str +
                "\n\nRetorne APENAS o texto traduzido, sem explicações."
            )
            user = f"Traduza para português jurídico brasileiro:\n\n{text}"

        # Tentativa 1: Groq
        try:
            import requests
            r = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {self._groq_key}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user",   "content": user},
                    ],
                    "max_tokens": min(len(text) * 3, 2000),
                    "temperature": 0.1,   # baixo: tradução precisa de consistência
                },
                timeout=20,
            )
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"].strip()
            logger.warning("translation Groq: status %d", r.status_code)
        except Exception as exc:
            logger.warning("translation Groq falhou: %s", exc)

        # Tentativa 2: Z.ai glm-5 (fallback)
        if self._zai_key:
            try:
                import requests
                r = requests.post(
                    "https://api.z.ai/api/paas/v4/chat/completions",
                    headers={"Authorization": f"Bearer {self._zai_key}", "Content-Type": "application/json"},
                    json={
                        "model": "glm-5",
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user",   "content": user},
                        ],
                        "max_tokens": 1500,
                        "temperature": 0.1,
                    },
                    timeout=30,
                )
                if r.status_code == 200:
                    return r.json()["choices"][0]["message"]["content"].strip()
            except Exception as exc:
                logger.warning("translation Z.ai fallback falhou: %s", exc)

        # Fallback final: retornar texto original (degradação graciosa)
        logger.warning("translation: todos os modelos falharam — retornando texto original")
        return text

    @staticmethod
    def _merge_chunks(sentences: list[str], max_chars: int) -> list[str]:
        """Agrupa sentenças em chunks de até max_chars caracteres."""
        chunks, current = [], ""
        for s in sentences:
            if len(current) + len(s) > max_chars and current:
                chunks.append(current.strip())
                current = s
            else:
                current += " " + s
        if current.strip():
            chunks.append(current.strip())
        return chunks or [""]
