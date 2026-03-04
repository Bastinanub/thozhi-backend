from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlmodel import Session
import json

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
# Shared logic — returns either a full reply string or triggers a questionnaire.
# Used by both the blocking and streaming endpoints so behaviour stays in sync.
# -----------------------------
def _handle_questionnaire_or_trigger(session, msg_raw, history, db):
    """
    Returns a dict:
        { "type": "response", "reply": str, "next_action": str, "report": dict | None }
    or
        { "type": "stream_prefix", "prefix": str, "next_action": str }
            — means: stream the LLM reply, then append prefix to it in the response
    """
    msg = msg_raw.strip().lower()

    # ── CONSENT ──────────────────────────────────────────────────────────────
    if session.get("consent") is None:
        if msg in ["yes", "agree", "i agree"]:
            session["consent"] = True
            return {
                "type": "response",
                "reply": "Thank you for consenting. You can now talk to me. How are you feeling today?",
                "next_action": "continue_chat",
                "report": None,
            }
        elif msg in ["no", "decline"]:
            return {
                "type": "response",
                "reply": "That's completely okay. No data will be stored. You may close this page safely.",
                "next_action": "stop",
                "report": None,
            }
        else:
            return {
                "type": "response",
                "reply": (
                    "Before we begin, I want to be transparent.\n\n"
                    "This chatbot is part of a research study.\n"
                    "Your conversations may be stored anonymously for research.\n\n"
                    "Do you agree to continue?\n\nType YES or NO."
                ),
                "next_action": "await_consent",
                "report": None,
            }

    # ── QUESTIONNAIRE MODE ────────────────────────────────────────────────────
    if session["mode"] in ["phq9", "gad7"]:
        try:
            answer = int(msg_raw)
            if answer not in [0, 1, 2, 3]:
                raise ValueError
        except Exception:
            return {
                "type": "response",
                "reply": "Please reply with a number: 0, 1, 2, or 3.",
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
            reply = (
                f"{empathy}\n\n"
                f"{next_q['question']}\n\n"
                "Options:\n"
                "0: Not at all\n"
                "1: Several days\n"
                "2: More than half the days\n"
                "3: Nearly every day"
            )
            return {"type": "response", "reply": reply, "next_action": "ask_next_question", "report": None}

        # questionnaire complete
        if session["mode"] == "phq9":
            score = phq9_score(session["answers"])
            interpretation = phq9_interpret(score)
            domain, tool = "Depression", "PHQ-9"
        else:
            score = gad7_score(session["answers"])
            interpretation = gad7_interpret(score)
            domain, tool = "Anxiety", "GAD-7"

        report = generate_report(tool_name=tool, score=score, interpretation=interpretation, domain=domain)
        reset_session(session["session_id"] if "session_id" in session else "")

        reply = (
            "Thank you for answering those questions.\n\n"
            f"{tool} Score: {score}\n"
            f"Interpretation: {interpretation}\n\n"
            "This is a screening result, not a diagnosis."
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
            # triggered but unknown type — fall through to normal chat
            return {"type": "stream", "next_action": "continue_chat"}

        questionnaire_suffix = (
            "\n\nTo understand this better, I'd like to ask a few short questions.\n\n"
            f"{q['question']}\n\n"
            "Options:\n"
            "0: Not at all\n"
            "1: Several days\n"
            "2: More than half the days\n"
            "3: Nearly every day"
        )
        return {
            "type": "stream_with_suffix",
            "suffix": questionnaire_suffix,
            "next_action": "start_questionnaire",
        }

    return {"type": "stream", "next_action": "continue_chat"}


# -----------------------------
# POST /chat  — original blocking endpoint (kept for compatibility)
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

    # stream types — collect full reply for the blocking endpoint
    llm_reply = chat_with_llm(payload.message, history)

    if result["type"] == "stream_with_suffix":
        full_reply = llm_reply + result["suffix"]
    else:
        full_reply = llm_reply

    log_chat(db, payload.session_id, "bot", full_reply)
    return ChatResponse(reply=full_reply, next_action=result["next_action"], report=None)


# -----------------------------
# POST /chat/stream  — SSE streaming endpoint
# Frontend reads this with EventSource / fetch + ReadableStream
# Each SSE event is JSON: { token, done, next_action, report }
# -----------------------------
@router.post("/chat/stream")
async def chat_stream_endpoint(payload: ChatRequest, db: Session = Depends(get_db)):
    session = get_session(payload.session_id)
    history = payload.history or []

    log_chat(db, payload.session_id, "user", payload.message)

    result = _handle_questionnaire_or_trigger(session, payload.message, history, db)

    # ── Non-LLM response (consent, questionnaire) — send as single SSE event ──
    if result["type"] == "response":
        log_chat(db, payload.session_id, "bot", result["reply"])

        def _single_event():
            payload_json = json.dumps({
                "token": result["reply"],
                "done": True,
                "next_action": result["next_action"],
                "report": result.get("report"),
            })
            yield f"data: {payload_json}\n\n"

        return StreamingResponse(_single_event(), media_type="text/event-stream")

    # ── LLM streaming response ─────────────────────────────────────────────────
    suffix      = result.get("suffix", "")
    next_action = result["next_action"]

    def _sse_generator():
        full_reply = ""

        for token in chat_stream(payload.message, history):
            full_reply += token
            yield f"data: {json.dumps({'token': token, 'done': False, 'next_action': None, 'report': None})}\n\n"

        # append questionnaire suffix as one final token (if trigger fired)
        if suffix:
            full_reply += suffix
            yield f"data: {json.dumps({'token': suffix, 'done': False, 'next_action': None, 'report': None})}\n\n"

        log_chat(db, payload.session_id, "bot", full_reply)

        # final done event
        yield f"data: {json.dumps({'token': '', 'done': True, 'next_action': next_action, 'report': None})}\n\n"

    return StreamingResponse(_sse_generator(), media_type="text/event-stream")
