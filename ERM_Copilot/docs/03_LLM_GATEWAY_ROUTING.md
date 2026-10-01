# 🌐 LLM Gateway & Smart Multi-Provider Routing

## 1. Overview

Industrial Enterprise Risk Management platforms cannot tolerate LLM downtime or vendor rate limits. The **`SmartLLMGatewayClient`** in `ERM_Copilot.gateway.client` implements a prioritized, self-healing routing architecture that seamlessly cascades across multiple AI providers.

---

## 2. Multi-Tier Provider Failover Strategy

```mermaid
flowchart TD
    Request([Incoming Copilot LLM Request]) --> Tier1{Tier 1: Portkey / Mesh AI Gateway}
    
    Tier1 -->|Success (200 OK)| Response([Formatted Response Returned])
    Tier1 -->|Timeout / Auth / Rate Limit Error| Tier2{Tier 2: Groq LLaMA 3.3 70B}
    
    Tier2 -->|Success (200 OK)| Response
    Tier2 -->|Rate Limit / API Error| Tier3{Tier 3: Google Gemini 2.5 Flash}
    
    Tier3 -->|Success (200 OK)| Response
    Tier3 -->|Exception| DeterministicFallback[Deterministic Rule-Based Response Generator]
    DeterministicFallback --> Response
```

---

## 3. Supported Providers & Configuration

### 3.1. Primary: Portkey / Mesh AI Gateway
- **SDK:** `portkey_ai.Portkey`
- **Environment Key:** `PORTKEY_API_KEY` / `MESH_API_KEY`
- **Gateway URL:** `https://api.portkey.ai/v1` or configured Mesh Endpoint
- **Role:** Centralized observability, rate-limit pooling, and custom routing policies.

### 3.2. Secondary: Groq LLaMA 3.3 (70B Versatile)
- **SDK:** `groq.Groq`
- **Environment Key:** `GROQ_API_KEY`
- **Model:** `llama-3.3-70b-versatile`
- **Role:** High-speed, low-latency reasoning engine with sub-500ms token generation.

### 3.3. Tertiary: Google Gemini 2.5 Flash
- **SDK:** `google.genai.Client`
- **Environment Key:** `GEMINI_API_KEY`
- **Model:** `gemini-2.5-flash`
- **Role:** Massive context window fallback with robust multilingual and chemical/engineering terminology understanding.

---

## 4. Gateway Implementation Details (`gateway/client.py`)

```python
class SmartLLMGatewayClient:
    """Resilient LLM Gateway with automatic multi-provider fallback."""

    def __init__(self):
        # 1. Initialize Portkey/Mesh
        mesh_key = settings.MESH_API_KEY or settings.PORTKEY_API_KEY or ""
        self._pk = Portkey(api_key=mesh_key, base_url=settings.MESH_API_BASE_URL) if mesh_key else None
        
        # 2. Initialize Groq
        self._groq = Groq(api_key=settings.GROQ_API_KEY) if settings.GROQ_API_KEY else None
        
        # 3. Initialize Gemini
        self._gemini = genai.Client(api_key=settings.GEMINI_API_KEY) if settings.GEMINI_API_KEY else None
```

---

## 5. Observability & Tracing

- **Logfire Integration:** Every inbound prompt and role context is instrumented via `logfire.info(...)`.
- **LangSmith Tracing:** Optional distributed trace logging via `LANGSMITH_API_KEY` and `LANGSMITH_PROJECT="MASS_QA_Chatbot_Dev"`.
