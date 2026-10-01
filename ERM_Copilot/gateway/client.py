"""
Multi-Provider LLM Gateway Client for ERM Copilot.
Directly routes completions across Portkey Gateway, Groq, and Google Gemini.
"""
import os
import time
import logging
from types import SimpleNamespace
from typing import List, Dict, Any, Optional

from ERM_Copilot.config.settings import settings

logger = logging.getLogger("ERM_Copilot.gateway.client")

# Optional vendor SDKs
try:
    from portkey_ai import Portkey, PORTKEY_GATEWAY_URL
except ImportError:
    Portkey, PORTKEY_GATEWAY_URL = None, "https://api.portkey.ai/v1"

try:
    from groq import Groq
except ImportError:
    Groq = None

try:
    from google import genai
except ImportError:
    genai = None


class SmartLLMGatewayClient:
    """
    Resilient LLM Gateway with automatic multi-provider fallback.
    """
    def __init__(self):
        self._pk = None
        mesh_key = settings.MESH_API_KEY or settings.PORTKEY_API_KEY or ""
        if Portkey and mesh_key and len(mesh_key) >= 10:
            try:
                self._pk = Portkey(api_key=mesh_key, base_url=settings.MESH_API_BASE_URL)
            except Exception as e:
                logger.debug(f"Portkey init fallback: {e}")

        self._groq = Groq(api_key=settings.GROQ_API_KEY) if (Groq and settings.GROQ_API_KEY) else None
        self._gemini = genai.Client(api_key=settings.GEMINI_API_KEY) if (genai and settings.GEMINI_API_KEY) else None

    class ChatCompletions:
        def __init__(self, parent):
            self.parent = parent

        def create(self, messages: List[Dict[str, str]], temperature: float = 0.1, **kwargs):
            # 1. Try Portkey Gateway
            if self.parent._pk is not None:
                try:
                    return self.parent._pk.chat.completions.create(
                        messages=messages,
                        temperature=temperature
                    )
                except Exception as e:
                    logger.warning(f"[Portkey] Gateway error: {e}. Trying direct Groq/Gemini...")

            # 2. Try Direct Groq
            if self.parent._groq is not None:
                candidate_models = [
                    "llama-3.3-70b-versatile",
                    "llama-3.1-8b-instant",
                    "qwen/qwen3.8-27b"
                ]
                for model_name in candidate_models:
                    try:
                        return self.parent._groq.chat.completions.create(
                            model=model_name,
                            messages=messages,
                            temperature=temperature,
                            timeout=12.0
                        )
                    except Exception:
                        continue

            # 3. Try Direct Google Gemini
            if self.parent._gemini is not None:
                combined_prompt = ""
                for m in messages:
                    role = m.get("role", "user").upper()
                    content = m.get("content", "")
                    combined_prompt += f"[{role}]:\n{content}\n\n"

                gemini_models = ["gemini-2.5-flash", "gemini-1.5-flash"]
                for g_model in gemini_models:
                    try:
                        gemini_resp = self.parent._gemini.models.generate_content(
                            model=g_model,
                            contents=combined_prompt,
                            config={"temperature": temperature}
                        )
                        content_text = gemini_resp.text or ""
                        if content_text:
                            msg_obj = SimpleNamespace(content=content_text)
                            choice_obj = SimpleNamespace(message=msg_obj)
                            return SimpleNamespace(choices=[choice_obj])
                    except Exception:
                        continue

            raise RuntimeError("All configured LLM providers (Portkey, Groq, Gemini) are currently unavailable.")

    @property
    def chat(self):
        class Chat:
            def __init__(self, parent):
                self.completions = SmartLLMGatewayClient.ChatCompletions(parent)
        return Chat(self)


# Global singleton instance
portkey_client = SmartLLMGatewayClient()
