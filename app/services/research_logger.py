from sqlmodel import Session
from app.db.models import ChatLog, QuestionnaireResult


def log_chat(db: Session, session_id: str, role: str, message: str):
    log = ChatLog(
        session_id=session_id,
        role=role,
        message=message
    )
    db.add(log)
    db.commit()


def log_questionnaire(
    db: Session,
    session_id: str,
    tool: str,
    score: int,
    interpretation: str
):
    result = QuestionnaireResult(
        session_id=session_id,
        tool=tool,
        score=score,
        interpretation=interpretation
    )
    db.add(result)
    db.commit()