"""
SYMBIONT Dataset Generators — create fine-tune datasets for domain specialization.

Generates instruction/response pairs in JSONL format compatible with
Unsloth/Alpaca training format.

Domains:
- legal-br: Brazilian law (tributário, trabalhista, civil, empresarial, digital)
- coding-python: Python development patterns
- general-assistant: General helpful assistant

Usage:
    from symbiont.datasets import generate_dataset
    generate_dataset("legal-br", "data/legal-train.jsonl", count=500)
"""

from __future__ import annotations

import json
import logging
import random
from pathlib import Path

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Legal-BR Dataset Templates
# ---------------------------------------------------------------------------

_LEGAL_TRIBUTARIO = [
    {
        "instruction": "Qual o prazo prescricional para cobrança de crédito tributário?",
        "output": "O prazo prescricional para cobrança de crédito tributário é de 5 anos, contados da data da constituição definitiva do crédito, conforme art. 174 do CTN. A prescrição se interrompe por: despacho do juiz que ordenar a citação (LC 118/2005), protesto judicial, qualquer ato judicial que constitua em mora o devedor, ou qualquer ato inequívoco que importe em reconhecimento do débito pelo devedor.",
    },
    {
        "instruction": "Como funciona a substituição tributária do ICMS?",
        "output": "A substituição tributária (ST) do ICMS concentra a responsabilidade pelo recolhimento do imposto em um único contribuinte da cadeia produtiva (substituto), que recolhe antecipadamente o ICMS de toda a cadeia até o consumidor final. Fundamentação: art. 150, §7° da CF/88 e LC 87/96, art. 6°. Existe ST para frente (antecipação) e para trás (diferimento). A base de cálculo da ST usa MVA (Margem de Valor Agregado) ou preço sugerido. O contribuinte tem direito à restituição se o fato gerador presumido não se realizar (RE 593.849/MG).",
    },
    {
        "instruction": "Explique a diferença entre imunidade e isenção tributária.",
        "output": "Imunidade é limitação constitucional ao poder de tributar (art. 150, VI, CF/88) — o ente federativo não pode sequer instituir o tributo sobre aquela situação. É permanente e só pode ser alterada por emenda constitucional. Exemplos: imunidade recíproca, templos, partidos, livros.\n\nIsenção é dispensa legal do pagamento do tributo já instituído (art. 175, I, CTN). É concedida por lei ordinária ou complementar, pode ser revogada, e pode ter prazo e condições. A isenção onerosa e com prazo não pode ser livremente revogada (art. 178, CTN).",
    },
    {
        "instruction": "Quais são os princípios constitucionais tributários?",
        "output": "Os princípios constitucionais tributários são:\n\n1. **Legalidade** (art. 150, I): tributo só por lei\n2. **Anterioridade** (art. 150, III, b): publicação no exercício anterior\n3. **Anterioridade nonagesimal** (art. 150, III, c): 90 dias da publicação\n4. **Irretroatividade** (art. 150, III, a): não retroage\n5. **Isonomia** (art. 150, II): tratamento igual aos iguais\n6. **Capacidade contributiva** (art. 145, §1°): quem pode mais, paga mais\n7. **Vedação ao confisco** (art. 150, IV): tributo não pode ser confiscatório\n8. **Liberdade de tráfego** (art. 150, V): não limitar circulação\n9. **Uniformidade geográfica** (art. 151, I): tributo federal uniforme\n10. **Não-cumulatividade** (art. 153, §3°, II): ICMS e IPI",
    },
    {
        "instruction": "Uma empresa do Simples Nacional pode emitir nota fiscal de exportação?",
        "output": "Sim. Empresas optantes pelo Simples Nacional podem realizar exportação e emitir nota fiscal correspondente. A receita de exportação é segregada e tem tratamento diferenciado:\n\n1. **ICMS**: imune na exportação (art. 155, §2°, X, 'a', CF/88)\n2. **PIS/COFINS**: alíquota zero na exportação\n3. **ISS**: não incide em serviços para o exterior (LC 116/2003)\n4. A receita de exportação compõe o faturamento do Simples para fins de faixa, mas as alíquotas dos tributos federais são reduzidas\n\nA empresa deve observar os procedimentos de despacho aduaneiro e classificação NCM/SH da mercadoria.",
    },
    {
        "instruction": "Qual a base de cálculo do ITBI na transmissão de imóvel?",
        "output": "A base de cálculo do ITBI é o valor venal do imóvel no momento da transmissão (art. 38, CTN). Pontos importantes:\n\n1. O STJ fixou que o valor venal para ITBI não precisa coincidir com o valor venal do IPTU (Tema Repetitivo 1113)\n2. O município não pode arbitrar base de cálculo prévia — deve considerar o valor da transação declarado\n3. Se o valor declarado for inferior ao de mercado, o município pode instaurar processo administrativo de arbitramento (art. 148, CTN)\n4. Na arrematação judicial, a base é o preço alcançado (Súmula 108, STF)\n5. Na integralização de capital, há controvérsia sobre a incidência (art. 156, §2°, I, CF)",
    },
]

