from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlmodel import Session
import json
import random

from app.db.database import get_db
from app.services.research_logger import log_chat
from app.services.llm import chat_stream, chat as chat_with_llm
from app.services.trigger import detect_trigger
from app.services.session_store import get_session, reset_session
from app.services.report import generate_report
from app.questionnaires.phq9_empathy import empathy_for_answer

from app.questionnaires.phq9 import (
    get_question as get_phq9_question,
    calculate_score as phq9_score,
    interpret_score as phq9_interpret
)

from app.questionnaires.gad7 import (
    get_question as get_gad7_question,
    calculate_score as gad7_score,
    interpret_score as gad7_interpret
)

router = APIRouter()


class ChatRequest(BaseModel):
    session_id: str
    message: str
    history: list[dict] | None = None


class ChatResponse(BaseModel):
    reply: str
    next_action: str
    report: dict | None = None


# -----------------------------
# Professional conversational phrasing
# -----------------------------

_QUESTIONNAIRE_INTROS = [
    "I'd like to understand how you're feeling a little better 🌸 Would you mind if I asked you a few short questions? It will only take a moment.",
    "I can sense that things feel difficult right now 💛 May I ask you a few simple questions? It'll help me get a clearer picture of how you're doing.",
    "I'd like to check in with you more carefully 🤗 I have a few brief questions — very straightforward, just choose a number that feels right for you.",
    "I want to make sure I'm truly understanding what you're going through 💬 Could we do a quick check-in together? Just a few questions.",
    "I'm here with you 🌿 Let me ask you a few things so I can better support you — nothing to worry about, just a gentle check-in.",
]

_OPTIONS_TEXT = (
    "Please choose the number that feels most true for you:\n\n"
    "0 — Not at all\n"
    "1 — Several days\n"
    "2 — More than half the days\n"
    "3 — Nearly every day"
)

_QUESTIONNAIRE_COMPLETE_MSGS = [
    "Thank you so much for answering all of that 🎉 It takes real courage to reflect on how you're feeling. Here's what I found:",
    "I truly appreciate you sharing all of that with me 🙏 That wasn't easy, and I want you to know it matters. Here's your result:",
    "You did wonderfully working through all of those questions 💛 Here's what the scores indicate:",
    "Thank you for being so open with me 🌸 Here's what your responses show:",
]

_TRANSITION_PHRASES = [
    "Understood. Moving to the next one 👉",
    "Thank you for that. Here's the next question —",
    "Got it 😊 Here's the next one:",
    "Noted. Almost there —",
    "You're doing really well! Next question 💪",
    "Appreciated. Here's the next —",
]


def _random(lst: list) -> str:
    return random.choice(lst)


# -----------------------------
# Persona system prompt
# -----------------------------

THOZHI_SYSTEM_PROMPT = """You are Thozhi, a warm, empathetic, and professional mental wellness companion.

Your communication style:
- Speak in a calm, caring, and professional tone at all times
- Use clear, simple English that feels approachable but never casual or informal
- You may use supportive emojis where appropriate (💛 🌸 🙏 🤗 🌿 💬)
- Never use informal words, slang, or colloquial terms such as "da", "machan", "machi", "chellam", "yaar", "bro", "dude", "ayyo", "aiyyo", or any regional slang
- Always be respectful, non-judgmental, and compassionate
- Never provide diagnoses, prescriptions, or medical advice
- Never make definitive claims — always encourage professional consultation
- Mirror the user's language (Tamil / English / Tanglish) only in terms of vocabulary, never in slang
- Keep responses concise and meaningful — avoid being overly wordy
- Your role is to support and listen, not to solve or prescribe"""


# -----------------------------
# Shared logic
# -----------------------------

