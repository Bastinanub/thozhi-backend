PHQ9_QUESTIONS = [
    "Over the last 2 weeks, how often have you felt little interest or pleasure in doing things?",
    "Over the last 2 weeks, how often have you felt down, depressed, or hopeless?",
    "Over the last 2 weeks, how often have you had trouble falling or staying asleep, or sleeping too much?",
    "Over the last 2 weeks, how often have you felt tired or had little energy?",
    "Over the last 2 weeks, how often have you had poor appetite or overeating?",
    "Over the last 2 weeks, how often have you felt bad about yourself — or that you are a failure?",
    "Over the last 2 weeks, how often have you had trouble concentrating on things?",
    "Over the last 2 weeks, how often have you been moving or speaking slowly, or being restless?",
    "Over the last 2 weeks, how often have you had thoughts that you would be better off dead or hurting yourself?"
]

PHQ9_OPTIONS = {
    0: "Not at all",
    1: "Several days",
    2: "More than half the days",
    3: "Nearly every day"
}


def get_question(index: int):
    if index < len(PHQ9_QUESTIONS):
        return {
            "question_number": index + 1,
            "question": PHQ9_QUESTIONS[index],
            "options": PHQ9_OPTIONS
        }
    return None


def calculate_score(answers: list[int]) -> int:
    return sum(answers)


def interpret_score(score: int) -> str:
    if score <= 4:
        return "Minimal depressive symptoms"
    elif score <= 9:
        return "Mild depressive symptoms"
    elif score <= 14:
        return "Moderate depressive symptoms"
    elif score <= 19:
        return "Moderately severe depressive symptoms"
    else:
        return "Severe depressive symptoms"