_LEGAL_TRABALHISTA = [
    {
        "instruction": "Quais são os requisitos para configuração de vínculo empregatício?",
        "output": "Os requisitos para configuração de vínculo empregatício estão no art. 3° da CLT:\n\n1. **Pessoalidade**: o serviço é prestado pessoalmente, sem substituição\n2. **Habitualidade/Não-eventualidade**: prestação contínua, não esporádica\n3. **Subordinação**: o trabalhador segue ordens do empregador (subordinação jurídica)\n4. **Onerosidade**: há contraprestação pecuniária pelo trabalho\n\nPresentes esses 4 elementos, o vínculo é reconhecido independentemente da denominação do contrato (princípio da primazia da realidade, art. 9° da CLT). A reforma trabalhista (Lei 13.467/2017) não alterou esses requisitos, mas criou novas modalidades como trabalho intermitente.",
    },
    {
        "instruction": "Como calcular a rescisão de contrato por demissão sem justa causa?",
        "output": "Na demissão sem justa causa, o empregado tem direito a:\n\n1. **Saldo de salário**: dias trabalhados no mês\n2. **Aviso prévio**: 30 dias + 3 dias por ano trabalhado (máx 90 dias) — trabalhado ou indenizado\n3. **13° salário proporcional**: meses trabalhados / 12\n4. **Férias vencidas + 1/3**: se houver período aquisitivo completo\n5. **Férias proporcionais + 1/3**: meses do período em curso / 12\n6. **Multa de 40% do FGTS**: sobre total depositado + correção\n7. **Saque do FGTS**: liberação do saldo\n8. **Guias para seguro-desemprego**: se preencher requisitos\n\nPrazo para pagamento: até 10 dias da notificação da demissão (art. 477, §6°, CLT).",
    },
    {
        "instruction": "O que mudou com a reforma trabalhista sobre horas extras?",
        "output": "A reforma trabalhista (Lei 13.467/2017) trouxe mudanças significativas:\n\n1. **Banco de horas**: pode ser por acordo individual (compensação em 6 meses) ou acordo coletivo (1 ano) — art. 59, §5° e §2°\n2. **Jornada 12x36**: pode ser por acordo individual escrito — art. 59-A\n3. **Tempo de deslocamento**: não é mais computado na jornada — art. 58, §2° (eliminação das horas in itinere)\n4. **Teletrabalho**: não sujeito a controle de jornada, sem direito a horas extras — art. 62, III\n5. **Intervalo intrajornada**: pode ser reduzido para 30 min por acordo coletivo — art. 611-A, III\n6. **Supressão parcial do intervalo**: gera indenização apenas do período suprimido, não a hora integral — art. 71, §4°",
    },
]

