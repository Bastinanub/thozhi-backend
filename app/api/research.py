from fastapi import APIRouter, Depends
from sqlmodel import Session, select
from fastapi.responses import StreamingResponse
import csv, io, re

from app.db.database import get_db
from app.db.models import ChatLog, QuestionnaireResult

router = APIRouter(prefix="/research", tags=["Research"])


# -------------------------
# SIMPLE ANONYMIZATION
# -------------------------
def anonymize(text: str):

    if not text:
        return ""

    text = re.sub(r'\b\d{10}\b', '[PHONE]', text)
    text = re.sub(r'\S+@\S+', '[EMAIL]', text)

    return text


# -------------------------
# FULL DATASET EXPORT
# -------------------------
@router.get("/export-full")
def export_full(db: Session = Depends(get_db)):

    logs = db.exec(select(ChatLog)).all()
    results = db.exec(select(QuestionnaireResult)).all()

    # Build questionnaire lookup
    q_lookup = {}

    for r in results:

        sid = getattr(r, "session_id", None)

        if sid:
            q_lookup[sid] = {
                "tool": getattr(r, "tool_name", ""),
                "score": getattr(r, "score", ""),
                "interpretation": getattr(r, "interpretation", "")
            }

    # group messages per session
    sessions = {}

    for log in logs:

        data = log.model_dump()

        sid = data.get("session_id")

        sessions.setdefault(sid, []).append(data)

    # create csv
    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "session_id",
        "user_id",
        "message_index",
        "role",
        "message",
        "timestamp",
        "conversation_length",
        "questionnaire_type",
        "questionnaire_score",
        "interpretation"
    ])

    # fill rows
    for sid, msgs in sessions.items():

        conv_len = len(msgs)
        q = q_lookup.get(sid, {})

        for i, m in enumerate(msgs):

            writer.writerow([
                sid,
                sid,  # using session_id as anonymous user_id
                i+1,
                m.get("sender") or m.get("role"),
                anonymize(m.get("message") or m.get("text")),
                m.get("timestamp") or m.get("created_at"),
                conv_len,
                q.get("tool",""),
                q.get("score",""),
                q.get("interpretation","")
            ])

    output.seek(0)

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=thozhi_research_dataset.csv"}
    )