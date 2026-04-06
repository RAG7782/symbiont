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
    parser.add_argument(
        "--port", "-p",
        type=int,
        default=7777,
        help="Porta do HTTP bridge (default: 7777)",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host do HTTP bridge (default: 0.0.0.0)",
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
    elif task_text.lower() == "tools":
        # Show available tools
        try:
            from symbiont.tools import ToolRegistry
            tools = ToolRegistry()
            s = tools.summary()
            print("🔧 Tools disponíveis:")
            if s["harnesses"]:
                print(f"   CLI Harnesses: {', '.join(s['harnesses'])}")
            print(f"   System tools: {', '.join(s['system_tools'])}")
            print(f"   Total: {s['total']}")
        except Exception as e:
            print(f"Error: {e}")
    elif task_text.lower().startswith("stress"):
        parts = task_text.split(maxsplit=1)
        stress_args = parts[1] if len(parts) > 1 else ""
        from symbiont.stress import stress_cmd
        asyncio.run(stress_cmd(stress_args, verbose=args.verbose))
    elif task_text.lower().startswith("audit"):
        parts = task_text.split(maxsplit=1)
        audit_args = parts[1] if len(parts) > 1 else ""
        from symbiont.audit import audit_cmd
        asyncio.run(audit_cmd(audit_args, verbose=args.verbose))
    elif task_text.lower() == "serve":
        # Start the HTTP bridge
        from symbiont.serve import serve as start_serve
        asyncio.run(start_serve(
            host=args.host,
            port=args.port,
            backend_name=args.backend,
            light=args.light,
            verbose=args.verbose,
        ))
    elif task_text.lower().startswith("squad"):
        parts = task_text.split(maxsplit=2)
        subcmd = parts[1] if len(parts) > 1 else "list"
        rest = parts[2] if len(parts) > 2 else ""
        from symbiont.persistence import PersistenceStore
        from symbiont.squads import SquadManager
        store = PersistenceStore()
        mgr = SquadManager(store=store)

        if subcmd == "list":
            squads = mgr.list_squads()
            print("🎯 Squads")
            print("=" * 60)
            if not squads:
                print("  No squads. Create one: sym squad create <name> <description>")
            for name, info in squads.items():
                print(f"  {name:15s} [{info['size']} agents] {info['description']}")
        elif subcmd == "create":
            cparts = rest.split(maxsplit=1)
            name = cparts[0] if cparts else ""
            desc = cparts[1] if len(cparts) > 1 else ""
            if not name:
                print("Usage: sym squad create <name> <description>")
            else:
                mgr.create(name, description=desc)
                print(f"✅ Squad '{name}' created")
        elif subcmd == "delete":
            if mgr.delete(rest.strip()):
                print(f"✅ Squad '{rest.strip()}' deleted")
            else:
                print(f"Squad '{rest.strip()}' not found")
        elif subcmd == "auto":
            logging.basicConfig(level=logging.WARNING)
            from symbiont import Symbiont
            org = Symbiont()
            org.set_llm_backend(make_backend(args.backend))
            asyncio.run(org.boot())
            assignments = mgr.auto_assign(org)
            asyncio.run(org.shutdown())
            for sq, agents in assignments.items():
                print(f"  {sq}: {len(agents)} agents")
            print(f"✅ Auto-assigned {sum(len(a) for a in assignments.values())} agents to {len(assignments)} squads")
        else:
            print(f"Unknown: sym squad [list|create|delete|auto]")
        store.close()
    elif task_text.lower().startswith("federation"):
        parts = task_text.split(maxsplit=2)
        subcmd = parts[1] if len(parts) > 1 else "status"
        from symbiont.persistence import PersistenceStore
        from symbiont.federation import Federation
        store = PersistenceStore()
        fed = Federation(store=store)
        if subcmd == "status":
            s = fed.summary()
            print(f"🌐 Federation: {s['organism_id']}")
            print(f"   Bridge: {s['bridge_url']}")
            print(f"   Peers: {s['alive_peers']}/{s['total_peers']} alive")
            for pid, p in s["peers"].items():
                icon = "🟢" if p["alive"] else "🔴"
                print(f"   {icon} {pid:15s} {p['url']}")
        elif subcmd == "add":
            rest = parts[2] if len(parts) > 2 else ""
            rparts = rest.split()
            if len(rparts) < 2:
                print("Usage: sym federation add <id> <url>")
            else:
                fed.register_peer(rparts[0], rparts[1])
                print(f"✅ Registered peer {rparts[0]} at {rparts[1]}")
        else:
            print("Unknown: sym federation [status|add]")
        store.close()
    elif task_text.lower().startswith("colony"):
        # Remote colony management
        parts = task_text.split(maxsplit=1)
        colony_args = parts[1] if len(parts) > 1 else ""
        from symbiont.colony import colony_cmd
        asyncio.run(colony_cmd(colony_args, args.backend, args.verbose))
    elif task_text.lower().startswith("finetune"):
        # Fine-tune pipeline with preset support
        parts = task_text.split()
        subcmd = parts[1] if len(parts) > 1 else "list"

        if subcmd == "list":
            from symbiont.datasets import list_presets
            print("🔧 Fine-tune Presets")
            print("=" * 60)
            for name, info in list_presets().items():
                print(f"  {name:20s} {info['description']}")
                print(f"  {'':20s} base: {info['base_model']}")
                print(f"  {'':20s} examples: {info['examples']} | output: {info['output_name']}")
                print()
            from symbiont.finetune import FineTunePipeline
            pipe = FineTunePipeline()
            print(f"  Modal: {'available' if pipe.available else 'not installed (pip install modal)'}")
            print(f"\n  Commands:")
            print(f"    sym finetune list              — show presets")
            print(f"    sym finetune prepare <preset>   — generate dataset")
            print(f"    sym finetune run <preset>       — full pipeline (Modal GPU)")
            print(f"    sym finetune validate <path>    — validate JSONL dataset")

        elif subcmd == "prepare":
            from symbiont.datasets import generate_dataset, PRESETS
            preset = parts[2] if len(parts) > 2 else ""
            if preset not in PRESETS:
                print(f"Unknown preset: {preset}. Available: {list(PRESETS.keys())}")
                sys.exit(1)
            output = f"data/{preset}-train.jsonl"
            result = generate_dataset(preset, output)
            print(f"📦 Dataset prepared: {result['examples']} examples → {output}")
            print(f"   Base model: {result['base_model']}")
            print(f"   Output model: {result['output_name']}")

        elif subcmd == "validate":
            from symbiont.datasets import validate_dataset
            path = parts[2] if len(parts) > 2 else ""
            if not path:
                print("Usage: sym finetune validate <path.jsonl>")
                sys.exit(1)
            result = validate_dataset(path)
            if result["valid"]:
                print(f"✅ Valid: {result['examples']} examples in {path}")
            else:
                print(f"❌ Invalid: {result['errors']}")

        elif subcmd == "run":
            from symbiont.datasets import PRESETS, generate_dataset
            from symbiont.finetune import FineTunePipeline
            preset_name = parts[2] if len(parts) > 2 else ""
            if preset_name not in PRESETS:
                print(f"Unknown preset: {preset_name}. Available: {list(PRESETS.keys())}")
                sys.exit(1)
            pipe = FineTunePipeline()
            if not pipe.available:
                print("Modal not installed. Run: pip install modal")
                sys.exit(1)
            preset = PRESETS[preset_name]
            # Prepare dataset
            data_path = f"data/{preset_name}-train.jsonl"
            gen = generate_dataset(preset_name, data_path)
            print(f"📦 Dataset: {gen['examples']} examples → {data_path}")
            # Run pipeline
            print(f"🔧 Starting fine-tune: {preset['base_model']} → {preset['output_name']}")
            print(f"   GPU: {preset['gpu']} | Epochs: {preset['epochs']} | LoRA r={preset['lora_r']}")
            result = asyncio.run(pipe.run(
                base_model=preset["base_model"],
                dataset_path=data_path,
                output_name=preset["output_name"],
                gpu=preset["gpu"],
                epochs=preset["epochs"],
                lora_r=preset["lora_r"],
                max_seq_length=preset["max_seq_length"],
            ))
            print(f"\n📊 Result: {json.dumps(result, indent=2)}")

        else:
            # Legacy: sym finetune <base_model> <name>
            from symbiont.finetune import FineTunePipeline
            pipe = FineTunePipeline()
            print(f"🔧 Fine-tune: {subcmd}")
            print(f"   Use 'sym finetune list' for presets")
            print(f"   Use 'sym finetune run <preset>' for full pipeline")
    else:
        images = args.image if args.image else None
        asyncio.run(run_task(task_text, args.backend, context, args.verbose, args.light, images))


if __name__ == "__main__":
    main()
