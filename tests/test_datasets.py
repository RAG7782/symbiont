"""Tests for dataset generation."""

import json
import os
import tempfile

import pytest

from symbiont.datasets import generate_dataset, list_presets, validate_dataset, PRESETS


class TestListPresets:
    def test_has_presets(self):
        presets = list_presets()
        assert "legal-br" in presets
        assert "coding-python" in presets
        assert "general" in presets

    def test_preset_structure(self):
        presets = list_presets()
        for name, info in presets.items():
            assert "name" in info
            assert "description" in info
            assert "base_model" in info
            assert "examples" in info
            assert info["examples"] > 0


class TestGenerateDataset:
    def test_generate_legal(self):
        path = tempfile.mktemp(suffix=".jsonl")
        try:
            result = generate_dataset("legal-br", path)
            assert result["examples"] > 0
            assert os.path.exists(path)
            # Validate JSONL format
            with open(path) as f:
                for line in f:
                    entry = json.loads(line)
                    assert "instruction" in entry
                    assert "output" in entry
                    assert "system" in entry
        finally:
            os.unlink(path)

    def test_generate_coding(self):
        path = tempfile.mktemp(suffix=".jsonl")
        try:
            result = generate_dataset("coding-python", path)
            assert result["examples"] > 0
            assert result["base_model"] == "unsloth/Qwen2.5-Coder-7B-bnb-4bit"
        finally:
            os.unlink(path)

    def test_unknown_preset(self):
        result = generate_dataset("nonexistent", "/dev/null")
        assert "error" in result

    def test_count_limit(self):
        path = tempfile.mktemp(suffix=".jsonl")
        try:
            result = generate_dataset("legal-br", path, count=3)
            assert result["examples"] == 3
        finally:
            os.unlink(path)


class TestValidateDataset:
    def test_valid(self):
        path = tempfile.mktemp(suffix=".jsonl")
        with open(path, "w") as f:
            f.write(json.dumps({"instruction": "test", "output": "ok"}) + "\n")
        try:
            result = validate_dataset(path)
            assert result["valid"] is True
            assert result["examples"] == 1
        finally:
            os.unlink(path)

    def test_invalid_json(self):
        path = tempfile.mktemp(suffix=".jsonl")
        with open(path, "w") as f:
            f.write("not json\n")
        try:
            result = validate_dataset(path)
            assert result["valid"] is False
        finally:
            os.unlink(path)

    def test_missing_fields(self):
        path = tempfile.mktemp(suffix=".jsonl")
        with open(path, "w") as f:
            f.write(json.dumps({"instruction": "test"}) + "\n")
        try:
            result = validate_dataset(path)
            assert result["valid"] is False
        finally:
            os.unlink(path)

    def test_file_not_found(self):
        result = validate_dataset("/nonexistent/path.jsonl")
        assert result["valid"] is False
