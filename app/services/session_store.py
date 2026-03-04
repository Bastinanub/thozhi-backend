SESSIONS = {}

def get_session(session_id: str):
    if session_id not in SESSIONS:
        SESSIONS[session_id] = {
            "mode": "chat",            # chat | phq9 | gad7
            "question_index": 0,
            "answers": [],
            "consent": None
        }
    return SESSIONS[session_id]


def reset_session(session_id: str):
    if session_id in SESSIONS:
        del SESSIONS[session_id]
