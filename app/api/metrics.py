from fastapi import APIRouter, Depends
from sqlmodel import Session, select, func

from app.db.database import get_db
from app.db.models import ChatLog, QuestionnaireResult

router = APIRouter(prefix="/metrics", tags=["Research Metrics"])


@router.get("/summary")
def research_summary(db: Session = Depends(get_db)):

    # -----------------------------
    # TOTAL MESSAGES
    # -----------------------------
    total_messages = db.exec(
        select(func.count()).select_from(ChatLog)
    ).one()

    # -----------------------------
    # TOTAL SESSIONS
    # -----------------------------
    sessions = db.exec(
        select(ChatLog.session_id).distinct()
    ).all()

    total_sessions = len(sessions)

    # -----------------------------
    # AVG CONVERSATION LENGTH
    # -----------------------------
    conv_lengths = {}

    logs = db.exec(select(ChatLog)).all()

    for l in logs:
        sid = getattr(l, "session_id", None)
        if sid:
            conv_lengths[sid] = conv_lengths.get(sid, 0) + 1

    avg_length = (
        sum(conv_lengths.values()) / len(conv_lengths)
        if conv_lengths else 0
    )

    # -----------------------------
    # QUESTIONNAIRE DATA
    # -----------------------------
    results = db.exec(select(QuestionnaireResult)).all()

    phq_scores = []
    gad_scores = []

    for r in results:
        tool = getattr(r, "tool_name", "")
        score = getattr(r, "score", 0)

        if tool == "PHQ-9":
            phq_scores.append(score)

        elif tool == "GAD-7":
            gad_scores.append(score)

    avg_phq = sum(phq_scores)/len(phq_scores) if phq_scores else 0
    avg_gad = sum(gad_scores)/len(gad_scores) if gad_scores else 0

    # -----------------------------
    # COMPLETION RATE
    # -----------------------------
    completion_rate = (
        len(results) / total_sessions
        if total_sessions else 0
    )

    return {

        "total_messages": total_messages,
        "total_sessions": total_sessions,
        "avg_conversation_length": round(avg_length, 2),

        "questionnaire_completion_rate": round(completion_rate, 3),

        "avg_phq_score": round(avg_phq, 2),
        "avg_gad_score": round(avg_gad, 2),

        "total_questionnaires": len(results)
    }