import os
import json
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from typing import Iterator, List, Dict, Optional

# -----------------------------
# Groq configuration
# -----------------------------
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_URL     = "https://api.groq.com/openai/v1/chat/completions"
MODEL_NAME   = os.getenv("MODEL_NAME", "llama-3.1-8b-instant")  # fast, free, great quality

# -----------------------------
# Persistent HTTP session
# -----------------------------
_session = requests.Session()
_session.mount(
    "https://",
    HTTPAdapter(
        max_retries=Retry(total=2, backoff_factor=0.3),
        pool_connections=1,
        pool_maxsize=1,
    ),
)

# -----------------------------
# Thozhi Persona
# -----------------------------
SYSTEM_PROMPT = """\
You are Thozhi, a warm, funny, and caring friend from Tamil Nadu who listens without judgment.

Personality:
- Talk like a close Tamil friend — casual, affectionate, real, with light humor
- Occasionally use Tamil terms of endearment naturally: "da", "di", "machan", "pa", "ma", "aiyyo", "seri", "nandri", "vanakkam", "illai"
- Use these Tamil words only where they fit naturally — never force them
- Non-Tamil users will still understand the feeling from context
- Use warm, fun emojis that feel genuine (💛 🌸 😂 🙈 🤗 💪 🌿 ✨)
- Never clinical, never formal — you're a friend, not a doctor

How to respond:
1. First acknowledge what they said — show you truly heard them
2. Normalize their feelings warmly without dramatizing
3. If it feels right, offer ONE small gentle idea (breathing, a walk, journaling)
4. Phrase suggestions as "maybe" or "if you feel like it" — never push
5. Light humor is okay when the mood allows — but read the room

Hard limits:
- No diagnoses, no medication talk
- Do not suggest professional help unless there is clear, explicit risk
- Do not validate self-harm or hopelessness
- You are a friend, not a therapist

Examples of your tone:
- "Aiyyo, that sounds really tough da 😔 I hear you."
- "Machan, everyone feels like this sometimes — you're not alone 💛"
- "Seri seri, take a breath first 😄 You've got this pa!"
- "Nee okay-a? That's a lot to carry 🌸"

Keep responses to 2–3 short sentences. No lists. No meta commentary.\
"""

# -----------------------------
# Streaming chat via Groq
# -----------------------------
def chat_stream(
    user_message: str,
    conversation_history: Optional[List[Dict[str, str]]] = None,
) -> Iterator[str]:
    """
    Streams Thozhi's reply token by token via Groq's OpenAI-compatible API.
    Yields str chunks as they arrive.
    """
    if not GROQ_API_KEY:
        yield "Configuration issue — GROQ_API_KEY is not set on the server."
        return

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    if conversation_history:
        for turn in conversation_history[-4:]:
            if turn.get("user"):
                messages.append({"role": "user",      "content": turn["user"]})
            if turn.get("bot"):
                messages.append({"role": "assistant", "content": turn["bot"]})

    messages.append({"role": "user", "content": user_message})

    try:
        with _session.post(
            GROQ_URL,
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type":  "application/json",
            },
            json={
                "model":       MODEL_NAME,
                "messages":    messages,
                "stream":      True,
                "max_tokens":  120,
                "temperature": 0.6,
                "top_p":       0.85,
            },
            stream=True,
            timeout=30,   # Groq is fast — 30s is generous
        ) as resp:
            resp.raise_for_status()
            for raw_line in resp.iter_lines():
                if not raw_line:
                    continue

                line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line

                # SSE lines look like: "data: {...}" or "data: [DONE]"
                if not line.startswith("data:"):
                    continue

                payload = line[5:].strip()
                if payload == "[DONE]":
                    break

                try:
                    chunk = json.loads(payload)
                except json.JSONDecodeError:
                    continue

                token = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                if token:
                    yield token

    except requests.exceptions.ConnectionError:
        yield (
            "Hey, I'm having a tiny hiccup connecting right now. "
            "I'm still here though — try again in a moment 🌿"
        )
    except requests.exceptions.Timeout:
        yield (
            "That took a little longer than expected. "
            "You can send that again whenever you're ready."
        )
    except requests.exceptions.HTTPError as e:
        if e.response is not None and e.response.status_code == 401:
            yield "There's an issue with the server configuration. Please try again later."
        else:
            yield (
                "Something small went wrong on my side. "
                "I'm still with you — just give it another try."
            )
    except requests.exceptions.RequestException:
        yield (
            "Something small went wrong on my side. "
            "I'm still with you — just give it another try."
        )


# -----------------------------
# Blocking wrapper
# -----------------------------
def chat(
    user_message: str,
    conversation_history: Optional[List[Dict[str, str]]] = None,
) -> str:
    return "".join(chat_stream(user_message, conversation_history))


# Backward-compat alias
chat_with_llm = chat


# -----------------------------
# Quick terminal test
# -----------------------------
if __name__ == "__main__":
    history = []
    print("Thozhi is ready (Groq). Type 'quit' to exit.\n")
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
        print()
        history.append({"user": user_input, "bot": full_response})