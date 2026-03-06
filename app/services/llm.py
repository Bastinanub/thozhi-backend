import os
import json
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from typing import Iterator, List, Dict, Optional
import requests

# -----------------------------
# Ollama configuration
# -----------------------------
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
MODEL_NAME  = os.getenv("MODEL_NAME", "phi3:mini")

# -----------------------------
# Persistent HTTP session
# (reuses the TCP connection instead of opening a new one every message)
# -----------------------------
_session = requests.Session()
_session.mount(
    "http://",
    HTTPAdapter(
        max_retries=Retry(total=2, backoff_factor=0.3),
        pool_connections=1,
        pool_maxsize=1,
    ),
)

# -----------------------------
# Thozhi Persona — trimmed for CPU speed
# Shorter prompt = fewer tokens to process on every single call
# -----------------------------
SYSTEM_PROMPT = """\
You are Thozhi, a warm and caring friend who listens without judgment.

Tone:
- Talk like a close, trusted friend — casual, gentle, real
- Never clinical, never formal
- Short sentences, natural language
- One soft emoji max, only when it genuinely fits

How to respond:
1. First, acknowledge what they said — show you actually heard them
2. Then, if it feels right, offer one small, gentle idea (breathing, journaling, a walk)
3. Never push advice. Phrase it as "maybe" or "if you feel like it"
4. Normalize their feelings without dramatizing them

Hard limits:
- No diagnoses, no medication talk
- Do not suggest professional help unless there is clear risk
- Do not validate self-harm or hopelessness
- You are a friend, not a therapist and not a replacement for real people

Keep responses to 2–3 short sentences. No lists. No meta commentary.\
"""

# -----------------------------
# Chat — streaming version
# Yields text chunks as they arrive so the UI can display them word by word.
# -----------------------------
def chat_stream(
    user_message: str,
    conversation_history: Optional[List[Dict[str, str]]] = None,
) -> Iterator[str]:
    """
    Streams Thozhi's reply token by token via Ollama's /api/chat endpoint.

    Yields:
        str — each chunk of text as it's generated

    Usage (terminal / backend):
        for chunk in chat_stream("I feel so tired"):
            print(chunk, end="", flush=True)

    Usage (FastAPI / Flask SSE):
        return StreamingResponse(chat_stream(msg, history), media_type="text/plain")
    """

    # Build the messages list for /api/chat
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    # Last 4 turns of history  (8 messages: 4 user + 4 assistant)
    if conversation_history:
        for turn in conversation_history[-4:]:
            if turn.get("user"):
                messages.append({"role": "user",      "content": turn["user"]})
            if turn.get("bot"):
                messages.append({"role": "assistant", "content": turn["bot"]})

    messages.append({"role": "user", "content": user_message})

    try:
        with _session.post(
            f"{OLLAMA_URL}/api/chat",
            json={
                "model":  MODEL_NAME,
                "messages": messages,
                "stream": True,
                "options": {
                    # --- Speed knobs for CPU ---
                    "num_predict":   80,   # hard cap on output tokens; keeps replies short
                    "num_ctx":       512,  # context window — smaller = much faster on CPU
                    "temperature":   0.6,  # slightly higher than before for a warmer, less robotic feel
                    "top_p":         0.85,
                    "repeat_penalty": 1.1, # discourages repetitive filler phrases
                    # Clean stop tokens — no system-prompt phrases that cause early cutoff
                    "stop": ["\nUser:", "\n\nUser:", "Human:"],
                },
            },
            stream=True,
            timeout=90,
        ) as resp:
            resp.raise_for_status()
            for raw_line in resp.iter_lines():
                if not raw_line:
                    continue
                try:
                    chunk = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue

                token = chunk.get("message", {}).get("content", "")
                if token:
                    yield token

                if chunk.get("done"):
                    break

    except requests.exceptions.ConnectionError:
        yield (
            "Hey, I'm having a tiny hiccup connecting right now. "
            "I'm still here though — try again in a moment 🌿"
        )
    except requests.exceptions.Timeout:
        yield (
            "That took a little longer than expected on my end. "
            "You can send that again whenever you're ready."
        )
    except requests.exceptions.RequestException:
        yield (
            "Something small went wrong on my side. "
            "I'm still with you — just give it another try."
        )


# -----------------------------
# Non-streaming wrapper
# For callers that want the full response as one string.
# -----------------------------
def chat(
    user_message: str,
    conversation_history: Optional[List[Dict[str, str]]] = None,
) -> str:
    """
    Blocking version — collects the full streamed response and returns it.
    Prefer chat_stream() wherever you can render incrementally.
    """
    return "".join(chat_stream(user_message, conversation_history))


# -----------------------------
# Quick terminal test
# -----------------------------
if __name__ == "__main__":
    history = []

    print("Thozhi is ready. Type 'quit' to exit.\n")
    while True:
        user_input = input("You: ").strip()
        if user_input.lower() in ("quit", "exit"):
            break
        if not user_input:
            continue

        print("Thozhi: ", end="", flush=True)
        full_response = ""
        for chunk in chat_stream(user_input, history):
            print(chunk, end="", flush=True)
            full_response += chunk
        print()  # newline after response

        history.append({"user": user_input, "bot": full_response})
        # Backward-compat alias so existing imports don't break
chat_with_llm = chat