def _handle_questionnaire_or_trigger(session, msg_raw, history, db):
    msg = msg_raw.strip().lower()

    # ── CONSENT ──────────────────────────────────────────────────────────────
    if session.get("consent") is None:
        if msg in ["yes", "agree", "i agree", "y", "ok", "okay", "sure", "haan", "aamam"]:
            session["consent"] = True
            return {
                "type": "response",
                "reply": (
                    "Thank you so much for agreeing — I'm really glad you're here 🙏\n\n"
                    "This is a safe, judgment-free space. "
                    "Please feel free to share whatever is on your mind 💛\n\n"
                    "So, how are you feeling today? 😊"
                ),
                "next_action": "continue_chat",
                "report": None,
            }
        elif msg in ["no", "decline", "nope", "illai", "no thanks"]:
            return {
                "type": "response",
                "reply": (
                    "That's completely okay 🙏 "
                    "Your privacy is important and I respect your decision. "
                    "Please take care of yourself, and know that support is always available when you're ready 🌸"
                ),
                "next_action": "stop",
                "report": None,
            }
        else:
            return {
                "type": "response",
                "reply": (
                    "Hello! 🙏 I'm Thozhi — your personal wellness companion.\n\n"
                    "Before we begin, I'd like to be transparent with you 😊\n\n"
                    "This chatbot is part of a research study. Your conversations may be stored "
                    "anonymously to help improve mental health support for others.\n\n"
                    "Do you agree to continue? Please type YES or NO — there is absolutely no pressure 💛"
                ),
                "next_action": "await_consent",
                "report": None,
            }

    # ── QUESTIONNAIRE MODE ────────────────────────────────────────────────────
    if session["mode"] in ["phq9", "gad7"]:
        try:
            answer = int(msg_raw.strip())
            if answer not in [0, 1, 2, 3]:
                raise ValueError
        except Exception:
            return {
                "type": "response",
                "reply": (
                    "I appreciate your response 😊 For this question, I need a number between 0 and 3. "
                    "Please reply with 0, 1, 2, or 3 — whichever feels most accurate for you."
                ),
                "next_action": "await_answer",
                "report": None,
            }

        session["answers"].append(answer)
        session["question_index"] += 1
        empathy = empathy_for_answer(answer, session["question_index"] - 1)

        next_q = (
            get_phq9_question(session["question_index"])
            if session["mode"] == "phq9"
            else get_gad7_question(session["question_index"])
        )

        if next_q:
            total_questions = 9 if session["mode"] == "phq9" else 7
            progress = f"({session['question_index']}/{total_questions})"
            transition = _random(_TRANSITION_PHRASES)

            reply = (
                f"{empathy}\n\n"
                f"{transition} {progress}\n\n"
                f"{next_q['question']}\n\n"
                f"{_OPTIONS_TEXT}"
            )
            return {
                "type": "response",
                "reply": reply,
                "next_action": "ask_next_question",
                "report": None,
            }

        # ── Questionnaire complete ────────────────────────────────────────────
        if session["mode"] == "phq9":
            score = phq9_score(session["answers"])
            interpretation = phq9_interpret(score)
            domain, tool = "Depression", "PHQ-9"
        else:
            score = gad7_score(session["answers"])
            interpretation = gad7_interpret(score)
            domain, tool = "Anxiety", "GAD-7"

        report = generate_report(
            tool_name=tool, score=score,
            interpretation=interpretation, domain=domain
        )
        reset_session(session.get("session_id", ""))

        completion_msg = _random(_QUESTIONNAIRE_COMPLETE_MSGS)
        reply = (
            f"{completion_msg}\n\n"
            f"📊 {tool} Score: {score}\n"
            f"🔍 {interpretation}\n\n"
            "Please remember — this is a screening result, not a clinical diagnosis. "
            "You are not alone, and support is always available 💛\n\n"
            "You can download your full report below 👇"
        )
        return {
            "type": "response",
            "reply": reply,
            "next_action": "report_generated",
            "report": report,
        }

    # ── NORMAL CHAT — check trigger ───────────────────────────────────────────
    trigger = detect_trigger(msg_raw)

    if trigger["triggered"]:
        session["question_index"] = 0
        session["answers"] = []

        if trigger["type"] == "depression":
            session["mode"] = "phq9"
            q = get_phq9_question(0)
        elif trigger["type"] == "anxiety":
            session["mode"] = "gad7"
            q = get_gad7_question(0)
        else:
            return {"type": "stream", "next_action": "continue_chat"}

        # Explicit request — skip LLM preamble, go straight to questionnaire
        if trigger.get("reason") == "explicit_request":
            intro = _random(_QUESTIONNAIRE_INTROS)
            reply = (
                f"{intro}\n\n"
                f"Question 1 —\n{q['question']}\n\n"
                f"{_OPTIONS_TEXT}"
            )
            return {
                "type": "response",
                "reply": reply,
                "next_action": "start_questionnaire",
                "report": None,
            }

        # Keyword-triggered — LLM responds first, then questionnaire follows
        questionnaire_suffix = (
            f"\n\n{_random(_QUESTIONNAIRE_INTROS)}\n\n"
            f"Question 1 —\n{q['question']}\n\n"
            f"{_OPTIONS_TEXT}"
        )
        return {
            "type": "stream_with_suffix",
            "suffix": questionnaire_suffix,
            "next_action": "start_questionnaire",
        }

    return {"type": "stream", "next_action": "continue_chat"}


