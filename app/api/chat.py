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
# Friendly conversational phrasing
# -----------------------------

# Transition into questionnaire — varied so it doesn't feel robotic
_QUESTIONNAIRE_INTROS = [
    "Hey, I just want to understand how you're feeling a little better 🌸 Mind if I ask you a few quick questions? It'll only take a minute, da!",
    "Aiyyo, I can hear that things feel heavy right now 💛 Can I ask you a few small questions? Just to get a clearer picture, okay?",
    "You know what, let me check in with you properly 🤗 I've got a few short questions — super simple, just pick a number. Ready?",
    "Machan, I want to make sure I'm really understanding you 💬 Can we do a quick little check-in together? Just a few questions!",
    "I'm here with you 🌿 Let me ask you a few things so I can understand better — nothing scary, just a small check-in, okay da?",
]

_OPTIONS_TEXT = (
    "Just pick the number that feels most true for you:\n\n"
    "0 — Not at all\n"
    "1 — Several days\n"
    "2 — More than half the days\n"
    "3 — Nearly every day"
)

_QUESTIONNAIRE_COMPLETE_MSGS = [
    "Superb da! 🎉 You did great answering all of that. Here's what I found:",
    "Ayyo, thank you so much for sharing all of that with me 🙏 That takes courage. Here's your result:",
    "You're amazing for going through all of that 💛 Seriously. Here's what the scores say:",
    "Nandri for being so open with me 🌸 Here's what your answers show:",
]

_TRANSITION_PHRASES = [
    "Okay, next one 👉",
    "Got it! Moving on —",
    "Seri, here's the next one 😊",
    "Okay da, almost there —",
    "You're doing great! Next question 💪",
    "Noted! Here's the next —",
]


def _random(lst: list) -> str:
    return random.choice(lst)


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
                    "Ayyo, thank you so much! 🙏 I'm really glad you're here.\n\n"
                    "This is a safe space — no judgment, no pressure. "
                    "Just talk to me like you'd talk to a friend 💛\n\n"
                    "So tell me... how are you feeling today, da? 😊"
                ),
                "next_action": "continue_chat",
                "report": None,
            }
        elif msg in ["no", "decline", "nope", "illai", "no thanks"]:
            return {
                "type": "response",
                "reply": (
                    "Seri, no worries at all! 🙏 "
                    "Your privacy is important. You can close this page safely. "
                    "Take care of yourself, da! 🌸"
                ),
                "next_action": "stop",
                "report": None,
            }
        else:
            return {
                "type": "response",
                "reply": (
                    "Vanakkam! 🙏 I'm Thozhi — your friendly wellness companion.\n\n"
                    "Before we start chatting, I want to be upfront with you 😊\n\n"
                    "This chatbot is part of a research study, and your conversations "
                    "may be stored anonymously to help us improve mental health support.\n\n"
                    "Do you agree to continue? Just type YES or NO — no pressure! 💛"
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
                    "Oops! 😅 I only understand numbers for this one. "
                    "Please reply with 0, 1, 2, or 3 — whichever feels right!"
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
            return {"type": "response", "reply": reply, "next_action": "ask_next_question", "report": None}

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
            "Remember — this is a screening result, not a diagnosis. "
            "You're not alone in this, da 💛\n\n"
            "You can download your full report below 👇"
        )
        return {"type": "response", "reply": reply, "next_action": "report_generated", "report": report}

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

        # For explicit requests skip the LLM preamble — go straight to questionnaire
        if trigger.get("reason") == "explicit_request":
            intro = _random(_QUESTIONNAIRE_INTROS)
            reply = (
                f"{intro}\n\n"
                f"Question 1 —\n{q['question']}\n\n"
                f"{_OPTIONS_TEXT}"
            )
            return {"type": "response", "reply": reply, "next_action": "start_questionnaire", "report": None}

        # For keyword-triggered — LLM responds first, then questionnaire follows
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
        return ChatResponse(reply=result["reply"], next_action=result["next_action"], report=result.get("report"))

    llm_reply = chat_with_llm(payload.message, history)

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

        for token in chat_stream(payload.message, history):
            full_reply += token
            yield f"data: {json.dumps({'token': token, 'done': False, 'next_action': None, 'report': None})}\n\n"

        if suffix:
            full_reply += suffix
            yield f"data: {json.dumps({'token': suffix, 'done': False, 'next_action': None, 'report': None})}\n\n"

        log_chat(db, payload.session_id, "bot", full_reply)
        yield f"data: {json.dumps({'token': '', 'done': True, 'next_action': next_action, 'report': None})}\n\n"

    return StreamingResponse(_sse_generator(), media_type="text/event-stream")