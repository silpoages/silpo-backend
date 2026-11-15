import pytest

from app.core.percentages import to_percentages


def test_to_percentages_returns_zeros_when_total_is_zero() -> None:
    assert to_percentages([0, 0, 0]) == [0.0, 0.0, 0.0]


def test_to_percentages_sums_exactly_100() -> None:
    result = to_percentages([1, 1, 1])

    assert result == [33.4, 33.3, 33.3]
    assert sum(result) == pytest.approx(100)


def test_to_percentages_keeps_proportions() -> None:
    assert to_percentages([3, 1, 0]) == [75.0, 25.0, 0.0]
