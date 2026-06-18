import pytest

from scripts.factor_engine_v3 import FactorEngineV3


def make_engine():
    engine = FactorEngineV3.__new__(FactorEngineV3)
    engine.factor_count = 0
    return engine


def test_value_factors_are_bounded_and_composed():
    factors = make_engine().calculate_value_factors(
        {"pe_ttm": 15, "pb": 2, "dividend_yield": 3}
    )

    assert factors["value_pe_score"] == 70
    assert factors["value_pb_score"] == 60
    assert factors["value_dividend_score"] == 60
    assert factors["value_composite"] == pytest.approx(190 / 3)


def test_value_factors_ignore_unusable_values():
    factors = make_engine().calculate_value_factors(
        {"pe_ttm": -1, "pb": None, "dividend_yield": 0}
    )

    assert factors == {}
