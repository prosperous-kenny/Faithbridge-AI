from faithbridge_ai.classifier import classify


def test_classify_food():
    result = classify("I cannot afford food for my family this week")
    assert result["category"] == "food"


def test_classify_employment():
    result = classify("I lost my job and need work to support my children")
    assert result["category"] == "employment"


def test_urgency_bounds():
    result = classify("We need urgent medical help immediately")
    assert 0 <= result["urgency_score"] <= 100
    assert result["priority"] in {"critical", "high", "medium", "low"}


def test_emergency_priority():
    result = classify("URGENT emergency eviction happening asap")
    assert result["priority"] == "critical"