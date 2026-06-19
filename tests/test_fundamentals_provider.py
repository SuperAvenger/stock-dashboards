from types import SimpleNamespace

from scripts.fundamentals_provider import fetch_fundamentals, longport_symbol
from scripts import hk_dashboard, us_dashboard


class FakeQuoteContext:
    def static_info(self, symbols):
        assert symbols == ["NVDA.US"]
        return [
            SimpleNamespace(
                eps_ttm=5,
                bps=20,
                total_shares=1000,
                dividend_yield=0.25,
            )
        ]


def test_fetch_fundamentals_uses_longport_static_info():
    result = fetch_fundamentals("NVDA", 100, quote_context=FakeQuoteContext())

    assert result["pe"] == 20
    assert result["pb"] == 5
    assert result["market_cap"] == 100000
    assert result["source"] == "longport"


def test_missing_credentials_return_explicit_empty_values(monkeypatch):
    monkeypatch.delenv("LONGPORT_APP_KEY", raising=False)
    monkeypatch.delenv("LONGPORT_APP_SECRET", raising=False)
    monkeypatch.delenv("LONGPORT_ACCESS_TOKEN", raising=False)

    result = fetch_fundamentals("00700.HK", 500)

    assert result["pe"] is None
    assert result["source"] == "unavailable"
    assert longport_symbol("00700.HK") == "00700.HK"


def test_dashboards_do_not_generate_mock_prices_by_default(monkeypatch):
    for dashboard in (hk_dashboard, us_dashboard):
        monkeypatch.setattr(dashboard, "LONGPORT_ACCESS_TOKEN", "")
        monkeypatch.setattr(dashboard, "ALLOW_SIMULATED_DATA", False)
        assert dashboard.get_kline("TEST", 30) == []
