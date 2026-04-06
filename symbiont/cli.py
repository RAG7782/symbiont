#!/usr/bin/env python3
"""
SYMBIONT CLI — interface simples para o organismo.

Uso:
    sym "Implemente autenticação JWT em FastAPI"
    sym "Analise os riscos de migrar o banco para Postgres 17"
    sym status
    sym --backend ollama "Faça um code review deste módulo"
    sym --backend echo "Teste rápido sem LLM"
"""

import asyncio
import argparse
import json
import logging
import sys


def pretty(data: dict) -> str:
    def default(obj):
        if isinstance(obj, set):
            return list(obj)
        if hasattr(obj, "name"):
            return obj.name
        return str(obj)

    def convert_keys(obj):
        if isinstance(obj, dict):
            return {
                (k.name if hasattr(k, "name") else str(k)): convert_keys(v)
                for k, v in obj.items()
            }
        if isinstance(obj, list):
            return [convert_keys(i) for i in obj]
        return obj

    return json.dumps(convert_keys(data), indent=2, default=default, ensure_ascii=False)


def make_backend(name: str, light: bool = False):
    from symbiont.backends import EchoBackend, OllamaBackend

    if name == "ollama":
        return OllamaBackend(light=light)
    elif name == "cloud":
        from symbiont.backends import OpenRouterBackend
        return OpenRouterBackend()
    elif name == "modal":
        from symbiont.modal_backend import ModalBackend
        return ModalBackend()
    elif name == "anthropic":
        from symbiont.backends import AnthropicBackend
        return AnthropicBackend()
    else:
        return EchoBackend()


async def run_task(task: str, backend_name: str, context: dict, verbose: bool, light: bool = False, images: list | None = None):
    from symbiont import Symbiont

    if verbose:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(name)-20s] %(message)s",
            datefmt="%H:%M:%S",
        )
    else:
        logging.basicConfig(level=logging.WARNING)

    organism = Symbiont()
    organism.set_llm_backend(make_backend(backend_name, light=light))

    mode = "light" if light else "full"
    print(f"🧬 SYMBIONT booting ({backend_name}/{mode})...")

    # Show IMI status
    backend_obj = organism._llm_backend
    if hasattr(backend_obj, '_memory') and backend_obj._memory:
        stats = backend_obj._memory.stats()
        print(f"   🧠 IMI memory: {stats.get('memories', 0)} memories loaded")
    await organism.boot()
    print(f"   {organism.agent_count} agents online\n")

    if images:
        print(f"📋 Task: {task} (+ {len(images)} image(s))\n")
    else:
        print(f"📋 Task: {task}\n")
    result = await organism.execute(task=task, context=context, images=images)

    # Extrair o que importa
    approach = result.get("approach", "")
    execution = result.get("execution", {})
    waggle = result.get("waggle_session", {})

    print("=" * 60)
    print("📊 RESULTADO")
    print("=" * 60)

    if waggle.get("decided"):
        print(f"🐝 Decisão coletiva: {waggle.get('decision', 'N/A')}")
        print(f"   Scouts consultados: {waggle.get('reports_count', 0)}")
    else:
        print(f"🎯 Abordagem: {approach}")

    if execution:
        artifact_id = execution.get("artifact_id", "")
        content = execution.get("content", "")
        if artifact_id:
            print(f"📦 Artefato: {artifact_id}")
        if content:
            print(f"\n{content}")

    phases = result.get("phase_history", [])
    if phases:
        phase_names = " → ".join(p[0] for p in phases)
        print(f"\n🔄 Fases: {phase_names}")

    print("=" * 60)

    await organism.shutdown()
    print("🧬 SYMBIONT shutdown.\n")


async def show_status(backend_name: str):
    from symbiont import Symbiont

    logging.basicConfig(level=logging.WARNING)

    organism = Symbiont()
    organism.set_llm_backend(make_backend(backend_name))
    await organism.boot()

    status = organism.status()
    print("🧬 SYMBIONT Status")
    print("=" * 60)
    print(pretty(status))

    await organism.shutdown()


