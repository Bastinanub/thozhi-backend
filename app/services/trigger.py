import re
from collections import deque

# -----------------------------
# Trigger keyword dictionaries
# -----------------------------

DEPRESSION_KEYWORDS = {
    "sad", "hopeless", "worthless", "empty", "tired", "exhausted",
    "lonely", "helpless", "crying", "numb", "unmotivated", "depressed",
    "low", "defeated", "hollow", "withdrawn", "isolated", "tearful",
    "no energy", "lost interest", "nothing matters", "cant get up",
    "no point", "feel nothing", "hate myself", "given up", "no motivation",
    "cant stop crying", "feel like a burden",
}

ANXIETY_KEYWORDS = {
    "anxious", "anxiety", "panic", "worried", "worry", "fear", "nervous",
    "restless", "scared", "uneasy", "stressed", "stress", "dread", "overwhelmed",
    "tense", "jittery", "paranoid",
    "panic attack", "overthinking", "heart racing", "heart beating fast",
    "palpitations", "cant breathe", "shortness of breath", "feel trapped",
    "mind wont stop", "worst case", "going to fail", "something bad",
}

# Phrases that mean the user is explicitly asking for a questionnaire
EXPLICIT_REQUEST_PATTERNS = [
    # Depression / PHQ-9
    r"\bphq\b", r"\bphq.?9\b",
    r"\bdepress\w*\s+(test|quiz|check|questionnaire|screening|assessment)\b",
    r"\b(test|check|assess|screen)\s+(my\s+)?(depression|mood)\b",
    r"\bam i (depressed|feeling depressed)\b",
    r"\btake\s+(a\s+)?(depression|phq)\b",

    # Anxiety / GAD-7
    r"\bgad\b", r"\bgad.?7\b",
    r"\banxi\w*\s+(test|quiz|check|questionnaire|screening|assessment)\b",
    r"\b(test|check|assess|screen)\s+(my\s+)?(anxiety)\b",
    r"\bam i (anxious|having anxiety)\b",
    r"\btake\s+(a\s+)?(anxiety|gad)\b",

    # Generic questionnaire requests
    r"\b(start|take|do|begin|give me|run|open)\s+(a\s+)?(questionnaire|quiz|test|screening|assessment)\b",
    r"\bquestion(naire)?\b.*\b(depression|anxiety|mood|mental health)\b",
    r"\b(mental health|mood)\b.*\b(test|check|quiz|questionnaire)\b",
    r"\bi want (to )?(take|do|answer)\b",
    r"\bcheck (my|on my) (mental health|mood|anxiety|depression)\b",
]

# Window and threshold settings
WINDOW_SIZE           = 3   # messages to look back
DEPRESSION_THRESHOLD  = 2   # keyword hits across window to auto-trigger
ANXIETY_THRESHOLD     = 2
INSTANT_THRESHOLD     = 2   # keyword hits in a SINGLE message → trigger immediately
COOLDOWN_MESSAGES     = 10


# -----------------------------
# Utility functions
# -----------------------------

def normalize_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def keyword_score(text: str, keywords: set) -> int:
    return sum(1 for kw in keywords if kw in text)


def _check_explicit_request(text: str) -> dict:
    """
    Check if the user is directly asking for a questionnaire.
    Returns trigger dict or None.
    """
    for pattern in EXPLICIT_REQUEST_PATTERNS:
        if re.search(pattern, text):
            # Determine which type they're asking for
            if re.search(r"\bdepress\w*|phq\b", text):
                return {"triggered": True, "type": "depression", "confidence": 99, "cooldown_active": False, "reason": "explicit_request"}
            if re.search(r"\banxi\w*|gad\b", text):
                return {"triggered": True, "type": "anxiety",    "confidence": 99, "cooldown_active": False, "reason": "explicit_request"}
            # Generic request — default to depression screening
            return {"triggered": True, "type": "depression", "confidence": 99, "cooldown_active": False, "reason": "explicit_request"}
    return None


# -----------------------------
# Sliding window detector
# -----------------------------

