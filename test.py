from app.services.trigger import detect_trigger

tests = [
    "I feel very sad and hopeless",
    "My heart is racing and I feel anxious",
    "I am okay today",
    "I feel tired and nothing matters anymore",
]

for t in tests:
    print(t)
    print(detect_trigger(t))
    print("-" * 40)
