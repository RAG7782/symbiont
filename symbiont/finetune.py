"""
SYMBIONT Fine-Tune Pipeline — Unsloth on Modal → deploy to Ollama.

Full pipeline:
1. Prepare dataset (local, via Unsloth Data Recipes or custom)
2. Upload to Modal Volume
3. Fine-tune with Unsloth + LoRA on Modal GPU
4. Export to GGUF
5. Import into Ollama as custom model

Usage:
    from symbiont.finetune import FineTunePipeline

    pipe = FineTunePipeline()

    # Full pipeline
    result = await pipe.run(
        base_model="unsloth/Qwen2.5-7B-bnb-4bit",
        dataset_path="data/train.jsonl",
        output_name="symbiont-qwen-custom",
        gpu="L4",
    )

    # Check status
    pipe.status()

CLI:
    sym finetune --base unsloth/Qwen2.5-7B-bnb-4bit --data train.jsonl --name my-model
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class FineTunePipeline:
    """End-to-end fine-tuning: data → Unsloth on Modal → GGUF → Ollama."""

    SUPPORTED_BASE_MODELS = [
        "unsloth/Qwen2.5-7B-bnb-4bit",
        "unsloth/Qwen2.5-14B-bnb-4bit",
        "unsloth/Qwen2.5-Coder-7B-bnb-4bit",
        "unsloth/gemma-2-9b-it-bnb-4bit",
        "unsloth/Llama-3.2-3B-Instruct-bnb-4bit",
        "unsloth/DeepSeek-R1-Distill-Qwen-7B-bnb-4bit",
    ]

    def __init__(self) -> None:
        self._check_modal()

    def _check_modal(self) -> None:
        try:
            import modal
            self._available = True
        except ImportError:
            self._available = False
            logger.warning("finetune: modal not installed")

    @property
    def available(self) -> bool:
        return self._available

    def list_base_models(self) -> list[str]:
        return self.SUPPORTED_BASE_MODELS

    async def run(
        self,
        base_model: str = "unsloth/Qwen2.5-7B-bnb-4bit",
        dataset_path: str = "",
        output_name: str = "symbiont-custom",
        gpu: str = "L4",
        epochs: int = 1,
        lora_r: int = 16,
        max_seq_length: int = 2048,
        import_to_ollama: bool = True,
    ) -> dict:
        """
        Run the full fine-tune pipeline.

        1. Upload dataset to Modal Volume
        2. Fine-tune with Unsloth
        3. Export to GGUF
        4. Import into Ollama (optional)
        """
        if not self._available:
            return {"error": "Modal not installed", "status": "failed"}

        logger.info("finetune: starting pipeline — %s on %s GPU", base_model, gpu)

        # Step 1: Validate
        if dataset_path and not Path(dataset_path).exists():
            return {"error": f"Dataset not found: {dataset_path}", "status": "failed"}

        # Step 2: Run fine-tune on Modal
        result = await self._modal_finetune(
            base_model=base_model,
            dataset_path=dataset_path,
            output_name=output_name,
            gpu=gpu,
            epochs=epochs,
            lora_r=lora_r,
            max_seq_length=max_seq_length,
        )

        if result.get("status") != "done":
            return result

        # Step 3: Export to GGUF on Modal
        gguf_result = await self._modal_export_gguf(output_name, gpu)

        # Step 4: Import into Ollama
        if import_to_ollama and gguf_result.get("status") == "done":
            ollama_result = await self._import_to_ollama(output_name, gguf_result.get("gguf_path", ""))
            result["ollama"] = ollama_result

        result["gguf"] = gguf_result
        return result

    async def _modal_finetune(self, base_model: str, dataset_path: str,
                                output_name: str, gpu: str, epochs: int,
                                lora_r: int, max_seq_length: int) -> dict:
        """Run Unsloth fine-tune on Modal."""

        # Upload dataset if provided
        dataset_upload = ""
        if dataset_path:
            dataset_upload = f'''
    # Load custom dataset
    from datasets import load_dataset
    dataset = load_dataset("json", data_files="/data/train.jsonl", split="train")
'''
        else:
            dataset_upload = '''
    # Use default demo dataset
    from datasets import load_dataset
    dataset = load_dataset("yahma/alpaca-cleaned", split="train[:1000]")
'''

        script = f'''
import modal
import json

image = modal.Image.debian_slim(python_version="3.11").pip_install(
    "unsloth[colab-new]@git+https://github.com/unslothai/unsloth.git",
    "xformers", "trl", "peft", "accelerate", "bitsandbytes",
    "datasets", "torch",
)
app = modal.App("symbiont-finetune-{output_name}", image=image)
vol = modal.Volume.from_name("symbiont-models", create_if_missing=True)
data_vol = modal.Volume.from_name("symbiont-data", create_if_missing=True)

@app.function(gpu="{gpu}", memory=32768, timeout=7200,
              volumes={{"/models": vol, "/data": data_vol}})
def finetune():
    from unsloth import FastLanguageModel
    from trl import SFTTrainer
    from transformers import TrainingArguments
    import os

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name="{base_model}",
        max_seq_length={max_seq_length},
        load_in_4bit=True,
    )

    model = FastLanguageModel.get_peft_model(
        model,
        r={lora_r},
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
        lora_alpha={lora_r},
        lora_dropout=0,
        bias="none",
        use_gradient_checkpointing="unsloth",
    )

    {dataset_upload}

    # Format dataset
    def format_prompt(example):
        text = f"### Instruction:\\n{{example.get('instruction', '')}}\\n\\n"
        if example.get('input'):
            text += f"### Input:\\n{{example['input']}}\\n\\n"
        text += f"### Response:\\n{{example.get('output', '')}}"
        return {{"text": text}}

    dataset = dataset.map(format_prompt)

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        dataset_text_field="text",
        max_seq_length={max_seq_length},
        args=TrainingArguments(
            per_device_train_batch_size=2,
            gradient_accumulation_steps=4,
            num_train_epochs={epochs},
            warmup_steps=5,
            learning_rate=2e-4,
            fp16=True,
            logging_steps=10,
            output_dir="/models/{output_name}-checkpoints",
            optim="adamw_8bit",
        ),
    )

    trainer.train()

    # Save
    model.save_pretrained("/models/{output_name}")
    tokenizer.save_pretrained("/models/{output_name}")
    vol.commit()

    return {{
        "status": "done",
        "output": "/models/{output_name}",
        "base_model": "{base_model}",
        "epochs": {epochs},
        "lora_r": {lora_r},
    }}

@app.local_entrypoint()
def main():
    result = finetune.remote()
    print("SYMBIONT_RESULT_START")
    print(json.dumps(result))
    print("SYMBIONT_RESULT_END")
'''

        return await self._run_modal_script(script)

    async def _modal_export_gguf(self, output_name: str, gpu: str) -> dict:
        """Export fine-tuned model to GGUF format on Modal."""

        script = f'''
import modal
import json

image = modal.Image.debian_slim(python_version="3.11").pip_install(
    "unsloth[colab-new]@git+https://github.com/unslothai/unsloth.git",
    "torch", "transformers",
)
app = modal.App("symbiont-export-{output_name}", image=image)
vol = modal.Volume.from_name("symbiont-models", create_if_missing=True)

@app.function(gpu="{gpu}", memory=32768, timeout=3600, volumes={{"/models": vol}})
def export():
    from unsloth import FastLanguageModel
    import os

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name="/models/{output_name}",
        max_seq_length=2048,
        load_in_4bit=True,
    )

    # Export to GGUF Q4_K_M
    gguf_path = "/models/{output_name}-gguf"
    model.save_pretrained_gguf(gguf_path, tokenizer, quantization_method="q4_k_m")
    vol.commit()

    files = os.listdir(gguf_path)
    return {{
        "status": "done",
        "gguf_path": gguf_path,
        "files": files,
    }}

@app.local_entrypoint()
def main():
    result = export.remote()
    print("SYMBIONT_RESULT_START")
    print(json.dumps(result))
    print("SYMBIONT_RESULT_END")
'''

        return await self._run_modal_script(script)

    async def _import_to_ollama(self, output_name: str, gguf_path: str) -> dict:
        """Download GGUF from Modal Volume and import into Ollama."""
        try:
            local_dir = Path.home() / ".ollama" / "imports" / output_name
            local_dir.mkdir(parents=True, exist_ok=True)

            # Download from Modal Volume
            result = await asyncio.to_thread(
                subprocess.run,
                ["modal", "volume", "get", "symbiont-models",
                 f"{output_name}-gguf/", str(local_dir), "--force"],
                capture_output=True, text=True, timeout=300,
            )

            if result.returncode != 0:
                return {"error": f"Download failed: {result.stderr[:200]}", "status": "failed"}

            # Find the GGUF file
            gguf_files = list(local_dir.glob("*.gguf"))
            if not gguf_files:
                return {"error": "No GGUF file found after download", "status": "failed"}

            gguf_file = gguf_files[0]

            # Create Ollama Modelfile
            modelfile = local_dir / "Modelfile"
            modelfile.write_text(f"""FROM {gguf_file}