class TriggerDetector:
    """
    Stateful trigger detector with three trigger modes:
    1. Explicit request  — user directly asks for a questionnaire (instant)
    2. Single-message    — enough keywords in one message (instant)
    3. Window-based      — keywords accumulate across recent messages
    """

    def __init__(
        self,
        window_size: int          = WINDOW_SIZE,
        depression_threshold: int = DEPRESSION_THRESHOLD,
        anxiety_threshold: int    = ANXIETY_THRESHOLD,
        instant_threshold: int    = INSTANT_THRESHOLD,
        cooldown_messages: int    = COOLDOWN_MESSAGES,
    ):
        self.window_size          = window_size
        self.depression_threshold = depression_threshold
        self.anxiety_threshold    = anxiety_threshold
        self.instant_threshold    = instant_threshold
        self.cooldown_messages    = cooldown_messages

        self._window: deque       = deque(maxlen=window_size)
        self._cooldown_remaining  = 0

    def add_message(self, user_message: str) -> dict:
        text = normalize_text(user_message)

        # ── 1. Explicit request — always fires, even during cooldown ──────────
        explicit = _check_explicit_request(text)
        if explicit:
            self._cooldown_remaining = self.cooldown_messages
            self._window.clear()
            return explicit

        dep_score = keyword_score(text, DEPRESSION_KEYWORDS)
        anx_score = keyword_score(text, ANXIETY_KEYWORDS)
        self._window.append((dep_score, anx_score))

        # ── Cooldown check (after explicit request bypass above) ──────────────
        if self._cooldown_remaining > 0:
            self._cooldown_remaining -= 1
            return {"triggered": False, "type": None, "confidence": 0, "cooldown_active": True}

        # ── 2. Single-message instant trigger ─────────────────────────────────
        if dep_score >= self.instant_threshold or anx_score >= self.instant_threshold:
            trigger_type = "depression" if dep_score >= anx_score else "anxiety"
            confidence   = max(dep_score, anx_score)
            self._cooldown_remaining = self.cooldown_messages
            self._window.clear()
            return {"triggered": True, "type": trigger_type, "confidence": confidence, "cooldown_active": False, "reason": "instant"}

        # ── 3. Window-based accumulation ──────────────────────────────────────
        total_dep = sum(d for d, _ in self._window)
        total_anx = sum(a for _, a in self._window)

        if total_dep >= self.depression_threshold or total_anx >= self.anxiety_threshold:
            trigger_type = "depression" if total_dep >= total_anx else "anxiety"
            confidence   = max(total_dep, total_anx)
            self._cooldown_remaining = self.cooldown_messages
            self._window.clear()
            return {"triggered": True, "type": trigger_type, "confidence": confidence, "cooldown_active": False, "reason": "window"}

        return {"triggered": False, "type": None, "confidence": 0, "cooldown_active": False}

    def reset(self):
        self._window.clear()
        self._cooldown_remaining = 0


# -----------------------------
# Stateless single-message wrapper
# Used by chat.py — still works, now with explicit request detection
# -----------------------------

def detect_trigger(user_message: str) -> dict:
    text = normalize_text(user_message)

    # Explicit request always wins
    explicit = _check_explicit_request(text)
    if explicit:
        return explicit

    dep = keyword_score(text, DEPRESSION_KEYWORDS)
    anx = keyword_score(text, ANXIETY_KEYWORDS)

    if dep == 0 and anx == 0:
        return {"triggered": False, "type": None, "confidence": 0}

    # Instant trigger on single message
    if dep >= INSTANT_THRESHOLD or anx >= INSTANT_THRESHOLD:
        trigger_type = "depression" if dep >= anx else "anxiety"
        return {"triggered": True, "type": trigger_type, "confidence": max(dep, anx)}

    # Single keyword — not enough on its own
    return {"triggered": False, "type": None, "confidence": 0}


# -----------------------------
# Smoke test
# -----------------------------

if __name__ == "__main__":
    detector = TriggerDetector()

    tests = [
        # Explicit requests
        "can i take a depression test?",
        "i want to do the PHQ-9",
        "check my anxiety please",
        "give me a questionnaire",
        "start the screening",
        # Single-message instant
        "i feel so sad and hopeless today",
        "i am so anxious and stressed and scared",
        # Window-based
        "i have been feeling a bit low",
        "just really tired lately",
        # Neutral
        "i had a good day today",
    ]

    print("=== Trigger Pipeline Test ===\n")
    for msg in tests:
        result = detector.add_message(msg)
        status = ""
        if result["triggered"]:
            reason = result.get("reason", "")
            status = f"  🚨 {result['type'].upper()} [{reason}] (confidence: {result['confidence']})"
        elif result["cooldown_active"]:
            status = "  ⏳ cooldown"
        print(f"  {msg[:55]:<55}{status}")