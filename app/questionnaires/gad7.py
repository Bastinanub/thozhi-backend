GAD7_QUESTIONS = [
    "Over the last 2 weeks, how often have you felt nervous, anxious, or on edge?",
    "Over the last 2 weeks, how often have you not been able to stop or control worrying?",
    "Over the last 2 weeks, how often have you worried too much about different things?",
    "Over the last 2 weeks, how often have you had trouble relaxing?",
    "Over the last 2 weeks, how often have you been so restless that it is hard to sit still?",
    "Over the last 2 weeks, how often have you become easily annoyed or irritable?",
    "Over the last 2 weeks, how often have you felt afraid as if something awful might happen?"
]

GAD7_OPTIONS = {
    0: "Not at all",
    1: "Several days",
    2: "More than half the days",
    3: "Nearly every day"
}


def get_question(index: int):
    if index < len(GAD7_QUESTIONS):
        return {
            "question_number": index + 1,
            "question": GAD7_QUESTIONS[index],
            "options": GAD7_OPTIONS
        }
    return None


def calculate_score(answers: list[int]) -> int:
    return sum(answers)


def interpret_score(score: int) -> str:
    if score <= 4:
        return "Minimal anxiety symptoms"
    elif score <= 9:
        return "Mild anxiety symptoms"
    elif score <= 14:
        return "Moderate anxiety symptoms"
    else:
        return "Severe anxiety symptoms"
