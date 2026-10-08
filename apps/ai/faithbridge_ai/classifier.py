import re


class Rule:
    def __init__(self, category: str, keywords: tuple[str, ...]) -> None:
        self.category = category
        self.keywords = keywords


RULES = [
    Rule("food", ("food", "hunger", "grocer", "meal", "eat", "starving", "bread")),
    Rule("education", ("school", "fees", "tuition", "books", "uniform", "class")),
    Rule(
        "medical",
        (
            "medical",
            "hospital",
            "clinic",
            "medicine",
            "treatment",
            "sick",
            "doctor",
            "health",
        ),
    ),
    Rule(
        "employment",
        ("job", "work", "employment", "hiring", "cv", "interview", "salary"),
    ),
    Rule(
        "housing",
        (
            "rent",
            "housing",
            "house",
            "eviction",
            "shelter",
            "accommodation",
            "morgage",
        ),
    ),
    Rule(
        "emergency",
        (
            "urgent",
            "emergency",
            "immediately",
            "asap",
            "disaster",
            "fire",
            "flood",
            "critical",
        ),
    ),
]

PRIORITY_RULES = [
    ("critical", ("urgent", "emergency", "immediately", "asap", "eviction", "critical")),
    ("high", ("need", "cannot", "cannot afford", "lost", "medical", "hospital")),
    ("medium", ("help", "support", "assistance", "out of work")),
]


def classify(text: str) -> dict:
    lowered = text.lower()
    words = set(re.findall(r"[a-z']+", lowered))

    best_category = "emergency"
    best_score = 0
    for rule in RULES:
        score = 0
        for keyword in rule.keywords:
            if keyword in lowered:
                score += 1 if " " in keyword else (2 if keyword in words else 1)
        if score > best_score:
            best_score = score
            best_category = rule.category

    if best_category == "emergency" and best_score <= 2:
        best_category = _fallback_category(lowered, words)

    return {"category": best_category, **score_urgency(text)}


def score_urgency(text: str) -> dict:
    """Urgency and priority for a need.

    Category selection and urgency scoring are deliberately separate: the
    TF-IDF baseline owns the category, while urgency stays on these keyword
    heuristics until Phase 2 calibrates it against labeled data. Keeping them
    split means swapping the classifier cannot silently change urgency.
    """
    lowered = text.lower()
    words = set(re.findall(r"[a-z']+", lowered))
    urgency_score = _urgency_score(lowered, words)
    return {"urgency_score": urgency_score, "priority": _priority(lowered, urgency_score)}



def _fallback_category(text: str, words: set[str]) -> str:
    for rule in RULES:
        if rule.category == "emergency":
            continue
        for keyword in rule.keywords:
            if keyword in text:
                return rule.category
    return "emergency"


def _urgency_score(text: str, words: set[str]) -> int:
    score = 30
    emergency_hits = sum(1 for key in PRIORITY_RULES[0][1] if key in text)
    score += emergency_hits * 20
    if "rent" in text or "eviction" in text or "homeless" in text:
        score += 15
    severity = ("need ", "cannot", "lost", "no money", "no income")
    score += sum(8 for s in severity if s in text)
    if len(words) > 40:
        score += 5
    return max(0, min(100, score))


def _priority(text: str, urgency_score: int) -> str:
    if urgency_score >= 80:
        return "critical"
    if urgency_score >= 60:
        return "high"
    if urgency_score >= 40:
        return "medium"
    return "low"