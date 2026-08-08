import pytest

from app.intelligence.risk_scoring import (
    RiskInput,
    RiskLevel,
    RiskScorer,
)


@pytest.fixture
def scorer() -> RiskScorer:
    return RiskScorer()


def make_input(**overrides) -> RiskInput:
    values = {
        "battery_soc_percent": 80.0,
        "temperature": 25.0,
        "tower_load_kw": 5.0,
        "solar_power_kw": 5.0,
        "grid_power_kw": 5.0,
    }

    values.update(overrides)
    return RiskInput(**values)


def test_normal_operating_conditions_are_low_risk(scorer):
    result = scorer.calculate(make_input())

    assert result.score < 25
    assert result.level == RiskLevel.LOW
    assert result.reasons == ()


def test_low_battery_soc_increases_risk(scorer):
    result = scorer.calculate(
        make_input(battery_soc_percent=35.0)
    )

    assert result.score >= 25
    assert result.level == RiskLevel.MODERATE
    assert "Battery SOC is below the warning threshold." in result.reasons


def test_critical_battery_soc_adds_high_risk(scorer):
    result = scorer.calculate(
        make_input(battery_soc_percent=20.0)
    )

    assert result.score >= 40
    assert "Battery SOC is at or below the critical threshold." in result.reasons


def test_high_temperature_increases_risk(scorer):
    result = scorer.calculate(
        make_input(temperature=50.0)
    )

    assert result.score >= 12
    assert "Temperature is above the high-temperature threshold." in result.reasons


def test_critical_temperature_increases_risk(scorer):
    result = scorer.calculate(
        make_input(temperature=55.0)
    )

    assert result.score >= 20
    assert "Temperature is at or above the critical threshold." in result.reasons


def test_no_solar_generation_increases_risk(scorer):
    result = scorer.calculate(
        make_input(solar_power_kw=0.0)
    )

    assert result.score >= 10
    assert "Solar generation is unavailable." in result.reasons


def test_insufficient_primary_power_increases_risk(scorer):
    result = scorer.calculate(
        make_input(
            solar_power_kw=1.0,
            grid_power_kw=1.0,
            tower_load_kw=5.0,
        )
    )

    assert result.score >= 10
    assert "Available primary power is below tower load." in result.reasons


def test_grid_unavailable_increases_risk(scorer):
    result = scorer.calculate(
        make_input(grid_power_kw=0.0)
    )

    assert result.score >= 15
    assert "Grid power is unavailable." in result.reasons


def test_multiple_risk_factors_can_produce_critical_risk(scorer):
    result = scorer.calculate(
        make_input(
            battery_soc_percent=10.0,
            temperature=60.0,
            tower_load_kw=10.0,
            solar_power_kw=0.0,
            grid_power_kw=0.0,
        )
    )

    assert result.score == 100.0
    assert result.level == RiskLevel.CRITICAL
    assert len(result.reasons) >= 4


def test_score_never_exceeds_100(scorer):
    result = scorer.calculate(
        make_input(
            battery_soc_percent=0.0,
            temperature=100.0,
            tower_load_kw=100.0,
            solar_power_kw=0.0,
            grid_power_kw=0.0,
        )
    )

    assert result.score == 100.0


def test_score_never_goes_below_zero(scorer):
    result = scorer.calculate(make_input())

    assert result.score >= 0.0


@pytest.mark.parametrize(
    ("score", "expected_level"),
    [
        (0, RiskLevel.LOW),
        (24.99, RiskLevel.LOW),
        (25, RiskLevel.MODERATE),
        (49.99, RiskLevel.MODERATE),
        (50, RiskLevel.HIGH),
        (74.99, RiskLevel.HIGH),
        (75, RiskLevel.CRITICAL),
        (100, RiskLevel.CRITICAL),
    ],
)
def test_risk_level_boundaries(score, expected_level):
    assert RiskScorer._get_level(score) == expected_level


@pytest.mark.parametrize(
    "field,value",
    [
        ("battery_soc_percent", -1),
        ("battery_soc_percent", 101),
        ("tower_load_kw", -1),
        ("solar_power_kw", -1),
        ("grid_power_kw", -1),
    ],
)
def test_invalid_input_is_rejected(field, value, scorer):
    data = make_input(**{field: value})

    with pytest.raises(ValueError):
        scorer.calculate(data)