# -----------------------------
# POST /chat  — blocking endpoint
# -----------------------------
@router.post("/chat", response_model=ChatResponse)
def chat_endpoint(payload: ChatRequest, db: Session = Depends(get_db)):
    session = get_session(payload.session_id)
    history = payload.history or []

    log_chat(db, payload.session_id, "user", payload.message)

    result = _handle_questionnaire_or_trigger(session, payload.message, history, db)

    if result["type"] == "response":
        log_chat(db, payload.session_id, "bot", result["reply"])
        return ChatResponse(
            reply=result["reply"],
            next_action=result["next_action"],
            report=result.get("report"),
        )

    llm_reply = chat_with_llm(
        payload.message,
        history,
        system_prompt=THOZHI_SYSTEM_PROMPT,
    )

    if result["type"] == "stream_with_suffix":
        full_reply = llm_reply + result["suffix"]
    else:
        full_reply = llm_reply

    log_chat(db, payload.session_id, "bot", full_reply)
    return ChatResponse(reply=full_reply, next_action=result["next_action"], report=None)


# -----------------------------
# POST /chat/stream  — SSE streaming endpoint
# -----------------------------
@router.post("/chat/stream")
async def chat_stream_endpoint(payload: ChatRequest, db: Session = Depends(get_db)):
    session = get_session(payload.session_id)
    history = payload.history or []

    log_chat(db, payload.session_id, "user", payload.message)

    result = _handle_questionnaire_or_trigger(session, payload.message, history, db)

    if result["type"] == "response":
        log_chat(db, payload.session_id, "bot", result["reply"])

        def _single_event():
            yield f"data: {json.dumps({'token': result['reply'], 'done': True, 'next_action': result['next_action'], 'report': result.get('report')})}\n\n"

        return StreamingResponse(_single_event(), media_type="text/event-stream")

    suffix      = result.get("suffix", "")
    next_action = result["next_action"]

    def _sse_generator():
        full_reply = ""

        for token in chat_stream(
            payload.message,
            history,
            system_prompt=THOZHI_SYSTEM_PROMPT,
        ):
            full_reply += token
            yield f"data: {json.dumps({'token': token, 'done': False, 'next_action': None, 'report': None})}\n\n"

        if suffix:
            full_reply += suffix
            yield f"data: {json.dumps({'token': suffix, 'done': False, 'next_action': None, 'report': None})}\n\n"

        log_chat(db, payload.session_id, "bot", full_reply)
        yield f"data: {json.dumps({'token': '', 'done': True, 'next_action': next_action, 'report': None})}\n\n"

    return StreamingResponse(_sse_generator(), media_type="text/event-stream")