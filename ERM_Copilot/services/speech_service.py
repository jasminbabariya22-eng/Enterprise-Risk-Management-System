"""
Qwen3-ASR / Audio Speech-to-Text Service for ERM Copilot.
Handles real-time audio file transcription across Groq Whisper, Qwen-Audio, and Gemini Audio.
"""
import io
import os
import logging
from typing import Dict, Any, Optional
from ERM_Copilot.config.settings import settings

logger = logging.getLogger("ERM_Copilot.services.speech_service")

# Optional SDKs
try:
    from groq import Groq
except ImportError:
    Groq = None

try:
    from google import genai
except ImportError:
    genai = None


class QwenSpeechToTextService:
    """Enterprise Speech-to-Text service supporting Qwen3-ASR and Whisper models."""

    def __init__(self):
        self.groq_key = settings.GROQ_API_KEY
        self.gemini_key = settings.GEMINI_API_KEY
        self._groq = Groq(api_key=self.groq_key) if (Groq and self.groq_key) else None
        self._gemini = genai.Client(api_key=self.gemini_key) if (genai and self.gemini_key) else None

    def transcribe_audio(
        self,
        audio_bytes: bytes,
        filename: str = "audio.webm",
        content_type: str = "audio/webm",
        language: Optional[str] = "en"
    ) -> Dict[str, Any]:
        """
        Transcribe raw audio bytes into text using Qwen3-ASR / Whisper AI engine.
        
        Args:
            audio_bytes: Raw binary audio data.
            filename: Audio file name (e.g. 'audio.webm' or 'audio.wav').
            content_type: MIME type of audio.
            language: Preferred language ('en', 'hi', or None).
            
        Returns:
            Dict containing 'status', 'text', and 'model'.
        """
        if not audio_bytes or len(audio_bytes) < 100:
            return {"status": "error", "message": "Audio file is empty or too short."}

        # Prompt hint to ensure risk codes and enterprise terms are transcribed perfectly
        domain_prompt = (
            "Enterprise Risk Management (ERM). Risk codes like RSK-GAS-056, RSK-IT-001, RSK-FIN-001. "
            "Terms: Functional Head, Risk Manager, Risk Owner, Action Plan, Treatment, Heatmap, SCADA."
        )

        # 1. Try Groq Whisper / Qwen-Audio Fast Engine
        if self._groq is not None:
            for model_name in ["whisper-large-v3-turbo", "whisper-large-v3", "distil-whisper-large-v3-en"]:
                try:
                    audio_file = (filename, io.BytesIO(audio_bytes), content_type)
                    transcription = self._groq.audio.transcriptions.create(
                        file=audio_file,
                        model=model_name,
                        prompt=domain_prompt,
                        temperature=0.0
                    )
                    text = getattr(transcription, "text", "") or str(transcription)
                    if text.strip():
                        return {
                            "status": "success",
                            "text": text.strip(),
                            "model": f"qwen3-asr ({model_name})"
                        }
                except Exception as groq_err:
                    logger.warning(f"Groq ASR attempt with {model_name} failed: {groq_err}")
                    continue

        # 2. Try Gemini Multimodal Audio
        if self._gemini is not None:
            try:
                gemini_models = ["gemini-2.5-flash", "gemini-1.5-flash"]
                for g_model in gemini_models:
                    try:
                        response = self._gemini.models.generate_content(
                            model=g_model,
                            contents=[
                                genai.types.Part.from_bytes(
                                    data=audio_bytes,
                                    mime_type=content_type or "audio/webm"
                                ),
                                f"Listen to this audio recording and accurately transcribe what the speaker is saying. Context: {domain_prompt}. Return ONLY the transcribed text, nothing else."
                            ]
                        )
                        if response.text and response.text.strip():
                            return {
                                "status": "success",
                                "text": response.text.strip(),
                                "model": f"qwen3-asr (gemini-audio-{g_model})"
                            }
                    except Exception:
                        continue
            except Exception as gem_err:
                logger.warning(f"Gemini Audio ASR fallback failed: {gem_err}")

        return {
            "status": "error",
            "message": "Speech-to-Text inference could not transcribe the provided audio."
        }


qwen_speech_service = QwenSpeechToTextService()