_LEGAL_CIVIL = [
    {
        "instruction": "Qual o prazo prescricional para ação de reparação civil?",
        "output": "O prazo prescricional para pretensão de reparação civil é de 3 anos, conforme art. 206, §3°, V do Código Civil. Exceções importantes:\n\n1. **Relações de consumo**: 5 anos (art. 27, CDC) para fato do produto/serviço\n2. **Fazenda Pública**: 5 anos (Decreto 20.910/32)\n3. **Seguro**: 1 ano para segurado, 3 anos para terceiro (art. 206, §1°, II)\n4. **Acidente de trabalho**: 5 anos, limitado a 2 anos após extinção do contrato (art. 7°, XXIX, CF)\n5. **Imprescritíveis**: dano ambiental (jurisprudência STJ) e danos decorrentes de tortura/trabalho escravo\n\nO termo inicial é a data do conhecimento do dano e autoria (teoria da actio nata).",
    },
    {
        "instruction": "Explique a responsabilidade civil objetiva e subjetiva.",
        "output": "**Responsabilidade subjetiva** (regra geral, art. 186 CC): exige prova de culpa (negligência, imprudência ou imperícia). Elementos: conduta, dano, nexo causal e culpa.\n\n**Responsabilidade objetiva** (art. 927, parágrafo único CC): independe de culpa. Basta conduta, dano e nexo causal. Aplica-se quando:\n\n1. A lei expressamente determina (CDC, art. 12/14 — fornecedor; CC, art. 931 — produtos)\n2. A atividade normalmente desenvolvida implica risco (teoria do risco da atividade)\n3. Dano ambiental (art. 14, §1°, Lei 6.938/81)\n4. Estado (art. 37, §6°, CF — responsabilidade objetiva da Administração)\n\nExclui-se nas duas: caso fortuito, força maior, culpa exclusiva da vítima e fato de terceiro.",
    },
]

_LEGAL_ALL = _LEGAL_TRIBUTARIO + _LEGAL_TRABALHISTA + _LEGAL_CIVIL

# ---------------------------------------------------------------------------
# Coding-Python Dataset Templates
# ---------------------------------------------------------------------------

_CODING_PYTHON = [
    {
        "instruction": "Write an async function that retries a failed HTTP request up to 3 times with exponential backoff.",
        "output": """```python
import asyncio
import aiohttp

async def fetch_with_retry(url: str, max_retries: int = 3) -> str:
    for attempt in range(max_retries + 1):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    resp.raise_for_status()
                    return await resp.text()
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            if attempt == max_retries:
                raise
            wait = 2 ** attempt  # 1s, 2s, 4s
            await asyncio.sleep(wait)
```""",
    },
    {
        "instruction": "Implement a thread-safe LRU cache in Python without external libraries.",
        "output": """```python
import threading
from collections import OrderedDict

class LRUCache:
    def __init__(self, capacity: int):
        self._cache: OrderedDict = OrderedDict()
        self._capacity = capacity
        self._lock = threading.Lock()

    def get(self, key):
        with self._lock:
            if key not in self._cache:
                return None
            self._cache.move_to_end(key)
            return self._cache[key]

    def put(self, key, value):
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            self._cache[key] = value
            if len(self._cache) > self._capacity:
                self._cache.popitem(last=False)

    def __len__(self):
        return len(self._cache)
```""",
    },
    {
        "instruction": "Create a Python decorator that measures function execution time and logs it.",
        "output": """```python
import functools
import logging
import time

logger = logging.getLogger(__name__)

def timed(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        try:
            return func(*args, **kwargs)
        finally:
            elapsed = time.perf_counter() - start
            logger.info("%s took %.3fs", func.__qualname__, elapsed)
    return wrapper

# Async version
def atimed(func):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        start = time.perf_counter()
        try:
            return await func(*args, **kwargs)
        finally:
            elapsed = time.perf_counter() - start
            logger.info("%s took %.3fs", func.__qualname__, elapsed)
    return wrapper
```""",
    },
    {
        "instruction": "Write a pub/sub event bus in Python using asyncio.",
        "output": """```python
import asyncio
from collections import defaultdict
from typing import Any, Callable, Coroutine

Handler = Callable[[Any], Coroutine[Any, Any, None]]

class EventBus:
    def __init__(self):
        self._subs: dict[str, list[Handler]] = defaultdict(list)

    def on(self, event: str, handler: Handler) -> None:
        self._subs[event].append(handler)

    def off(self, event: str, handler: Handler) -> None:
        self._subs[event] = [h for h in self._subs[event] if h is not handler]

    async def emit(self, event: str, data: Any = None) -> None:
        tasks = [h(data) for h in self._subs.get(event, [])]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    @property
    def events(self) -> list[str]:
        return [e for e, subs in self._subs.items() if subs]
```""",
    },
    {
        "instruction": "Implement a simple connection pool for database connections in Python.",
        "output": """```python
import asyncio
from contextlib import asynccontextmanager
from typing import Any

class ConnectionPool:
    def __init__(self, factory, max_size: int = 10):
        self._factory = factory
        self._pool: asyncio.Queue = asyncio.Queue(maxsize=max_size)
        self._size = 0
        self._max_size = max_size

    async def _create(self):
        conn = await self._factory()
        self._size += 1
        return conn

    @asynccontextmanager
    async def acquire(self):
        if self._pool.empty() and self._size < self._max_size:
            conn = await self._create()
        else:
            conn = await self._pool.get()
        try:
            yield conn
        finally:
            await self._pool.put(conn)

    async def close_all(self):
        while not self._pool.empty():
            conn = await self._pool.get()
            if hasattr(conn, 'close'):
                await conn.close()
        self._size = 0
```""",
    },
]

