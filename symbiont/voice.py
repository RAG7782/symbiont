"""
SYMBIONT Voice — speech-to-text and text-to-speech integration.

Uses Whisper (OpenAI) for STT and edge-tts/macOS say for TTS.
Enables the SYMBIONT organism to listen and speak.

Usage:
    from symbiont.voice import Voice

    voice = Voice()
    text = voice.listen()              # Record + transcribe
    text = voice.transcribe("file.wav")  # Transcribe existing file
    voice.speak("Olá, mundo!")          # TTS
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


class Voice:
    """Unified voice interface for SYMBIONT — STT via Whisper, TTS via edge-tts/say."""

    def __init__(
        self,
        whisper_model: str = "base",
        language: str = "pt",
        tts_engine: str = "auto",
        tts_voice: str = "pt-BR-FranciscaNeural",
        record_duration: int = 5,
    ):
        self._whisper_model_name = whisper_model
        self._whisper_model = None
        self._language = language
        self._tts_engine = tts_engine  # "edge", "say", or "auto"
        self._tts_voice = tts_voice
        self._record_duration = record_duration

        # Detect available tools
        self._has_sox = shutil.which("sox") is not None
        self._has_edge_tts = shutil.which("edge-tts") is not None
        self._has_say = shutil.which("say") is not None
        self._has_whisper = False

        try:
            import whisper
            self._has_whisper = True
        except ImportError:
            logger.warning("voice: whisper not installed (pip install openai-whisper)")

        if self._tts_engine == "auto":
            self._tts_engine = "edge" if self._has_edge_tts else "say"

    @property
    def available(self) -> bool:
        """Check if at least STT or TTS is available."""
        return self._has_whisper or self._has_edge_tts or self._has_say

    @property
    def capabilities(self) -> dict:
        return {
            "stt": self._has_whisper,
            "tts": self._has_edge_tts or self._has_say,
            "record": self._has_sox,
            "whisper_model": self._whisper_model_name,
            "tts_engine": self._tts_engine,
        }

    # ------------------------------------------------------------------
    # STT — Speech to Text
    # ------------------------------------------------------------------

    def _load_whisper(self):
        if self._whisper_model is None:
            import whisper
            logger.info("voice: loading whisper model '%s'...", self._whisper_model_name)
            self._whisper_model = whisper.load_model(self._whisper_model_name)
        return self._whisper_model

    def transcribe(self, audio_path: str) -> str:
        """Transcribe an audio file to text using Whisper."""
        if not self._has_whisper:
            raise RuntimeError("Whisper not installed. Run: pip install openai-whisper")

        model = self._load_whisper()
        result = model.transcribe(audio_path, language=self._language)
        text = result["text"].strip()
        logger.info("voice: transcribed '%s' → '%s'", audio_path, text[:50])
        return text

    def record(self, duration: int | None = None) -> str:
        """Record audio from microphone using sox. Returns path to wav file."""
        if not self._has_sox:
            raise RuntimeError("sox not installed. Run: brew install sox")

        duration = duration or self._record_duration
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)

        logger.info("voice: recording %ds...", duration)
        subprocess.run(
            ["sox", "-d", "-r", "16000", "-c", "1", tmp.name, "trim", "0", str(duration)],
            check=True,
            stderr=subprocess.DEVNULL,
        )
        return tmp.name

    def listen(self, duration: int | None = None) -> str:
        """Record audio and transcribe to text. The full pipeline."""
        audio_path = self.record(duration)
        try:
            return self.transcribe(audio_path)
        finally:
            os.unlink(audio_path)

    # ------------------------------------------------------------------
    # TTS — Text to Speech
    # ------------------------------------------------------------------

    def speak(self, text: str) -> None:
        """Speak text aloud using edge-tts or macOS say."""
        if self._tts_engine == "edge" and self._has_edge_tts:
            self._speak_edge(text)
        elif self._has_say:
            self._speak_say(text)
        else:
            logger.warning("voice: no TTS engine available")

    def _speak_edge(self, text: str) -> None:
        """TTS via Microsoft Edge neural voices."""
        tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        try:
            subprocess.run(
                ["edge-tts", "--voice", self._tts_voice, "--text", text, "--write-media", tmp.name],
                check=True,
                stderr=subprocess.DEVNULL,
            )
            subprocess.run(["afplay", tmp.name], check=True)
        except Exception as e:
            logger.warning("voice: edge-tts failed (%s), falling back to say", e)
            self._speak_say(text)
        finally:
            os.unlink(tmp.name)

    def _speak_say(self, text: str) -> None:
        """TTS via macOS native say command."""
        subprocess.run(["say", "-v", "Luciana", text])

    def speak_to_file(self, text: str, output_path: str) -> str:
        """Generate TTS audio and save to file."""
        if self._tts_engine == "edge" and self._has_edge_tts:
            subprocess.run(
                ["edge-tts", "--voice", self._tts_voice, "--text", text, "--write-media", output_path],
                check=True,
                stderr=subprocess.DEVNULL,
            )
        elif self._has_say:
            # macOS say can output to AIFF
            subprocess.run(["say", "-v", "Luciana", "-o", output_path, text])
        return output_path
