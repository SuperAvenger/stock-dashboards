import numpy as np
import pandas as pd

from scripts.research_assessment import build_score_assessment, research_priority


def price_frame(values):
    return pd.DataFrame({"close": values})


def test_assessment_explains_score_and_discloses_simulated_sources():
    values = np.linspace(100, 150, 140)
    result = build_score_assessment(
        price_frame(values),
        current_price=float(values[-1]),
        market_source="simulated",
        fundamental_source="simulated",
    )

    assert result["score"] >= 50
    assert len(result["factors"]) == 3
    assert result["confidence"] == "low"
    assert "simulated_market_data" in result["risk_flags"]
    assert "simulated_fundamentals" in result["risk_flags"]


def test_research_priority_is_not_an_order_instruction():
    assert research_priority(80) == "重点研究"
    assert research_priority(60) == "持续观察"
    assert research_priority(30) == "谨慎跟踪"