# ---------------------------------------------------------------------------
# General Assistant Dataset Templates
# ---------------------------------------------------------------------------

_GENERAL = [
    {
        "instruction": "Resuma os pontos principais de um bom README para um projeto open source.",
        "output": "Um bom README deve conter:\n\n1. **Nome e descrição**: uma frase que explica o que o projeto faz\n2. **Badges**: CI, coverage, versão, licença\n3. **Quickstart**: exemplo mínimo funcional em < 10 linhas\n4. **Instalação**: passo a passo claro\n5. **Uso**: exemplos dos casos de uso mais comuns\n6. **API/Referência**: link para docs detalhados\n7. **Contribuição**: como contribuir, code of conduct\n8. **Licença**: qual licença e link\n\nDicas: use GIFs/screenshots para mostrar o resultado visual. Mantenha o quickstart acima da dobra. Escreva para alguém que nunca viu o projeto.",
    },
    {
        "instruction": "Compare microserviços vs monolito para uma startup early-stage.",
        "output": "Para uma startup early-stage, **monolito é quase sempre a melhor escolha**.\n\n**Monolito — vantagens early-stage:**\n- Deploy simples (1 artefato)\n- Debugging direto (stack trace local)\n- Refactoring fácil (tudo no mesmo codebase)\n- Menos infra (sem service mesh, API gateway, etc)\n- Velocidade de desenvolvimento\n\n**Microserviços — riscos early-stage:**\n- Overhead de infra (Kubernetes, observability, networking)\n- Latência de rede entre serviços\n- Complexidade de deploy (N pipelines, N deploys)\n- Debugging distribuído\n- Time pequeno = gargalo humano\n\n**Regra prática**: comece monolito, extraia serviços quando (1) a equipe cresce > 10 devs, (2) partes do sistema têm requisitos de escala muito diferentes, ou (3) você precisa de deploy independente de componentes.",
    },
]

# ---------------------------------------------------------------------------
# Preset Definitions
# ---------------------------------------------------------------------------

