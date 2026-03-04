from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime


# ======================
# CHAT MESSAGE TABLE
# ======================

class ChatLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    session_id: str
    role: str
    message: str

    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ======================
# QUESTIONNAIRE RESULT TABLE
# ======================

class QuestionnaireResult(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    session_id: str
    tool: str
    score: int
    interpretation: str

    timestamp: datetime = Field(default_factory=datetime.utcnow)