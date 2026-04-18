"""Tests for GPURouter — provider detection, routing, and inference dispatch."""

from __future__ import annotations

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from symbiont.gpu_router import GPURouter


class TestProviderDetection:
    def test_empty_env_no_api_providers(self):
        """Without env vars, API providers (together, openrouter, lightning) are absent."""
        with patch.dict(os.environ, {}, clear=False):
            env = {k: v for k, v in os.environ.items()
                   if k not in ("TOGETHER_API_KEY", "OPENROUTER_API_KEY", "LIGHTNING_API_KEY")}
            with patch.dict(os.environ, env, clear=True):
                router = GPURouter()
                assert "together" not in router._providers
                assert "openrouter" not in router._providers
                assert "lightning" not in router._providers

    def test_together_key_registers_provider(self):
        with patch.dict(os.environ, {"TOGETHER_API_KEY": "test-key"}):
            router = GPURouter()
            assert "together" in router._providers
            assert router._providers["together"]["style"] == "api"

    def test_openrouter_key_registers_provider(self):
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}):
            router = GPURouter()
            assert "openrouter" in router._providers
            assert router._providers["openrouter"]["style"] == "api"

    def test_lightning_key_registers_provider(self):
        with patch.dict(os.environ, {"LIGHTNING_API_KEY": "test-key"}):
            router = GPURouter()
            assert "lightning" in router._providers
            assert router._providers["lightning"]["style"] == "serverless"

    def test_modal_registered_when_importable(self):
        mock_modal = MagicMock()
        with patch.dict("sys.modules", {"modal": mock_modal}):
            router = GPURouter()
            assert "modal" in router._providers
            assert router._providers["modal"]["style"] == "serverless"

    def test_modal_absent_when_not_installed(self):
        with patch.dict("sys.modules", {"modal": None}):
            router = GPURouter()
            assert "modal" not in router._providers

    def test_brev_registered_when_binary_present(self):
        with patch("shutil.which", return_value="/usr/local/bin/brev"):
            router = GPURouter()
            assert "brev" in router._providers
            assert router._providers["brev"]["style"] == "persistent"

    def test_brev_absent_when_binary_missing(self):
        with patch("shutil.which", return_value=None):
            router = GPURouter()
            assert "brev" not in router._providers


class TestStatus:
    def test_status_returns_dict(self):
        router = GPURouter()
        s = router.status()
        assert isinstance(s, dict)
        assert "providers" in s
        assert "count" in s
        assert "recommended" in s

    def test_status_count_matches_providers(self):
        with patch.dict(os.environ, {"TOGETHER_API_KEY": "k", "OPENROUTER_API_KEY": "k2"}):
            router = GPURouter()
            s = router.status()
            assert s["count"] == len(router._providers)


class TestBestProvider:
    def test_no_providers_returns_none(self):
        router = GPURouter()
        router._providers = {}
        assert router._best_provider() is None

    def test_api_preferred_for_inference(self):
        """API-style (together, priority=0) wins over serverless for inference."""
        with patch.dict(os.environ, {"TOGETHER_API_KEY": "k"}):
            with patch.dict("sys.modules", {"modal": MagicMock()}):
                router = GPURouter()
                best = router._best_provider("inference")
                assert best == "together"  # priority 0 < modal priority 1

    def test_serverless_preferred_for_compute(self):
        """Serverless (modal, priority=1) wins for non-inference tasks."""
        with patch.dict(os.environ, {"TOGETHER_API_KEY": "k"}):
            with patch.dict("sys.modules", {"modal": MagicMock()}):
                router = GPURouter()
                best = router._best_provider("compute")
                assert best == "modal"

    def test_fallback_to_any_when_no_preferred_style(self):
        router = GPURouter()
        router._providers = {
            "openrouter": {"style": "api", "priority": 3},
        }
        best = router._best_provider("compute")
        assert best == "openrouter"


class TestInference:
    @pytest.mark.asyncio
    async def test_together_inference_dispatched(self):
        with patch.dict(os.environ, {"TOGETHER_API_KEY": "test-key"}):
            router = GPURouter()
            router._providers = {"together": {"style": "api", "priority": 0}}
            router._together_inference = AsyncMock(return_value="mocked response")

            result = await router.inference("hello", provider="together")
            assert result == "mocked response"
            router._together_inference.assert_awaited_once_with("hello", None)

    @pytest.mark.asyncio
    async def test_openrouter_inference_dispatched(self):
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}):
            router = GPURouter()
            router._providers = {"openrouter": {"style": "api", "priority": 3}}
            router._openrouter_inference = AsyncMock(return_value="openrouter response")

            result = await router.inference("hello", provider="openrouter")
            assert result == "openrouter response"

    @pytest.mark.asyncio
    async def test_modal_inference_uses_modal_backend(self):
        mock_mb = MagicMock()
        mock_mb.complete = AsyncMock(return_value="modal response")

        with patch("symbiont.gpu_router.GPURouter._detect_providers"):
            router = GPURouter()
            router._providers = {"modal": {"style": "serverless", "priority": 1}}

        with patch("symbiont.modal_backend.ModalBackend", return_value=mock_mb):
            with patch("symbiont.gpu_router.GPURouter._best_provider", return_value="modal"):
                result = await router.inference("hello", provider="modal")
                assert result == "modal response"

    @pytest.mark.asyncio
    async def test_no_provider_raises_value_error(self):
        router = GPURouter()
        router._providers = {}
        with pytest.raises(ValueError, match="No provider available"):
            await router.inference("hello")

    @pytest.mark.asyncio
    async def test_embeddings_no_modal_raises(self):
        router = GPURouter()
        router._providers = {"together": {"style": "api", "priority": 0}}
        with pytest.raises(ValueError, match="Embeddings require serverless"):
            await router.embeddings(["text"])

    @pytest.mark.asyncio
    async def test_finetune_no_modal_raises(self):
        router = GPURouter()
        router._providers = {"openrouter": {"style": "api", "priority": 3}}
        with pytest.raises(ValueError, match="Fine-tuning requires serverless"):
            await router.finetune("base_model")


class TestTogetherInference:
    @pytest.mark.asyncio
    async def test_together_calls_api(self):
        import httpx

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "4"}}]
        }

        with patch.dict(os.environ, {"TOGETHER_API_KEY": "test-key"}):
            router = GPURouter()
            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                mock_client.post = AsyncMock(return_value=mock_response)
                mock_client_cls.return_value = mock_client

                result = await router._together_inference("What is 2+2?")
                assert result == "4"
                mock_client.post.assert_awaited_once()
                call_kwargs = mock_client.post.call_args
                assert "together.xyz" in call_kwargs[0][0]

    @pytest.mark.asyncio
    async def test_openrouter_calls_api(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "openrouter answer"}}]
        }

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}):
            router = GPURouter()
            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                mock_client.post = AsyncMock(return_value=mock_response)
                mock_client_cls.return_value = mock_client

                result = await router._openrouter_inference("hello")
                assert result == "openrouter answer"
                call_kwargs = mock_client.post.call_args
                assert "openrouter.ai" in call_kwargs[0][0]