PARAMETER num_ctx 4096
PARAMETER temperature 0.7

SYSTEM "You are a SYMBIONT fine-tuned assistant. Be concise and helpful."
""")

            # Import into Ollama
            result = await asyncio.to_thread(
                subprocess.run,
                ["ollama", "create", output_name, "-f", str(modelfile)],
                capture_output=True, text=True, timeout=300,
            )

            if result.returncode == 0:
                return {"status": "done", "ollama_model": output_name, "gguf": str(gguf_file)}
            else:
                return {"error": result.stderr[:200], "status": "failed"}

        except Exception as e:
            return {"error": str(e), "status": "failed"}

    async def _run_modal_script(self, script: str) -> dict:
        """Execute a Modal script and parse the result."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(script)
            script_path = f.name

        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["modal", "run", script_path],
                capture_output=True, text=True, timeout=7200,
            )

            output = result.stdout
            if "SYMBIONT_RESULT_START" in output:
                start = output.index("SYMBIONT_RESULT_START") + len("SYMBIONT_RESULT_START")
                end = output.index("SYMBIONT_RESULT_END")
                return json.loads(output[start:end].strip())
            elif result.returncode != 0:
                return {"error": result.stderr[:500], "status": "failed"}
            else:
                return {"output": output[:500], "status": "unknown"}
        finally:
            os.unlink(script_path)
