def empathy_for_answer(answer: int, question_index: int) -> str:
    """
    Generates a short empathetic response based on user's PHQ-9 answer.
    """

    if answer == 0:
        return "I’m glad to hear that this hasn’t been troubling you."

    if answer == 1:
        return "That sounds like it has been a bit difficult at times."

    if answer == 2:
        return "That seems really challenging, and it makes sense to feel affected by that."

    if answer == 3:
        return (
            "I’m really sorry you’ve been experiencing this so often. "
            "Thank you for sharing that with me."
        )

    return ""
