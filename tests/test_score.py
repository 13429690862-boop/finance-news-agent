import pytest

from agent.score import calculate_opportunity_score, classify_priority


def test_calculate_opportunity_score_uses_formula():
    assert calculate_opportunity_score(5, 4, 3, 2) == 30


@pytest.mark.parametrize("value", [0, 6])
def test_calculate_opportunity_score_validates_inputs(value):
    with pytest.raises(ValueError):
        calculate_opportunity_score(value, 4, 3, 2)


def test_calculate_opportunity_score_rejects_zero_difficulty():
    with pytest.raises(ValueError):
        calculate_opportunity_score(5, 4, 3, 0)


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (25, "high"),
        (24.9, "medium"),
        (12, "medium"),
        (11.9, "low"),
    ],
)
def test_classify_priority(score, expected):
    assert classify_priority(score) == expected