def main():
    parser = argparse.ArgumentParser(
        prog="sym",
        description="SYMBIONT — organismo multi-agente bio-inspirado",
    )
    parser.add_argument(
        "task",
        nargs="*",
        help="Tarefa para o organismo executar (ou 'status')",
    )
    parser.add_argument(
        "--backend", "-b",
        choices=["ollama", "cloud", "modal", "anthropic", "echo"],
        default="ollama",
        help="Backend LLM (default: ollama)",
    )
    parser.add_argument(
        "--context", "-c",
        type=str,
        default="{}",
        help='Contexto JSON, ex: \'{"lang":"python"}\'',
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Mostrar logs do organismo",
    )
    parser.add_argument(
        "--light", "-l",
        action="store_true",
        help="Modo light: usa só qwen3:8b para todos os agentes (economiza RAM)",
    )
    parser.add_argument(
        "--image", "-i",
        action="append",
        default=[],
        help="Caminho de imagem para análise multimodal (pode repetir: -i img1.png -i img2.jpg)",
    )

    args = parser.parse_args()

    if not args.task:
        parser.print_help()
        sys.exit(0)

    task_text = " ".join(args.task)

    try:
        context = json.loads(args.context)
    except json.JSONDecodeError:
        context = {}

    if task_text.lower() == "status":
        asyncio.run(show_status(args.backend))
    elif task_text.lower() == "dream":
        # Run IMI consolidation
        try:
            from symbiont.memory import IMIMemory
            mem = IMIMemory()
            if mem.available:
                print(f"🧠 IMI: {mem.memory_count} memories. Running dream cycle...")
                result = mem.dream()
                print(f"   Done. {result}")
            else:
                print("🧠 IMI not available.")
        except Exception as e:
            print(f"Error: {e}")
    elif task_text.lower() == "memories":
        # Show IMI stats
        try:
            from symbiont.memory import IMIMemory
            mem = IMIMemory()
            print(f"🧠 IMI Memory Stats: {json.dumps(mem.stats(), indent=2)}")
        except Exception as e:
            print(f"Error: {e}")
    elif task_text.lower() == "listen":
        # Voice mode: record → transcribe → execute
        try:
            from symbiont.voice import Voice
            voice = Voice()
            if not voice.capabilities["stt"]:
                print("Whisper not installed. Run: pip install openai-whisper")
                sys.exit(1)
            print("🎤 Fale agora (5s)...")
            text = voice.listen()
            print(f"📝 Você disse: {text}\n")
            if text:
                asyncio.run(run_task(text, args.backend, context, args.verbose, args.light))
        except Exception as e:
            print(f"Error: {e}")
    elif task_text.lower() == "voice":
        # Show voice capabilities
        try:
            from symbiont.voice import Voice
            print(f"🎤 Voice: {json.dumps(Voice().capabilities, indent=2)}")
        except Exception as e:
            print(f"Error: {e}")
    elif task_text.lower() == "gpu":
        # Show GPU providers status
        try:
            from symbiont.gpu_router import GPURouter
            router = GPURouter()
            status = router.status()
            print("🖥️  GPU Providers:")
            for name, info in status["providers"].items():
                print(f"   [{name}] {info['name']} — {info['free_tier']} — {info['style']}")
            print(f"\n   Recommended: {status['recommended']}")
        except Exception as e:
            print(f"Error: {e}")
    elif task_text.lower().startswith("finetune"):
        # Fine-tune pipeline
        try:
            from symbiont.finetune import FineTunePipeline
            pipe = FineTunePipeline()
            if not pipe.available:
                print("Modal not installed. Run: pip install modal")
                sys.exit(1)
            parts = task_text.split()
            base = parts[1] if len(parts) > 1 else "unsloth/Qwen2.5-7B-bnb-4bit"
            name = parts[2] if len(parts) > 2 else "symbiont-custom"
            print(f"🔧 Fine-tune Pipeline: {base} → {name}")
            print(f"   GPU: L4 | Epochs: 1 | LoRA r=16")
            print(f"   Available base models:")
            for m in pipe.list_base_models():
                print(f"     - {m}")
            print(f"\n   To run: sym finetune {base} {name}")
            print(f"   (Full pipeline: Unsloth → Modal GPU → GGUF → Ollama)")
        except Exception as e:
            print(f"Error: {e}")
    else:
        images = args.image if args.image else None
        asyncio.run(run_task(task_text, args.backend, context, args.verbose, args.light, images))


if __name__ == "__main__":
    main()
