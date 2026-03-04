import re
from collections import deque

# -----------------------------
# Trigger keyword dictionaries
# -----------------------------

DEPRESSION_KEYWORDS = {
    # Single-word
    "sad", "hopeless", "worthless", "empty", "tired", "exhausted",
    "lonely", "helpless", "crying", "numb", "unmotivated", "depressed",
    "low", "defeated", "hollow", "withdrawn", "isolated", "tearful",
    # Multi-word
    "no energy", "lost interest", "nothing matters", "cant get up",
    "no point", "feel nothing", "hate myself", "given up", "no motivation",
    "cant stop crying", "feel like a burden",
}

ANXIETY_KEYWORDS = {
    # Single-word
    "anxious", "anxiety", "panic", "worried", "worry", "fear", "nervous",
    "restless", "scared", "uneasy", "stressed", "stress", "dread", "overwhelmed",
    "tense", "jittery", "paranoid",
    # Multi-word
    "panic attack", "overthinking", "heart racing", "heart beating fast",
    "palpitations", "cant breathe", "shortness of breath", "feel trapped",
    "mind wont stop", "worst case", "going to fail", "something bad",
}

# How many recent messages to consider
WINDOW_SIZE = 5

# Minimum score to trigger questionnaire (tune as needed)
DEPRESSION_THRESHOLD = 3
ANXIETY_THRESHOLD = 3

# After triggering, ignore further triggers for this many messages
COOLDOWN_MESSAGES = 10


# -----------------------------
# Utility functions
# -----------------------------

def normalize_text(text: str) -> str:
    """Lowercase, strip punctuation but preserve spaces for multi-word matching."""
    text = text.lower()
    # Remove all punctuation except spaces
    text = re.sub(r"[^a-z\s]", "", text)
    # Collapse multiple spaces
    text = re.sub(r"\s+", " ", text).strip()
    return text


def keyword_score(text: str, keywords: set) -> int:
    """
    Count keyword matches. Multi-word keywords are matched as substrings.
    Each keyword match counts once per message (not per occurrence in the message).
    """
    score = 0
    for kw in keywords:
        if kw in text:
            score += 1
    return score


# -----------------------------
# Sliding window detector
# -----------------------------

class TriggerDetector:
    """
    Stateful trigger detector that evaluates scores across a sliding window
    of recent messages. Includes a cooldown to prevent repeated triggering.
    """

    def __init__(
        self,
        window_size: int = WINDOW_SIZE,
        depression_threshold: int = DEPRESSION_THRESHOLD,
        anxiety_threshold: int = ANXIETY_THRESHOLD,
        cooldown_messages: int = COOLDOWN_MESSAGES,
    ):
        self.window_size = window_size
        self.depression_threshold = depression_threshold
        self.anxiety_threshold = anxiety_threshold
        self.cooldown_messages = cooldown_messages

        # Stores (depression_score, anxiety_score) per message
        self._window: deque = deque(maxlen=window_size)
        # Counts down after a trigger fires; no new trigger while > 0
        self._cooldown_remaining: int = 0

    def add_message(self, user_message: str) -> dict:
        """
        Process a new user message and return trigger info.

        Returns:
            {
                "triggered": bool,
                "type": "depression" | "anxiety" | None,
                "confidence": int,   # total keyword hits across window
                "cooldown_active": bool
            }
        """
        text = normalize_text(user_message)

        dep_score = keyword_score(text, DEPRESSION_KEYWORDS)
        anx_score = keyword_score(text, ANXIETY_KEYWORDS)

        self._window.append((dep_score, anx_score))

        # Tick cooldown down
        if self._cooldown_remaining > 0:
            self._cooldown_remaining -= 1
            return {
                "triggered": False,
                "type": None,
                "confidence": 0,
                "cooldown_active": True,
            }

        # Aggregate scores across the window
        total_dep = sum(d for d, _ in self._window)
        total_anx = sum(a for _, a in self._window)

        dep_triggered = total_dep >= self.depression_threshold
        anx_triggered = total_anx >= self.anxiety_threshold

        if dep_triggered or anx_triggered:
            # Pick the higher score; tie → prefer depression
            if total_dep >= total_anx:
                trigger_type = "depression"
                confidence = total_dep
            else:
                trigger_type = "anxiety"
                confidence = total_anx

            # Start cooldown and clear window so scores don't carry over
            self._cooldown_remaining = self.cooldown_messages
            self._window.clear()

            return {
                "triggered": True,
                "type": trigger_type,
                "confidence": confidence,
                "cooldown_active": False,
            }

        return {
            "triggered": False,
            "type": None,
            "confidence": 0,
            "cooldown_active": False,
        }

    def reset(self):
        """Fully reset state (e.g. new session or after questionnaire completed)."""
        self._window.clear()
        self._cooldown_remaining = 0


# -----------------------------
# Convenience wrapper (stateless, single message)
# Use TriggerDetector class for production
# -----------------------------

def detect_trigger(user_message: str) -> dict:
    """
    Stateless single-message check. Useful for quick testing.
    NOTE: For production use, instantiate TriggerDetector and call add_message().
    """
    text = normalize_text(user_message)
    dep = keyword_score(text, DEPRESSION_KEYWORDS)
    anx = keyword_score(text, ANXIETY_KEYWORDS)

    if dep == 0 and anx == 0:
        return {"triggered": False, "type": None, "confidence": 0}

    if dep >= anx:
        return {"triggered": dep >= DEPRESSION_THRESHOLD, "type": "depression", "confidence": dep}
    else:
        return {"triggered": anx >= ANXIETY_THRESHOLD, "type": "anxiety", "confidence": anx}


# -----------------------------
# Quick smoke test
# -----------------------------

if __name__ == "__main__":
    detector = TriggerDetector(
        window_size=5,
        depression_threshold=3,
        anxiety_threshold=3,
        cooldown_messages=10,
    )

    conversation = [
        "I've just been feeling really sad lately",
        "Everything feels so empty and hopeless",
        "I don't know, I'm just so exhausted all the time",
        "Nothing matters anymore honestly",
        "I just feel so numb",  # should trigger depression here
        "I'm doing a bit better today",
        "Though I have been really anxious about work",
        "My heart keeps racing and I can't breathe properly",
        "I keep overthinking everything, it's exhausting",
        "I feel so stressed and nervous all the time",          # cooldown active
        "I feel so stressed and nervous all the time still",    # cooldown active
        "Still panicking about everything",                     # cooldown ends, new window starts
        "Worried about everything all the time",
        "Heart racing again, I feel so scared",
        "I just feel so overwhelmed and dread everything",      # should trigger anxiety here
    ]

    print("=== Trigger Pipeline Test ===\n")
    for i, msg in enumerate(conversation, 1):
        result = detector.add_message(msg)
        status = ""
        if result["triggered"]:
            status = f"  🚨 TRIGGER → {result['type'].upper()} questionnaire (confidence: {result['confidence']})"
        elif result["cooldown_active"]:
            status = "  ⏳ cooldown active"
        print(f"[{i:02}] {msg[:60]:<60}{status}")