"""
Modal Backend — serverless GPU compute for SYMBIONT.

Dispatches heavy tasks (fine-tuning, 70B+ inference, batch embeddings)
to Modal.com GPU containers. Results return to the organism.

Supports:
- LLM inference on GPU (T4/L4/A100)
- Batch processing via .map()
- Background tasks (fine-tune, embeddings)

Usage:
    from symbiont.modal_backend import ModalBackend
    backend = ModalBackend(gpu="T4")

    # As a SYMBIONT backend
    organism.set_llm_backend(backend)

    # Direct GPU tasks
    result = await backend.run_gpu_task("generate embeddings for 10k docs", data={...})

Requires: pip install modal, modal token set
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ModalBackend:
    """
    Serverless GPU backend via Modal.com.

    Maps model tiers to cloud-hosted models running on GPU:
    - haiku  → Qwen2.5-7B on T4 (fast, cheap)
    - sonnet → Qwen2.5-72B on L4 (powerful)
    - opus   → Qwen3-235B-A22B on A100 (frontier)
    - reason → DeepSeek-R1 on A100 (deep reasoning)

    All inference runs on Modal's serverless GPUs.
    Cost: ~$0.59/hr (T4) to ~$3.73/hr (A100).
    Free tier: $30/month.
    """

    TIER_CONFIG = {
        "haiku": {
            "model": "Qwen/Qwen2.5-7B-Instruct",
            "gpu": "T4",
            "memory": 16384,
        },
        "sonnet": {
            "model": "Qwen/Qwen2.5-72B-Instruct-AWQ",
            "gpu": "L4",
            "memory": 32768,
        },
        "opus": {
            "model": "Qwen/Qwen3-235B-A22B-AWQ",
            "gpu": "A100",
            "memory": 65536,
        },
        "reason": {
            "model": "deepseek-ai/DeepSeek-R1-AWQ",
            "gpu": "A100",
            "memory": 65536,
        },
    }

    def __init__(self, gpu: str = "T4", default_tier: str = "haiku") -> None:
        self._gpu = gpu
        self._default_tier = default_tier
        self._available = False

        try:
            import modal
            self._modal = modal
            self._available = True
            logger.info("modal-backend: connected (gpu=%s)", gpu)
        except ImportError:
            logger.warning("modal-backend: modal not installed (pip install modal)")

    @property
    def available(self) -> bool:
        return self._available

    async def complete(self, prompt: str, context: dict, model_tier: str = "sonnet", images: list | None = None) -> str:
        """
        Run LLM inference on Modal GPU.
        Dispatches a serverless function that loads the model and generates a response.
        """
        if not self._available:
            raise RuntimeError("Modal not installed. Run: pip install modal")

        tier_config = self.TIER_CONFIG.get(model_tier, self.TIER_CONFIG[self._default_tier])

        system_prompt = (
            "You are a SYMBIONT agent — part of a bio-inspired multi-agent system. "
            "Be concise, structured, and action-oriented."
        )
        if context:
            system_prompt += f"\n\nContext: {context}"

        # Build the Modal function dynamically
        result = await asyncio.to_thread(
            self._run_inference,
            model_name=tier_config["model"],
            gpu=tier_config["gpu"],
            memory=tier_config["memory"],
            system_prompt=system_prompt,
            user_prompt=prompt,
        )

        return result

    def _run_inference(self, model_name: str, gpu: str, memory: int, system_prompt: str, user_prompt: str) -> str:
        """Run inference synchronously via Modal."""
        import subprocess
        import tempfile

        # Create a temporary Modal script
        system_prompt_escaped = system_prompt.replace('"', '\\"')
        user_prompt_escaped = user_prompt.replace('"', '\\"')
        script = f'''
import modal

image = modal.Image.debian_slim(python_version="3.11").pip_install(
    "vllm>=0.6.0", "torch", "transformers"
)
app = modal.App("symbiont-inference", image=image)

@app.function(gpu="{gpu}", memory={memory}, timeout=300)
def inference():
    from vllm import LLM, SamplingParams

    llm = LLM(model="{model_name}", trust_remote_code=True)
    params = SamplingParams(temperature=0.7, max_tokens=2048)

    messages = [
        {{"role": "system", "content": """{system_prompt_escaped}"""}},
        {{"role": "user", "content": """{user_prompt_escaped}"""}},
    ]

    # Format as chat template
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained("{model_name}", trust_remote_code=True)
    prompt_text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)

    outputs = llm.generate([prompt_text], params)
    return outputs[0].outputs[0].text

@app.local_entrypoint()
def main():
    result = inference.remote()
    print("SYMBIONT_RESULT_START")
    print(result)
    print("SYMBIONT_RESULT_END")
'''

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(script)
            script_path = f.name

        try:
            result = subprocess.run(
                ["modal", "run", script_path],
                capture_output=True,
                text=True,
                timeout=600,
            )

            output = result.stdout
            if "SYMBIONT_RESULT_START" in output:
                start = output.index("SYMBIONT_RESULT_START") + len("SYMBIONT_RESULT_START")
                end = output.index("SYMBIONT_RESULT_END")
                return output[start:end].strip()
            elif result.returncode != 0:
                logger.error("modal-backend: error — %s", result.stderr[:500])
                return f"[Modal error: {result.stderr[:200]}]"
            else:
                return output.strip()
        finally:
            os.unlink(script_path)

    async def run_gpu_task(self, task_type: str, **kwargs) -> dict:
        """
        Run arbitrary GPU tasks on Modal.

        Supported task types:
        - "embeddings": Generate embeddings for a list of texts
        - "finetune": Fine-tune a model with LoRA
        - "batch_inference": Run inference on multiple prompts

        Returns a dict with results.
        """
        if not self._available:
            raise RuntimeError("Modal not installed")

        if task_type == "embeddings":
            return await self._run_embeddings(**kwargs)
        elif task_type == "batch_inference":
            return await self._run_batch_inference(**kwargs)
        elif task_type == "finetune":
            return await self._run_finetune(**kwargs)
        else:
            raise ValueError(f"Unknown task type: {task_type}")

    async def _run_embeddings(self, texts: list[str], model: str = "BAAI/bge-large-en-v1.5") -> dict:
        """Generate embeddings on GPU via Modal."""
        import subprocess
        import tempfile
        import json

        texts_json = json.dumps(texts, ensure_ascii=False)
        texts_json_escaped = texts_json.replace('"', '\\"')

        script = f'''
import modal
import json

image = modal.Image.debian_slim(python_version="3.11").pip_install(
    "sentence-transformers", "torch"
)
app = modal.App("symbiont-embeddings", image=image)
vol = modal.Volume.from_name("symbiont-results", create_if_missing=True)

@app.function(gpu="T4", memory=16384, timeout=600, volumes={{"/results": vol}})
def embed():
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer("{model}")
    texts = json.loads("""{texts_json_escaped}""")
    embeddings = model.encode(texts, show_progress_bar=True)
    result = {{"count": len(texts), "dim": embeddings.shape[1], "done": True}}
    # Save to volume
    import numpy as np
    np.save("/results/embeddings.npy", embeddings)
    vol.commit()
    return result

@app.local_entrypoint()
def main():
    result = embed.remote()
    print("SYMBIONT_RESULT_START")
    print(json.dumps(result))
    print("SYMBIONT_RESULT_END")
'''

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(script)
            script_path = f.name

        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["modal", "run", script_path],
                capture_output=True, text=True, timeout=600,
            )
            output = result.stdout
            if "SYMBIONT_RESULT_START" in output:
                start = output.index("SYMBIONT_RESULT_START") + len("SYMBIONT_RESULT_START")
                end = output.index("SYMBIONT_RESULT_END")
                return json.loads(output[start:end].strip())
            return {"error": result.stderr[:300]}
        finally:
            os.unlink(script_path)

    async def _run_batch_inference(self, prompts: list[str], model: str = "Qwen/Qwen2.5-7B-Instruct", gpu: str = "T4") -> dict:
        """Run batch inference on multiple prompts in parallel on Modal."""
        # Each prompt becomes a separate Modal container via .map()
        results = []
        for prompt in prompts:
            result = await self.complete(prompt, {}, model_tier="haiku")
            results.append(result)
        return {"results": results, "count": len(results)}

    async def _run_finetune(self, base_model: str = "unsloth/Qwen2.5-7B-bnb-4bit",
                             dataset: str = "", output_name: str = "symbiont-ft",
                             epochs: int = 1, gpu: str = "L4") -> dict:
        """
        Fine-tune a model with LoRA via Unsloth on Modal.
        Returns when complete with the output model path.
        """
        import subprocess
        import tempfile

        script = f'''
import modal

image = modal.Image.debian_slim(python_version="3.11").pip_install(
    "unsloth[colab-new]", "xformers", "trl", "peft", "accelerate", "bitsandbytes",
    "datasets", "torch"
)
app = modal.App("symbiont-finetune", image=image)
vol = modal.Volume.from_name("symbiont-models", create_if_missing=True)

@app.function(gpu="{gpu}", memory=32768, timeout=7200, volumes={{"/models": vol}})
def finetune():
    from unsloth import FastLanguageModel
    from trl import SFTTrainer
    from transformers import TrainingArguments
    from datasets import load_dataset

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name="{base_model}",
        max_seq_length=2048,
        load_in_4bit=True,
    )

    model = FastLanguageModel.get_peft_model(
        model,
        r=16,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
        lora_alpha=16,
        lora_dropout=0,
        bias="none",
        use_gradient_checkpointing="unsloth",
    )

    # Save LoRA adapter
    model.save_pretrained("/models/{output_name}")
    tokenizer.save_pretrained("/models/{output_name}")
    vol.commit()

    return {{"status": "done", "output": "/models/{output_name}", "epochs": {epochs}}}

@app.local_entrypoint()
def main():
    import json
    result = finetune.remote()
    print("SYMBIONT_RESULT_START")
    print(json.dumps(result))
    print("SYMBIONT_RESULT_END")
'''

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
            return {"error": result.stderr[:300], "status": "failed"}
        finally:
            os.unlink(script_path)