PRESETS = {
    "legal-br": {
        "name": "Legal BR",
        "description": "Brazilian law specialization (tributário, trabalhista, civil)",
        "base_model": "unsloth/Qwen2.5-7B-bnb-4bit",
        "system_prompt": "Você é um assistente jurídico especializado em direito brasileiro. Responda com fundamentação legal precisa, citando artigos de lei, súmulas e jurisprudência quando aplicável. Seja objetivo e técnico.",
        "templates": _LEGAL_ALL,
        "epochs": 2,
        "lora_r": 16,
        "max_seq_length": 4096,
        "gpu": "L4",
        "output_name": "symbiont-legal-br",
    },
    "coding-python": {
        "name": "Coding Python",
        "description": "Python development patterns and best practices",
        "base_model": "unsloth/Qwen2.5-Coder-7B-bnb-4bit",
        "system_prompt": "You are an expert Python developer. Write clean, efficient, well-tested code. Use type hints, follow PEP 8, and prefer stdlib solutions when possible.",
        "templates": _CODING_PYTHON,
        "epochs": 2,
        "lora_r": 16,
        "max_seq_length": 4096,
        "gpu": "L4",
        "output_name": "symbiont-coding-py",
    },
    "general": {
        "name": "General Assistant",
        "description": "Balanced general-purpose assistant",
        "base_model": "unsloth/Qwen2.5-7B-bnb-4bit",
        "system_prompt": "You are a helpful, concise assistant. Give practical answers with clear structure.",
        "templates": _GENERAL,
        "epochs": 1,
        "lora_r": 8,
        "max_seq_length": 2048,
        "gpu": "L4",
        "output_name": "symbiont-general",
    },
}


# ---------------------------------------------------------------------------
# Dataset Generation
# ---------------------------------------------------------------------------

def _augment_template(template: dict, system_prompt: str) -> dict:
    """Convert a template into Alpaca format with system prompt."""
    return {
        "instruction": template["instruction"],
        "input": template.get("input", ""),
        "output": template["output"],
        "system": system_prompt,
    }


def generate_dataset(
    preset_name: str,
    output_path: str,
    count: int | None = None,
    shuffle: bool = True,
) -> dict:
    """
    Generate a fine-tune dataset from a preset.

    Args:
        preset_name: Name of the preset (legal-br, coding-python, general)
        output_path: Path to write JSONL file
        count: Number of examples (None = all templates)
        shuffle: Shuffle the dataset

    Returns:
        dict with stats about the generated dataset
    """
    if preset_name not in PRESETS:
        return {"error": f"Unknown preset: {preset_name}. Available: {list(PRESETS.keys())}"}

    preset = PRESETS[preset_name]
    templates = list(preset["templates"])
    system_prompt = preset["system_prompt"]

    if shuffle:
        random.shuffle(templates)

    if count and count < len(templates):
        templates = templates[:count]

    # Generate JSONL
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    with open(output, "w", encoding="utf-8") as f:
        for template in templates:
            entry = _augment_template(template, system_prompt)
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    stats = {
        "preset": preset_name,
        "examples": len(templates),
        "output_path": str(output),
        "base_model": preset["base_model"],
        "output_name": preset["output_name"],
    }

    logger.info("datasets: generated %d examples for %s → %s", len(templates), preset_name, output_path)
    return stats


def list_presets() -> dict[str, dict]:
    """Return available presets with their descriptions."""
    return {
        name: {
            "name": p["name"],
            "description": p["description"],
            "base_model": p["base_model"],
            "examples": len(p["templates"]),
            "output_name": p["output_name"],
        }
        for name, p in PRESETS.items()
    }


def validate_dataset(path: str) -> dict:
    """Validate a JSONL dataset file."""
    p = Path(path)
    if not p.exists():
        return {"valid": False, "error": "File not found"}

    errors = []
    count = 0
    with open(p, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            try:
                entry = json.loads(line)
                if "instruction" not in entry:
                    errors.append(f"Line {i}: missing 'instruction'")
                if "output" not in entry:
                    errors.append(f"Line {i}: missing 'output'")
                count += 1
            except json.JSONDecodeError as e:
                errors.append(f"Line {i}: invalid JSON — {e}")

    return {
        "valid": len(errors) == 0,
        "examples": count,
        "errors": errors[:10],
        "path": str(p),
    }
