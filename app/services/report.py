from datetime import datetime

# -----------------------------
# Score range metadata
# -----------------------------

_PHQ9_RANGES = [
    (0,  4,  "Minimal or no depression",    "Your responses suggest little to no signs of depression right now."),
    (5,  9,  "Mild depression",              "Your responses suggest mild depressive symptoms. These are common and manageable."),
    (10, 14, "Moderate depression",          "Your responses suggest a moderate level of depressive symptoms worth paying attention to."),
    (15, 19, "Moderately severe depression", "Your responses suggest moderately severe symptoms. Support is available and can help."),
    (20, 27, "Severe depression",            "Your responses suggest severe symptoms. Please consider reaching out to someone you trust or a professional."),
]

_GAD7_RANGES = [
    (0,  4,  "Minimal anxiety",  "Your responses suggest little to no anxiety symptoms right now."),
    (5,  9,  "Mild anxiety",     "Your responses suggest mild anxiety. Many people experience this and there are ways to ease it."),
    (10, 14, "Moderate anxiety", "Your responses suggest a moderate level of anxiety symptoms worth paying attention to."),
    (15, 21, "Severe anxiety",   "Your responses suggest significant anxiety. Support is available — you don't have to manage this alone."),
]

_COPING_STRATEGIES = {
    "depression": [
        "Keep a small, consistent daily routine — even just getting dressed at the same time each day.",
        "Spend a few minutes outside. Natural light and gentle movement can lift mood over time.",
        "Write down one thing you noticed or felt today — no pressure to make it positive.",
        "Reach out to one person you trust, even just to say hello.",
        "Break tasks into the smallest possible steps and acknowledge finishing each one.",
        "Try to keep a regular sleep schedule, even on weekends, and limit alcohol intake.",
    ],
    "anxiety": [
        "Try box breathing: inhale 4 counts, hold 4, exhale 4, hold 4 — repeat 3–4 times.",
        "Ground yourself with 5-4-3-2-1: notice 5 things you see, 4 you can touch, 3 you hear, 2 you smell, 1 you taste.",
        "Write down what's worrying you, then write one small thing within your control right now.",
        "Limit caffeine, especially after noon — it can amplify anxious feelings significantly.",
        "Do a short body scan: starting from your feet, consciously relax each area upward.",
        "Reduce news and social media if they tend to spike your anxiety.",
    ],
}

_TOOL_META = {
    "PHQ-9": {
        "max": 27,
        "ranges": _PHQ9_RANGES,
        "description": (
            "The PHQ-9 (Patient Health Questionnaire-9) is a validated, widely used tool "
            "for screening and measuring the severity of depression. Scores range from 0 to 27."
        ),
    },
    "GAD-7": {
        "max": 21,
        "ranges": _GAD7_RANGES,
        "description": (
            "The GAD-7 (Generalized Anxiety Disorder-7) is a validated tool for screening "
            "and measuring anxiety severity. Scores range from 0 to 21."
        ),
    },
}

_ANSWER_LABELS = ["Not at all", "Several days", "More than half the days", "Nearly every day"]


def _get_contextual_note(tool_name: str, score: int) -> str:
    meta = _TOOL_META.get(tool_name)
    if not meta:
        return ""
    for low, high, _, note in meta["ranges"]:
        if low <= score <= high:
            return note
    return ""


def _build_score_ranges(tool_name: str) -> list[dict]:
    meta = _TOOL_META.get(tool_name)
    if not meta:
        return []
    return [
        {"range": f"{low}–{high}", "label": label}
        for low, high, label, _ in meta["ranges"]
    ]


# -----------------------------
# Main report generator
# -----------------------------

def generate_report(
    tool_name: str,
    score: int,
    interpretation: str,
    domain: str,
    answers: list[int] | None = None,
    session_history: list[dict] | None = None,
) -> dict:
    """
    Builds a detailed report dict for both API responses and PDF generation.

    Args:
        tool_name:        "PHQ-9" or "GAD-7"
        score:            Raw numeric score
        interpretation:   Short severity label
        domain:           "Depression" or "Anxiety"
        answers:          Optional per-question scores (0–3) for breakdown section
        session_history:  Optional past sessions [{"date": str, "score": int, "interpretation": str}]
    """
    domain_key  = domain.lower()
    meta        = _TOOL_META.get(tool_name, {})
    coping      = _COPING_STRATEGIES.get(domain_key, [])
    score_ranges = _build_score_ranges(tool_name)
    contextual_note = _get_contextual_note(tool_name, score)

    # Per-question breakdown
    question_breakdown = []
    if answers:
        for i, ans in enumerate(answers):
            question_breakdown.append({
                "question_number": i + 1,
                "score": ans,
                "label": _ANSWER_LABELS[ans] if 0 <= ans <= 3 else "Unknown",
            })

    # Severity trend (past sessions + current)
    trend = []
    if session_history:
        for entry in session_history:
            trend.append({
                "date":           entry.get("date", ""),
                "score":          entry.get("score", 0),
                "interpretation": entry.get("interpretation", ""),
            })
    trend.append({
        "date":           datetime.utcnow().strftime("%Y-%m-%d"),
        "score":          score,
        "interpretation": interpretation,
    })

    return {
        # ── Core (backward-compatible) ──────────────────────────────────────
        "domain":         domain,
        "tool_used":      tool_name,
        "score":          score,
        "interpretation": interpretation,
        "generated_at":   datetime.utcnow().isoformat(),

        # ── User-facing summary ─────────────────────────────────────────────
        "summary": contextual_note or (
            f"Your responses indicate {interpretation.lower()}. "
            "This result is based on a standardized screening questionnaire."
        ),

        # ── What the score means ────────────────────────────────────────────
        "tool_description": meta.get("description", ""),
        "score_max":        meta.get("max", 0),
        "score_ranges":     score_ranges,       # [{range, label}, ...]

        # ── Per-question breakdown ──────────────────────────────────────────
        "question_breakdown": question_breakdown,  # [{question_number, score, label}, ...]

        # ── Coping strategies ───────────────────────────────────────────────
        "coping_strategies": coping,            # [str, ...]

        # ── Severity trend ──────────────────────────────────────────────────
        "trend": trend,                         # [{date, score, interpretation}, ...]

        # ── Recommendations (dual-audience) ────────────────────────────────
        "recommendation": (
            "If these feelings are affecting your daily life, talking to a licensed mental health "
            "professional can help. You don't need to be in crisis to seek support — early "
            "conversations with a counsellor or therapist are often the most helpful."
        ),
        "professional_note": (
            f"Screening tool: {tool_name}. Total score: {score}/{meta.get('max', '?')}. "
            f"Severity band: {interpretation}. This is a self-reported screening result and should "
            "be interpreted alongside a full clinical assessment."
        ),
        "disclaimer": (
            "This report is for screening and self-awareness purposes only. "
            "It does not constitute a medical diagnosis or clinical assessment."
        ),
    }
