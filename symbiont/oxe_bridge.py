"""
OXÉ Bridge — SYMBIONT ↔ OXÉ API Integration

Conecta o organismo SYMBIONT ao OXÉ API, mapeando as castes do SYMBIONT
para os agentes especializados do OXÉ.

Mapeamento Caste → Agente OXÉ:
  Scout (Tier 0)  → busca paralela: jurisprudência + legislação + doutrina
  Media (Tier 1)  → construção: LexiaForge (redação) + JurisGuard (revisão)
  Major (Tier 2)  → estratégia: OXÉ Curador (jurimetria) + Neuropersuasão
  Minima (Suport) → formatação: Design Jurídico (.docx/.pdf)

Pipeline Premium (3 waves):
  Wave 1 (Scout)  → pesquisa paralela em todos os corpora
  Wave 2 (Media+Major) → análise estratégica + redação + blindagem
  Wave 3 (Minima) → formatação ABNT + entrega .docx

Configuração via env vars (nenhuma credencial hardcoded):
  OXE_URL       — URL base da API  (default: http://localhost:8500)
  OXE_EMAIL     — e-mail de login
  OXE_PASSWORD  — senha de login

Uso:
    from symbiont.oxe_bridge import OXEBridge

    bridge = OXEBridge()                        # lê env vars
    result = await bridge.run_premium(
        "elabore recurso sobre ISS na prestação de serviços"
    )
    print(result.wave3_peca)
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import time
from dataclasses import dataclass, field
from typing import Any

import requests

logger = logging.getLogger(__name__)

# ─── Configuração via env vars ─────────────────────────────────────────────────

OXE_DEFAULT_URL = "http://localhost:8500"
TOKEN_TTL = 82800  # 23h — renova antes de expirar (token válido por 24h)


# ─── Modelo de custo por tarefa ───────────────────────────────────────────────

COST_TIERS: dict[str, dict] = {
    "free":    {"model": "ollama/qwen3:8b",   "cost_usd": 0.000},
    "cheap":   {"model": "glm-5",              "cost_usd": 0.010},
    "medium":  {"model": "glm-5-turbo",        "cost_usd": 0.012},
    "high":    {"model": "glm-5.1",            "cost_usd": 0.015},
    "premium": {"model": "claude-sonnet-4-6",  "cost_usd": 0.060},
}

WAVE_COST: dict[str, str] = {
    "wave1_search":     "free",    # busca → Ollama local grátis
    "wave2_strategy":   "cheap",   # jurimetria → GLM barato
    "wave2_persuasion": "medium",  # neuropersuasão → GLM médio
    "wave2_draft":      "high",    # redação → GLM alto ou Claude
    "wave2_review":     "cheap",   # revisão → GLM barato
    "wave3_format":     "free",    # formatação → Ollama local grátis
}


# ─── Resultado do pipeline ────────────────────────────────────────────────────

@dataclass
class PremiumResult:
    query:                str
    wave1_jurisprudencia: list[dict] = field(default_factory=list)
    wave1_legislacao:     list[dict] = field(default_factory=list)
    wave1_doutrina:       list[dict] = field(default_factory=list)
    wave2_jurimetria:     str = ""
    wave2_persuasao:      str = ""
    wave2_rascunho:       str = ""
    wave2_revisado:       str = ""
    wave3_peca:           str = ""
    docx_path:            str = ""
    custo_estimado_usd:   float = 0.0
    tempo_total_s:        float = 0.0
    erros:                list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


# ─── OXÉ Bridge ──────────────────────────────────────────────────────────────

class OXEBridge:
    """
    Bridge entre SYMBIONT e OXÉ API.

    Gerencia autenticação JWT com renovação automática (TOKEN_TTL = 23h).
    Todas as credenciais vêm de env vars — nenhuma hardcoded.
    """

    def __init__(
        self,
        oxe_url: str | None = None,
        email: str | None = None,
        password: str | None = None,
    ) -> None:
        self.oxe_url   = (oxe_url or os.environ.get("OXE_URL", OXE_DEFAULT_URL)).rstrip("/")
        self._email    = email    or os.environ.get("OXE_EMAIL", "")
        self._password = password or os.environ.get("OXE_PASSWORD", "")
        self._token    = ""
        self._token_ts = 0.0
        self._session  = requests.Session()
        self._session.headers.update({"Content-Type": "application/json"})

    # ── Auth ──────────────────────────────────────────────────────────────────

    def _get_token(self) -> str:
        """Retorna token JWT válido, renovando se expirado."""
        if self._token and (time.time() - self._token_ts) < TOKEN_TTL:
            return self._token
        if not self._email or not self._password:
            raise RuntimeError(
                "OXE_EMAIL e OXE_PASSWORD devem estar definidos como env vars"
            )
        r = self._session.post(
            f"{self.oxe_url}/login",
            json={"email": self._email, "password": self._password},
            timeout=15,
        )
        r.raise_for_status()
        self._token    = r.json()["token"]
        self._token_ts = time.time()
        logger.debug("oxe_bridge: token renovado")
        return self._token

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._get_token()}"}

    # ── Chamadas OXÉ API ──────────────────────────────────────────────────────

    def buscar(
        self, query: str, collection: str = "oxe_jurisprudencia", top_k: int = 5
    ) -> list[dict]:
        """Busca semântica em qualquer coleção OXÉ."""
        try:
            r = self._session.post(
                f"{self.oxe_url}/buscar",
                headers=self._headers(),
                json={"query": query, "top_k": top_k, "collection": collection},
                timeout=30,
            )
            r.raise_for_status()
            return r.json().get("resultados", [])
        except Exception as exc:
            logger.warning("oxe_bridge: busca falhou (%s): %s", collection, exc)
            return []

    def chat(
        self,
        message: str,
        skill: str | None = None,
        conversation_id: str = "premium",
        tier: str = "high",
    ) -> str:
        """Envia mensagem ao OXÉ com skill específica."""
        payload: dict[str, Any] = {
            "message": message,
            "conversation_id": conversation_id,
        }
        if skill:
            payload["skill"] = skill
        try:
            r = self._session.post(
                f"{self.oxe_url}/chat",
                headers=self._headers(),
                json=payload,
                timeout=120,
            )
            r.raise_for_status()
            return r.json().get("response", "")
        except Exception as exc:
            logger.warning("oxe_bridge: chat falhou (skill=%s): %s", skill, exc)
            return ""

    def escritorio_docx(self, conversation_id: str) -> bytes | None:
        """Baixa o .docx gerado pelo Escritório Virtual."""
        try:
            r = self._session.get(
                f"{self.oxe_url}/escritorio/{conversation_id}/docx",
                headers=self._headers(),
                timeout=60,
            )
            r.raise_for_status()
            return r.content
        except Exception as exc:
            logger.warning("oxe_bridge: docx falhou: %s", exc)
            return None

    def health(self) -> dict:
        """Verifica saúde do OXÉ."""
        try:
            r = self._session.get(f"{self.oxe_url}/health", timeout=10)
            return r.json()
        except Exception:
            return {"api": "offline"}

    # ── Pipeline Premium ──────────────────────────────────────────────────────

    async def run_premium(
        self,
        query: str,
        conv_id: str | None = None,
        estilo_advogado: str = "",
    ) -> PremiumResult:
        """
        Executa o pipeline premium completo (3 waves).

        Wave 1 — Inteligência (paralela, Ollama grátis):
          Busca semântica em jurisprudência, legislação e doutrina.

        Wave 2 — Estratégia & Construção (GLM/Claude):
          Jurimetria → Neuropersuasão → LexiaForge → JurisGuard.

        Wave 3 — Entrega (Ollama grátis):
          Formatação ABNT + .docx.
        """
        t0 = time.time()
        conv_id = conv_id or f"premium-{int(t0)}"
        result  = PremiumResult(query=query)
        custo   = 0.0

        logger.info("oxe_bridge: pipeline premium — '%s'", query[:80])

        # ── Wave 1: Inteligência (paralela) ──────────────────────────────────
        logger.info("oxe_bridge: Wave 1 — pesquisa paralela")

        loop = asyncio.get_running_loop()
        juris_f = loop.run_in_executor(None, self.buscar, query, "oxe_jurisprudencia", 5)
        legis_f = loop.run_in_executor(None, self.buscar, query, "oxe_legislacao", 5)
        doutr_f = loop.run_in_executor(None, self.buscar, query, "oxe_regulatorio", 3)

        (
            result.wave1_jurisprudencia,
            result.wave1_legislacao,
            result.wave1_doutrina,
        ) = await asyncio.gather(juris_f, legis_f, doutr_f)

        logger.info(
            "oxe_bridge: Wave 1 concluída — juris=%d, legis=%d, doutr=%d",
            len(result.wave1_jurisprudencia),
            len(result.wave1_legislacao),
            len(result.wave1_doutrina),
        )

        # ── Wave 2A: Jurimetria ───────────────────────────────────────────────
        logger.info("oxe_bridge: Wave 2A — Jurimetria")

        juris_context = "\n".join(
            f"- {r.get('tribunal','?')} ({r.get('data','?')}): {r.get('ementa','')[:120]}"
            for r in result.wave1_jurisprudencia
        )
        juris_prompt = (
            f"QUERY: {query}\n\n"
            f"JURISPRUDÊNCIA ENCONTRADA:\n{juris_context}\n\n"
            "Analise a probabilidade de sucesso desta tese considerando:\n"
            "1. Tendência predominante dos tribunais\n"
            "2. Análise por câmara/turma quando possível\n"
            "3. Pontos fortes e fracos da posição\n"
            "Seja objetivo e quantitativo quando possível."
        )
        result.wave2_jurimetria = await loop.run_in_executor(
            None, self.chat, juris_prompt, "biaslens", f"{conv_id}-juri", "cheap"
        )
        custo += COST_TIERS["cheap"]["cost_usd"]

        # ── Wave 2B: Neuropersuasão ───────────────────────────────────────────
        logger.info("oxe_bridge: Wave 2B — Neuropersuasão")

        persuasao_prompt = (
            f"QUERY: {query}\n\n"
            f"ANÁLISE JURIMETRIA:\n{result.wave2_jurimetria[:500]}\n\n"
            "Identifique:\n"
            "1. Tom argumentativo ideal para este juízo (técnico/emocional/assertivo)\n"
            "2. Elementos retóricos mais eficazes baseados nos julgados\n"
            "3. Argumentos que mais ressoam com este tribunal\n"
            "4. Gatilhos cognitivos que devem ser ativados\n"
            "Baseie-se nos padrões reais das decisões encontradas."
        )
        result.wave2_persuasao = await loop.run_in_executor(
            None, self.chat, persuasao_prompt, None, f"{conv_id}-persuasao", "medium"
        )
        custo += COST_TIERS["medium"]["cost_usd"]

        # ── Wave 2C: Redação (LexiaForge) ────────────────────────────────────
        logger.info("oxe_bridge: Wave 2C — LexiaForge redação")

        legis_context = "\n".join(
            f"- {r.get('titulo','?')}: {r.get('ementa','')[:100]}"
            for r in result.wave1_legislacao
        )
        draft_prompt = (
            f"DEMANDA: {query}\n\n"
            f"JURISPRUDÊNCIA:\n{juris_context}\n\n"
            f"LEGISLAÇÃO APLICÁVEL:\n{legis_context}\n\n"
            f"ANÁLISE JURIMETRIA:\n{result.wave2_jurimetria[:400]}\n\n"
            f"CALIBRAÇÃO RETÓRICA:\n{result.wave2_persuasao[:300]}\n\n"
            + (f"ESTILO DO ADVOGADO:\n{estilo_advogado}\n\n" if estilo_advogado else "")
            + "Redija a peça jurídica completa em prosa fluida, "
              "incorporando todos os elementos acima. "
              "Estrutura: Preâmbulo → Fatos → Fundamentos Jurídicos → Pedidos."
        )
        result.wave2_rascunho = await loop.run_in_executor(
            None, self.chat, draft_prompt, "lexiaforge", f"{conv_id}-draft", "high"
        )
        custo += COST_TIERS["high"]["cost_usd"]

        # ── Wave 2D: Revisão (JurisGuard) ────────────────────────────────────
        logger.info("oxe_bridge: Wave 2D — JurisGuard revisão")

        review_prompt = (
            "Revise e fortaleça a peça abaixo, atuando como advogado adverso "
            "que tentará atacá-la. Identifique e corrija todos os pontos fracos.\n\n"
            f"PEÇA ORIGINAL:\n{result.wave2_rascunho[:3000]}"
        )
        result.wave2_revisado = await loop.run_in_executor(
            None, self.chat, review_prompt, "jurisguard", f"{conv_id}-review", "cheap"
        )
        custo += COST_TIERS["cheap"]["cost_usd"]

        # ── Wave 3: Formatação & Entrega ──────────────────────────────────────
        logger.info("oxe_bridge: Wave 3 — formatação")

        await loop.run_in_executor(
            None,
            self.chat,
            (
                "Formate e estruture a seguinte peça jurídica conforme padrão ABNT "
                f"e templates de grandes escritórios de SP:\n\n{result.wave2_revisado[:4000]}"
            ),
            None,
            f"{conv_id}-format",
            "free",
        )

        docx_bytes = await loop.run_in_executor(
            None, self.escritorio_docx, f"{conv_id}-format"
        )
        if docx_bytes:
            docx_path = os.path.join(
                tempfile.gettempdir(), f"oxe_premium_{conv_id}.docx"
            )
            with open(docx_path, "wb") as f:
                f.write(docx_bytes)
            result.docx_path = docx_path
            logger.info("oxe_bridge: .docx salvo em %s", docx_path)

        result.wave3_peca         = result.wave2_revisado
        result.custo_estimado_usd = custo
        result.tempo_total_s      = time.time() - t0

        logger.info(
            "oxe_bridge: pipeline concluído — tempo=%.1fs, custo=$%.3f, docx=%s",
            result.tempo_total_s,
            result.custo_estimado_usd,
            "✓" if result.docx_path else "✗",
        )
        return result


# ─── Router FastAPI (opcional) ────────────────────────────────────────────────
# PremiumRequest definido em nível de módulo para evitar forward-reference
# issues com Pydantic v2 quando o router é incluído em apps externos.

try:
    from pydantic import BaseModel as _BaseModel

    class PremiumRequest(_BaseModel):
        query:            str
        conversation_id:  str = ""
        estilo_advogado:  str = ""

except ImportError:
    PremiumRequest = None  # type: ignore[assignment,misc]


def create_premium_router(bridge: OXEBridge | None = None):
    """
    Cria o router FastAPI /premium para integração no gateway OXÉ.

    Uso em chat.py:
        from symbiont.oxe_bridge import create_premium_router
        app.include_router(create_premium_router())
    """
    try:
        from fastapi import APIRouter, HTTPException
    except ImportError:
        logger.warning("oxe_bridge: fastapi não instalado — router não disponível")
        return None

    if PremiumRequest is None:
        logger.warning("oxe_bridge: pydantic não instalado — router não disponível")
        return None

    router  = APIRouter(prefix="/premium", tags=["premium"])
    _bridge = bridge or OXEBridge()

    @router.post("")
    async def premium_endpoint(req: PremiumRequest):  # type: ignore[valid-type]
        """Pipeline premium multiagente (3 waves). Retorna peça completa + path .docx."""
        if not req.query.strip():
            raise HTTPException(400, "query obrigatória")
        try:
            result = await _bridge.run_premium(
                query=req.query,
                conv_id=req.conversation_id or None,
                estilo_advogado=req.estilo_advogado,
            )
            return result.to_dict()
        except Exception as exc:
            raise HTTPException(500, str(exc))

    @router.get("/health")
    async def premium_health():
        return {"bridge": "ok", "oxe": _bridge.health()}

    return router
