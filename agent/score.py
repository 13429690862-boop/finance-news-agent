"""Opportunity scoring helpers."""


def _validate_score_input(name: str, value: int | float) -> None:
    """Validate that a scoring input is within the accepted 1-5 range."""
    if not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a number")
    if value < 1 or value > 5:
        raise ValueError(f"{name} must be between 1 and 5")


def calculate_opportunity_score(
    market_intensity: int | float,
    china_relevance: int | float,
    monetization_clarity: int | float,
    implementation_difficulty: int | float,
) -> float:
    """Calculate the opportunity score from bounded 1-5 factor ratings."""
    inputs = {
        "market_intensity": market_intensity,
        "china_relevance": china_relevance,
        "monetization_clarity": monetization_clarity,
        "implementation_difficulty": implementation_difficulty,
    }
    for name, value in inputs.items():
        _validate_score_input(name, value)

    if implementation_difficulty == 0:
        raise ValueError("implementation_difficulty must not be zero")

    return market_intensity * china_relevance * monetization_clarity / implementation_difficulty


def classify_priority(score: int | float) -> str:
    """Classify a numeric score as high, medium, or low priority."""
    if score >= 25:
        return "high"
    if score >= 12:
        return "medium"
    return "low"
