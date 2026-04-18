"""
symbiont/legal_assembly.py — LegalAssembly

Ensemble de modelos para análise jurídica: múltiplos agentes especializados
executam em paralelo, um Aggregator sintetiza, um Adversarial ataca, e um
Refinador produz o output final em PT.

Inspirado em "Mixture of Agents" (Together AI, 2024):
ensembles de modelos medianos superam modelos individuais superiores em 73% dos casos.

Arquitetura:
    query + shared_context
        ↓
    [Planner]       — distribui papéis por modelo disponível (ciente de rate limit)
        ↓ (paralelo, timeout=60s por agente)
    [Jurimetria]    — análise quantitativa de probabilidades e precedentes (EN)
    [Argumentação]  — construção retórica e estratégia processual (EN)
    [Precedentes]   — identificação de súmulas e teses aplicáveis (PT)
        ↓
    [Aggregator]    — síntese estruturada (modelo mais forte disponível)
        ↓
    [Adversarial]   — ataca a síntese com persona configurável (ex: "Procurador")
        ↓
    [Refinador PT]  — incorpora críticas e produz output final jurídico
        ↓
    AssemblyResult

Integração no OXÉ bridge:
    assembly = LegalAssembly(
        groq_key=os.environ["GROQ_API_KEY"],
        zai_key=os.environ["ZAI_API_KEY"],
        translation_layer=TranslationLayer(groq_key=...),
    )
    result = await assembly.run(
        query="ICMS sobre SaaS — município competente",
        shared_context={"juris": wave1_juris, "legis": wave1_legis},
        adversarial_persona="Procurador do Estado de São Paulo",
    )
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from threading import Lock
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from symbiont.translation import TranslationLayer

logger = logging.getLogger(__name__)

# ── Rate Limit Tracker ────────────────────────────────────────────────────────

class RateLimitTracker:
    """
    Singleton thread-safe que rastreia janelas de 429 por modelo.
    Permite ao Planner escolher modelos disponíveis agora.
    """

    _instance: RateLimitTracker | None = None
    _lock = Lock()
    _WINDOW_S = 60   # janela de rate limit (segundos)

    def __new__(cls) -> RateLimitTracker:
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._hits: dict[str, list[float]] = {}
                cls._instance._hits_lock = Lock()
            return cls._instance

    def record_429(self, model_id: str) -> None:
        """Registra um 429 para o modelo."""
        with self._hits_lock:
            self._hits.setdefault(model_id, []).append(time.time())

    def is_available(self, model_id: str) -> bool:
        """Retorna True se o modelo não tem 429s recentes na janela."""
        now = time.time()
        with self._hits_lock:
            hits = self._hits.get(model_id, [])
            recent = [t for t in hits if now - t < self._WINDOW_S]
            self._hits[model_id] = recent   # limpar antigos
            return len(recent) == 0

    def next_available(self, candidates: list[str]) -> str | None:
        """Retorna o primeiro modelo disponível da lista de candidatos."""
        return next((m for m in candidates if self.is_available(m)), None)

    def status(self) -> dict[str, bool]:
        """Retorna disponibilidade de todos os modelos rastreados."""
        return {m: self.is_available(m) for m in self._hits}


# ── Resultado ─────────────────────────────────────────────────────────────────

@dataclass
class AssemblyResult:
    query:        str = ""
    jurimetria:   str = ""
    argumentacao: str = ""
    precedentes:  str = ""
    sintese:      str = ""
    adversarial:  str = ""
    refinado:     str = ""
    models_used:  dict[str, str] = field(default_factory=dict)
    quality_score: float = 0.0    # 0-1, calculado pelo Aggregator
    latency_s:    float = 0.0
    tokens_total: int   = 0
    erros:        list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "query":         self.query,
            "jurimetria":    self.jurimetria,
            "argumentacao":  self.argumentacao,
            "precedentes":   self.precedentes,
            "sintese":       self.sintese,
            "adversarial":   self.adversarial,
            "refinado":      self.refinado,
            "models_used":   self.models_used,
            "quality_score": self.quality_score,
            "latency_s":     round(self.latency_s, 1),
            "erros":         self.erros,
        }


# ── Catálogo de modelos por papel ─────────────────────────────────────────────

# Papel → lista de candidatos em ordem de preferência (provider:model)
_ROLE_CANDIDATES: dict[str, list[str]] = {
    "jurimetria":    [   # raciocínio analítico EN — modelos fortes
        "groq:qwen/qwen3-32b",
        "groq:llama-3.3-70b-versatile",
        "groq:openai/gpt-oss-120b",
        "zai:glm-5-turbo",
    ],
    "argumentacao":  [   # construção retórica EN
        "groq:llama-3.3-70b-versatile",
        "groq:openai/gpt-oss-120b",
        "groq:qwen/qwen3-32b",
        "zai:glm-5-turbo",
    ],
    "precedentes":   [   # busca e síntese de jurisprudência PT
        "zai:glm-5-turbo",
        "zai:glm-5.1",
        "groq:llama-3.3-70b-versatile",
    ],
    "aggregator":    [   # síntese — modelo mais forte
        "groq:openai/gpt-oss-120b",
        "groq:llama-3.3-70b-versatile",
        "groq:qwen/qwen3-32b",
        "zai:glm-5.1",
    ],
    "adversarial":   [   # ataque crítico — bom em raciocínio
        "groq:llama-3.3-70b-versatile",
        "groq:openai/gpt-oss-120b",
        "zai:glm-5-turbo",
    ],
    "refinador":     [   # refinamento jurídico PT — melhor PT
        "zai:glm-5-turbo",
        "groq:qwen/qwen3-32b",
        "groq:llama-3.3-70b-versatile",
    ],
}


# ── LegalAssembly ─────────────────────────────────────────────────────────────

class LegalAssembly:
    """
    Ensemble jurídico de múltiplos modelos com planner consciente de rate limit.

    Thread-safe. Suporte a TranslationLayer para pipelines EN.
    Cada agente tem timeout de 60s com fallback gracioso.
    """

    _AGENT_TIMEOUT_S = 60
    _MAX_AGENT_OUTPUT = 1200   # chars — reserva contexto para Aggregator

    def __init__(
        self,
        groq_key: str,
        zai_key: str,
        openrouter_key: str = "",
        translation_layer: TranslationLayer | None = None,
        rate_limit_tracker: RateLimitTracker | None = None,
    ) -> None:
        self._groq_key   = groq_key
        self._zai_key    = zai_key
        self._or_key     = openrouter_key
        self._translation = translation_layer
        self._tracker    = rate_limit_tracker or RateLimitTracker()

    # ── API pública ───────────────────────────────────────────────────────────

    async def run(
        self,
        query: str,
        shared_context: dict,
        adversarial_persona: str = "Procurador da Fazenda Nacional",
        roles: list[str] | None = None,
        conv_id: str = "",
    ) -> AssemblyResult:
        """
        Executa o assembly completo.

        Args:
            query:               Consulta jurídica em PT
            shared_context:      Contexto compartilhado (ex: resultados Wave 1 do OXÉ)
            adversarial_persona: Persona do agente adversarial
            roles:               Papéis a executar (None = todos os 3 padrão)
            conv_id:             ID da conversa (para cache de tradução)
        """
        t0 = time.time()
        result = AssemblyResult(query=query)
        active_roles = roles or ["jurimetria", "argumentacao", "precedentes"]

        # Planner: distribui modelos por papel
        role_models = self._plan(active_roles)
        result.models_used = {r: m for r, m in role_models.items()}
        logger.info("legal_assembly: planner → %s", role_models)

        # Contexto compartilhado comprimido (para não exceder context window dos agentes)
        ctx_summary = self._compress_context(shared_context)

        # Execução paralela dos agentes com timeout
        agent_tasks = {
            role: self._run_agent(role, query, ctx_summary, role_models.get(role, ""), conv_id)
            for role in active_roles
        }

        agent_outputs: dict[str, str] = {}
        raw_results = await asyncio.gather(
            *[asyncio.wait_for(task, timeout=self._AGENT_TIMEOUT_S)
              for task in agent_tasks.values()],
            return_exceptions=True,
        )

        for role, output in zip(agent_tasks.keys(), raw_results):
            if isinstance(output, Exception):
                logger.warning("legal_assembly: agente %s falhou: %s", role, output)
                result.erros.append(f"{role}: {output}")
                agent_outputs[role] = ""
            else:
                agent_outputs[role] = output or ""

        result.jurimetria   = agent_outputs.get("jurimetria", "")
        result.argumentacao = agent_outputs.get("argumentacao", "")
        result.precedentes  = agent_outputs.get("precedentes", "")

        # Aggregator — sintetiza os outputs
        aggregator_model = role_models.get("aggregator", "")
        if any(agent_outputs.values()):
            result.sintese, result.quality_score = await self._aggregate(
                query, agent_outputs, aggregator_model, ctx_summary, conv_id,
            )
        else:
            result.erros.append("aggregator: todos os agentes retornaram vazio")

        # Adversarial — ataca a síntese
        adversarial_model = role_models.get("adversarial", "")
        if result.sintese:
            result.adversarial = await self._run_adversarial(
                result.sintese, adversarial_persona, adversarial_model, conv_id,
            )

        # Refinador — incorpora críticas e finaliza em PT jurídico
        refinador_model = role_models.get("refinador", "")
        if result.sintese:
            result.refinado = await self._run_refiner(
                result.sintese,
                result.adversarial,
                refinador_model,
                conv_id,
            )

        result.latency_s = time.time() - t0
        logger.info(
            "legal_assembly: concluído em %.1fs | quality=%.2f | erros=%d",
            result.latency_s, result.quality_score, len(result.erros),
        )
        return result

    # ── Planner ───────────────────────────────────────────────────────────────

    def _plan(self, roles: list[str]) -> dict[str, str]:
        """
        Distribui modelos por papel, consciente de rate limit e provider.
        Garante diversidade de provider quando possível.
        """
        plan: dict[str, str] = {}
        used_by_provider: dict[str, int] = {}   # provider → contagem de uso

        all_roles = roles + ["aggregator", "adversarial", "refinador"]

        for role in all_roles:
            candidates = _ROLE_CANDIDATES.get(role, [])
            selected = None

            # Preferir modelo disponível com menor uso do provider
            for candidate in candidates:
                provider = candidate.split(":")[0]
                model_id = candidate.split(":", 1)[1]

                if not self._is_model_available(candidate):
                    continue

                # Preferir diversidade de provider
                provider_count = used_by_provider.get(provider, 0)
                if selected is None or provider_count < used_by_provider.get(selected.split(":")[0], 999):
                    selected = candidate

            if selected:
                plan[role] = selected
                provider = selected.split(":")[0]
                used_by_provider[provider] = used_by_provider.get(provider, 0) + 1
            else:
                # Fallback: usar primeiro candidato mesmo se pode ter rate limit
                if candidates:
                    plan[role] = candidates[0]
                    logger.warning("legal_assembly: todos os candidatos para %s com 429 recente — usando %s mesmo assim", role, candidates[0])

        return plan

    def _is_model_available(self, provider_model: str) -> bool:
        """Verifica disponibilidade no tracker."""
        return self._tracker.is_available(provider_model)

    # ── Agentes ───────────────────────────────────────────────────────────────

    async def _run_agent(
        self,
        role: str,
        query: str,
        ctx_summary: str,
        model: str,
        conv_id: str,
    ) -> str:
        """Executa um agente especializado."""
        prompts = {
            "jurimetria": (
                f"You are a Brazilian tax law analyst. Analyze the following legal question "
                f"and provide: (1) probability of success based on precedents (%), "
                f"(2) key jurisprudential trends, (3) risk factors. Be concise (max 800 chars).\n\n"
                f"Question: {query}\n\nContext:\n{ctx_summary}"
            ),
            "argumentacao": (
                f"You are a Brazilian litigation strategist. For the following legal question, "
                f"provide: (1) strongest arguments in favor, (2) rhetorical approach, "
                f"(3) how to present to the court. Concise (max 800 chars).\n\n"
                f"Question: {query}\n\nContext:\n{ctx_summary}"
            ),
            "precedentes": (
                f"Você é especialista em jurisprudência brasileira. Para a seguinte questão jurídica, "
                f"identifique: (1) súmulas e teses vinculantes aplicáveis, (2) leading cases do STF/STJ, "
                f"(3) posição atual dos tribunais. Máximo 800 caracteres.\n\n"
                f"Questão: {query}\n\nContexto:\n{ctx_summary}"
            ),
        }

        prompt = prompts.get(role, f"Analise juridicamente: {query}\n\nContexto: {ctx_summary}")

        # Jurimetria e argumentação: usar TranslationLayer se disponível
        use_translation = role in ("jurimetria", "argumentacao") and self._translation is not None
        if use_translation:
            result_en = await asyncio.to_thread(
                self._call_model, model, prompt, conv_id=conv_id
            )
            if result_en:
                result_pt = await asyncio.to_thread(
                    self._translation.translate_en_pt, result_en, conv_id
                )
                return result_pt[:self._MAX_AGENT_OUTPUT]
        else:
            result = await asyncio.to_thread(
                self._call_model, model, prompt, conv_id=conv_id
            )
            return (result or "")[:self._MAX_AGENT_OUTPUT]

        return ""

    async def _aggregate(
        self,
        query: str,
        agent_outputs: dict[str, str],
        model: str,
        ctx_summary: str,
        conv_id: str,
    ) -> tuple[str, float]:
        """Aggregator: sintetiza outputs dos agentes em análise coesa."""
        parts = []
        if agent_outputs.get("jurimetria"):
            parts.append(f"ANÁLISE QUANTITATIVA:\n{agent_outputs['jurimetria']}")
        if agent_outputs.get("argumentacao"):
            parts.append(f"ESTRATÉGIA PROCESSUAL:\n{agent_outputs['argumentacao']}")
        if agent_outputs.get("precedentes"):
            parts.append(f"JURISPRUDÊNCIA APLICÁVEL:\n{agent_outputs['precedentes']}")

        synthesis_input = "\n\n".join(parts)

        prompt = (
            f"Você é o sintetizador jurídico de um sistema multi-agente. "
            f"Integre as análises abaixo em uma síntese coesa e profissional para a questão:\n"
            f"'{query}'\n\n"
            f"{synthesis_input}\n\n"
            f"Ao final, atribua uma pontuação de qualidade (0.0 a 1.0) indicando: "
            f"coerência interna, citações jurídicas presentes, e completude. "
            f"Formato: [...síntese...]\n\nQUALIDADE: X.X"
        )

        raw = await asyncio.to_thread(self._call_model, model, prompt, conv_id=conv_id)
        if not raw:
            return "", 0.0

        # Extrair quality score
        import re
        quality = 0.6   # default se não encontrar
        m = re.search(r"QUALIDADE:\s*([0-9]\.[0-9])", raw)
        if m:
            try:
                quality = float(m.group(1))
                raw = raw[:m.start()].strip()
            except ValueError:
                pass

        return raw, quality

    async def _run_adversarial(
        self,
        sintese: str,
        persona: str,
        model: str,
        conv_id: str,
    ) -> str:
        """Adversarial: ataca a síntese com persona configurável."""
        prompt = (
            f"Você é {persona}. Sua função é identificar todas as fraquezas, "
            f"inconsistências e pontos vulneráveis na análise jurídica abaixo. "
            f"Seja cirúrgico e técnico — aponte argumentos que a parte contrária usaria. "
            f"Máximo 600 caracteres.\n\n"
            f"ANÁLISE A ATACAR:\n{sintese[:1500]}"
        )
        result = await asyncio.to_thread(self._call_model, model, prompt, conv_id=conv_id)
        return (result or "")[:800]

    async def _run_refiner(
        self,
        sintese: str,
        adversarial: str,
        model: str,
        conv_id: str,
    ) -> str:
        """Refinador: incorpora críticas adversariais e fortalece a síntese."""
        if not adversarial:
            return sintese

        prompt = (
            f"Você é um advogado tributarista sênior. Dado a análise jurídica e as críticas "
            f"adversariais abaixo, produza uma versão aprimorada que: "
            f"(1) incorpore as críticas válidas, (2) fortaleça os pontos atacados, "
            f"(3) mantenha a tese principal se juridicamente sólida.\n\n"
            f"ANÁLISE ORIGINAL:\n{sintese[:1500]}\n\n"
            f"CRÍTICAS ADVERSARIAIS:\n{adversarial[:600]}\n\n"
            f"Produza a análise refinada e fortalecida:"
        )
        result = await asyncio.to_thread(self._call_model, model, prompt, conv_id=conv_id)
        return result or sintese   # fallback para síntese original se falhar

    # ── Chamador de modelo ────────────────────────────────────────────────────

    def _call_model(self, provider_model: str, prompt: str, conv_id: str = "") -> str:
        """Chama o modelo especificado no formato 'provider:model_id'."""
        if not provider_model:
            return ""

        try:
            provider, model_id = provider_model.split(":", 1)
        except ValueError:
            provider, model_id = "groq", provider_model

        try:
            if provider == "groq":
                return self._call_groq(model_id, prompt)
            elif provider == "zai":
                return self._call_zai(model_id, prompt)
            elif provider == "openrouter":
                return self._call_openrouter(model_id, prompt)
            else:
                logger.warning("legal_assembly: provider desconhecido: %s", provider)
                return ""
        except Exception as exc:
            if "429" in str(exc):
                self._tracker.record_429(provider_model)
                logger.warning("legal_assembly: 429 em %s — registrado no tracker", provider_model)
            else:
                logger.warning("legal_assembly: %s falhou: %s", provider_model, exc)
            return ""

    def _call_groq(self, model_id: str, prompt: str) -> str:
        import requests
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {self._groq_key}", "Content-Type": "application/json"},
            json={
                "model": model_id,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 1200,
                "temperature": 0.3,
            },
            timeout=30,
        )
        if r.status_code == 429:
            raise RuntimeError("429")
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"]
        # Strip thinking tags (Qwen3)
        import re
        content = re.sub(r"<think>[\s\S]*?</think>", "", content).strip()
        return content

    def _call_zai(self, model_id: str, prompt: str) -> str:
        import requests
        # glm-5-turbo e glm-5.1 têm reasoning interno que consome tokens
        # antes do output — usar max_tokens alto para garantir output real
        is_reasoning = model_id in ("glm-5-turbo", "glm-5.1")
        max_tok = 3000 if is_reasoning else 1200
        r = requests.post(
            "https://api.z.ai/api/paas/v4/chat/completions",
            headers={"Authorization": f"Bearer {self._zai_key}", "Content-Type": "application/json"},
            json={
                "model": model_id,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tok,
                "temperature": 0.3,
            },
            timeout=90,
        )
        if r.status_code == 429:
            raise RuntimeError("429")
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"]
        # Se ainda vazio (reasoning esgotou budget), logar para diagnóstico
        if not content:
            reasoning = r.json()["choices"][0]["message"].get("reasoning_content", "")
            import logging
            logging.getLogger(__name__).warning(
                "legal_assembly: zai/%s retornou content vazio (reasoning=%d chars) — "
                "considere aumentar max_tokens ou usar glm-5 (sem reasoning)",
                model_id, len(reasoning),
            )
        return content

    def _call_openrouter(self, model_id: str, prompt: str) -> str:
        import requests
        r = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {self._or_key}", "Content-Type": "application/json"},
            json={
                "model": model_id,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 1200,
                "temperature": 0.3,
            },
            timeout=45,
        )
        if r.status_code == 429:
            raise RuntimeError("429")
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]

    # ── Utilitários ───────────────────────────────────────────────────────────

    @staticmethod
    def _compress_context(ctx: dict, max_chars: int = 2000) -> str:
        """Comprime contexto compartilhado para caber no prompt dos agentes."""
        parts = []
        for key, value in ctx.items():
            if isinstance(value, list):
                # Lista de dicts (ex: resultados Qdrant)
                items = []
                for item in value[:5]:   # max 5 itens
                    if isinstance(item, dict):
                        ementa = item.get("ementa", item.get("content", str(item)))
                        items.append(ementa[:200])
                    else:
                        items.append(str(item)[:200])
                parts.append(f"{key}:\n" + "\n".join(f"  - {i}" for i in items))
            elif isinstance(value, str):
                parts.append(f"{key}: {value[:300]}")

        full = "\n\n".join(parts)
        return full[:max_chars] + ("..." if len(full) > max_chars else "")
