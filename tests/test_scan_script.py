"""Tests for scripts/scan.py, the screen-then-analyze helper."""

import importlib.util
import sys
from pathlib import Path

import pytest

from cli.models import AnalystType

_SPEC = importlib.util.spec_from_file_location(
    "scan", Path(__file__).resolve().parents[1] / "scripts" / "scan.py"
)
scan = importlib.util.module_from_spec(_SPEC)
sys.modules["scan"] = scan   # dataclasses look their module up here
_SPEC.loader.exec_module(scan)

pytestmark = pytest.mark.unit

ALL = [AnalystType.MARKET, AnalystType.SOCIAL, AnalystType.NEWS, AnalystType.FUNDAMENTALS]


class FakeGraph:
    """Stands in for TradingAgentsGraph: a rating per ticker, or an error."""

    instances = []

    def __init__(self, selected_analysts, config):
        self.selected_analysts = selected_analysts
        self.config = config
        self.calls = []
        FakeGraph.instances.append(self)

    def propagate(self, ticker, date, asset_type):
        self.calls.append((ticker, date, asset_type))
        outcome = self.config["outcomes"][ticker]
        if isinstance(outcome, Exception):
            raise outcome
        return {"final_rating": outcome}, outcome

    def save_reports(self, state, ticker):
        folder = Path(self.config["results_dir"]) / "reports" / ticker
        folder.mkdir(parents=True, exist_ok=True)
        return folder / "complete_report.md"


@pytest.fixture(autouse=True)
def _reset_fake():
    FakeGraph.instances = []


def test_read_watchlist_skips_comments_and_blanks(tmp_path):
    path = tmp_path / "watchlist.txt"
    path.write_text("# my list\naapl\n\nMSFT  # cloud\nnvda, amd\n", encoding="utf-8")
    assert scan.read_watchlist(path) == ["aapl", "MSFT", "nvda", "amd"]


def test_canonical_tickers_uppercases_and_dedupes():
    assert scan.canonical_tickers(["aapl", "AAPL", "btc-usd", "msft"]) == ["AAPL", "BTC-USD", "MSFT"]


def test_canonical_tickers_refuses_garbage():
    with pytest.raises(ValueError):
        scan.canonical_tickers(["../etc"])


def test_fetch_screen_maps_quotes_and_caps_count():
    calls = []

    def fake_screen(name, count):
        calls.append((name, count))
        return {"quotes": [
            {"symbol": "AAA", "shortName": "Alpha", "regularMarketPrice": 10.0,
             "regularMarketChangePercent": 1.5, "marketCap": 2e9},
            {"symbol": "BBB", "longName": "Beta Corp"},
            {"shortName": "no symbol"},
            {"symbol": "CCC"},
        ]}

    candidates = scan.fetch_screen("undervalued_large_caps", 2, screen=fake_screen)
    assert calls == [("undervalued_large_caps", 2)]
    assert [c.symbol for c in candidates] == ["AAA", "BBB"]
    assert candidates[0].name == "Alpha" and candidates[0].market_cap == 2e9
    assert candidates[1].name == "Beta Corp"


def test_fetch_screen_rejects_unknown_name():
    with pytest.raises(ValueError, match="unknown screen"):
        scan.fetch_screen("top_etfs_us", 5, screen=lambda *a, **k: {})


def test_ranked_orders_bullish_first_and_failures_last():
    results = [scan.Result(t, r) for t, r in [
        ("E", scan.FAILED), ("A", "Sell"), ("B", "Buy"), ("C", "REVIEW"), ("D", "Hold"), ("F", "Overweight"),
    ]]
    assert [r.rating for r in scan.ranked(results)] == ["Buy", "Overweight", "Hold", "Sell", "REVIEW", scan.FAILED]


def test_analyze_all_records_failures_and_reuses_graph(tmp_path):
    config = {"results_dir": str(tmp_path),
              "outcomes": {"AAPL": "Buy", "MSFT": RuntimeError("no data"), "NVDA": "Hold"}}
    results = scan.analyze_all(["AAPL", "MSFT", "NVDA"], "2026-10-01", ALL, config, graph_factory=FakeGraph)

    assert len(FakeGraph.instances) == 1
    assert FakeGraph.instances[0].selected_analysts == ["market", "social", "news", "fundamentals"]
    assert [(r.ticker, r.rating) for r in results] == [("AAPL", "Buy"), ("MSFT", scan.FAILED), ("NVDA", "Hold")]
    assert results[0].report.name == "complete_report.html"
    assert "no data" in results[1].error


def test_analyze_all_builds_crypto_graph_without_fundamentals(tmp_path):
    config = {"results_dir": str(tmp_path), "outcomes": {"AAPL": "Buy", "BTC-USD": "Hold"}}
    scan.analyze_all(["AAPL", "BTC-USD"], "2026-10-01", ALL, config, graph_factory=FakeGraph)

    stock, crypto = FakeGraph.instances
    assert crypto.selected_analysts == ["market", "social", "news"]
    assert crypto.calls == [("BTC-USD", "2026-10-01", "crypto")]
    assert stock.calls == [("AAPL", "2026-10-01", "stock")]


def test_write_summary_ranks_and_links_reports(tmp_path):
    report = tmp_path / "r" / "complete_report.html"
    results = [scan.Result("MSFT", scan.FAILED, error="boom <x>"), scan.Result("AAPL", "Buy", report=report)]
    md_path, html_path = scan.write_summary(results, tmp_path / "out", "Scan")

    md = md_path.read_text(encoding="utf-8")
    assert md.index("AAPL") < md.index("MSFT")
    page = html_path.read_text(encoding="utf-8")
    assert report.as_uri() in page
    assert "boom &lt;x&gt;" in page


def test_main_dry_run_never_builds_a_graph():
    def explode(*args, **kwargs):
        raise AssertionError("dry run must not build a graph")

    assert scan.main(["--tickers", "AAPL,MSFT", "--dry-run"], graph_factory=explode) == 0


def test_main_screen_dry_run_uses_top(monkeypatch):
    seen = {}

    def fake_screen(name, count):
        seen["count"] = count
        return {"quotes": [{"symbol": s} for s in ("AAA", "BBB", "CCC")]}

    assert scan.main(["--screen", "most_actives", "--top", "3", "--dry-run"], screen=fake_screen) == 0
    assert seen["count"] == 3


def test_main_screen_network_error_is_reported(capsys):
    def offline(name, count):
        raise RuntimeError("tunnel failed")

    assert scan.main(["--screen", "most_actives", "--dry-run"], screen=offline) == 2


def test_main_refuses_without_yes_when_not_a_terminal(monkeypatch):
    monkeypatch.setattr(scan.sys.stdin, "isatty", lambda: False, raising=False)
    assert scan.main(["--tickers", "AAPL"], graph_factory=FakeGraph) == 2
    assert FakeGraph.instances == []


def test_main_runs_and_writes_summary(tmp_path, monkeypatch):
    from tradingagents.default_config import DEFAULT_CONFIG

    monkeypatch.setitem(DEFAULT_CONFIG, "results_dir", str(tmp_path))
    monkeypatch.setitem(DEFAULT_CONFIG, "outcomes", {"AAPL": "Overweight", "MSFT": "Sell"})
    code = scan.main(["--tickers", "MSFT,AAPL", "--date", "2026-10-01", "--yes", "--no-open"],
                     graph_factory=FakeGraph)

    assert code == 0
    summaries = list((tmp_path / "scans").glob("*/summary.md"))
    assert len(summaries) == 1
    text = summaries[0].read_text(encoding="utf-8")
    assert text.index("AAPL") < text.index("MSFT")
