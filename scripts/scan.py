"""Screen for candidates, run TradingAgents on each, and rank the ratings.

TradingAgents analyzes one ticker at a time; it does not search for stocks. This
script supplies the shortlist, from a Yahoo Finance screen or your own list, runs
the full analysis on each ticker, and writes a ranked summary.

    bash scripts/scan.sh --list-screens
    bash scripts/scan.sh --screen undervalued_large_caps --top 5 --dry-run
    bash scripts/scan.sh --screen undervalued_large_caps --top 5
    bash scripts/scan.sh --watchlist watchlist.txt
    bash scripts/scan.sh --tickers AAPL,MSFT,NVDA
"""

from __future__ import annotations

import argparse
import datetime
import html
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console
from rich.table import Table

from cli.models import AssetType
from cli.prompts import (
    detect_asset_type,
    filter_analysts_for_asset_type,
    parse_analysis_date,
    parse_analysts,
    parse_ticker,
)
from tradingagents.agents.rating import RATING_REVIEW, RATINGS_5_TIER, run_rating

console = Console()

# Yahoo's predefined equity screens (yfinance.PREDEFINED_SCREENER_QUERIES), with
# what each looks for. The fund and ETF screens are left out: the pipeline
# analyzes companies.
SCREENS = {
    "undervalued_large_caps": "Large caps with low P/E and PEG ratios",
    "undervalued_growth_stocks": "Earnings growth above 25% with low P/E and PEG",
    "growth_technology_stocks": "Tech stocks with revenue and earnings growth above 25%",
    "most_actives": "US stocks over $2B market cap with the highest trading volume today",
    "day_gainers": "US stocks over $2B market cap up more than 3% today",
    "day_losers": "US stocks over $2B market cap down more than 2.5% today",
    "small_cap_gainers": "Small caps with the biggest gains today",
    "aggressive_small_caps": "Small caps with high earnings growth, by volume",
    "most_shorted_stocks": "Stocks with the highest short interest",
}

FAILED = "FAILED"
# Most bullish first; a run with no readable rating or an error sorts last.
RANK = {rating: index for index, rating in enumerate((*RATINGS_5_TIER, RATING_REVIEW, FAILED))}


@dataclass
class Candidate:
    symbol: str
    name: str = ""
    price: float | None = None
    change_pct: float | None = None
    market_cap: float | None = None


@dataclass
class Result:
    ticker: str
    rating: str
    report: Path | None = None
    error: str | None = None


def read_watchlist(path: Path) -> list[str]:
    """Tickers from a file: one per line (or comma-separated), ``#`` starts a comment."""
    tickers = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0]
        tickers.extend(t.strip() for t in line.split(",") if t.strip())
    return tickers


def canonical_tickers(raw: list[str]) -> list[str]:
    """Canonical symbols in their given order, each once."""
    return list(dict.fromkeys(parse_ticker(t) for t in raw))


def fetch_screen(name: str, count: int, screen=None) -> list[Candidate]:
    """The top ``count`` results of a Yahoo predefined screen."""
    if name not in SCREENS:
        raise ValueError(f"unknown screen {name!r}; see --list-screens")
    if screen is None:
        import yfinance

        screen = yfinance.screen
    quotes = screen(name, count=count).get("quotes", [])
    return [
        Candidate(
            symbol=q["symbol"],
            name=q.get("shortName") or q.get("longName") or "",
            price=q.get("regularMarketPrice"),
            change_pct=q.get("regularMarketChangePercent"),
            market_cap=q.get("marketCap"),
        )
        for q in quotes
        if q.get("symbol")
    ][:count]


def analyze_all(tickers, date, analysts, config, graph_factory=None, progress=None) -> list[Result]:
    """Run the full pipeline on each ticker; a failure is recorded, not raised."""
    if graph_factory is None:
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        graph_factory = TradingAgentsGraph
    graphs = {}   # one graph per asset type, reused across tickers like run_backtest does
    results = []
    for index, ticker in enumerate(tickers, 1):
        if progress:
            progress(index, len(tickers), ticker)
        asset_type = detect_asset_type(ticker)
        try:
            if asset_type not in graphs:
                selected = filter_analysts_for_asset_type(analysts, asset_type)
                graphs[asset_type] = graph_factory([a.value for a in selected], config=config)
            graph = graphs[asset_type]
            state, _ = graph.propagate(ticker, date, asset_type.value)
            report = graph.save_reports(state, ticker)
            results.append(Result(ticker, run_rating(state), report=report.parent / "complete_report.html"))
        except Exception as exc:  # one bad ticker or data outage must not end the scan
            results.append(Result(ticker, FAILED, error=f"{type(exc).__name__}: {exc}"))
    return results


def ranked(results: list[Result]) -> list[Result]:
    return sorted(results, key=lambda r: RANK.get(r.rating, len(RANK)))


def write_summary(results: list[Result], out_dir: Path, title: str) -> tuple[Path, Path]:
    """Write summary.md and summary.html (linking each report) into ``out_dir``."""
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = ranked(results)

    md = [f"# {title}", "", "| # | Ticker | Rating | Report |", "|---|---|---|---|"]
    for n, r in enumerate(rows, 1):
        detail = str(r.report) if r.report else (r.error or "")
        md.append(f"| {n} | {r.ticker} | {r.rating} | {detail} |")
    md_path = out_dir / "summary.md"
    md_path.write_text("\n".join(md) + "\n", encoding="utf-8")

    body = []
    for n, r in enumerate(rows, 1):
        if r.report:
            detail = f'<a href="{html.escape(r.report.as_uri())}">Open report</a>'
        else:
            detail = html.escape(r.error or "")
        body.append(
            f"<tr><td>{n}</td><td>{html.escape(r.ticker)}</td>"
            f'<td class="r-{html.escape(r.rating.lower())}">{html.escape(r.rating)}</td>'
            f"<td>{detail}</td></tr>"
        )
    html_path = out_dir / "summary.html"
    html_path.write_text(_HTML.format(title=html.escape(title), rows="\n".join(body)), encoding="utf-8")
    return md_path, html_path


_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  body {{ font: 15px/1.5 -apple-system, system-ui, sans-serif; margin: 2rem auto; max-width: 52rem; padding: 0 1rem; color: #1d1d1f; background: #fff; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ text-align: left; padding: .5rem .75rem; border-bottom: 1px solid #ddd; }}
  .r-buy, .r-overweight {{ color: #1a7f37; font-weight: 600; }}
  .r-underweight, .r-sell {{ color: #b42318; font-weight: 600; }}
  .r-review, .r-failed {{ color: #8a6d00; }}
  p.note {{ color: #666; font-size: 13px; }}
  @media (prefers-color-scheme: dark) {{ body {{ color: #eee; background: #161616; }} th, td {{ border-color: #333; }} }}
</style></head>
<body>
<h1>{title}</h1>
<table><thead><tr><th>#</th><th>Ticker</th><th>Rating</th><th>Report</th></tr></thead>
<tbody>
{rows}
</tbody></table>
<p class="note">Ratings are the agents' opinion for research, not financial advice. Read each report's reasoning before acting.</p>
</body></html>
"""


def _fmt_cap(value):
    if value is None:
        return ""
    for unit, size in (("T", 1e12), ("B", 1e9), ("M", 1e6)):
        if value >= size:
            return f"{value / size:.1f}{unit}"
    return f"{value:,.0f}"


def print_candidates(candidates: list[Candidate]) -> None:
    table = Table(title="Candidates")
    for column in ("#", "Ticker", "Name", "Price", "Change", "Market cap"):
        table.add_column(column)
    for n, c in enumerate(candidates, 1):
        table.add_row(
            str(n), c.symbol, c.name,
            "" if c.price is None else f"{c.price:,.2f}",
            "" if c.change_pct is None else f"{c.change_pct:+.2f}%",
            _fmt_cap(c.market_cap),
        )
    console.print(table)


def print_results(results: list[Result]) -> None:
    table = Table(title="Ranked ratings")
    for column in ("#", "Ticker", "Rating", "Report"):
        table.add_column(column)
    for n, r in enumerate(ranked(results), 1):
        table.add_row(str(n), r.ticker, r.rating, str(r.report) if r.report else (r.error or ""))
    console.print(table)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scan.sh",
        description="Run TradingAgents on a shortlist of tickers and rank the ratings.",
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--screen", help="Yahoo screen to take candidates from (see --list-screens)")
    source.add_argument("--tickers", help="Comma-separated tickers, e.g. AAPL,MSFT,NVDA")
    source.add_argument("--watchlist", type=Path, help="File with one ticker per line")
    parser.add_argument("--list-screens", action="store_true", help="List the available screens and exit")
    parser.add_argument("--top", type=int, default=5, help="Analyze at most this many tickers (default 5)")
    parser.add_argument("--date", default=None, help="Analysis date YYYY-MM-DD (default today)")
    parser.add_argument(
        "--analysts", default="market,sentiment,news,fundamentals",
        help="Comma-separated analysts (default: market,sentiment,news,fundamentals)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Show the candidates and exit; no AI calls")
    parser.add_argument("--yes", action="store_true", help="Run without asking for confirmation")
    parser.add_argument("--no-open", action="store_true", help="Don't open the summary in a browser")
    return parser


def main(argv=None, graph_factory=None, screen=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.list_screens:
        width = max(map(len, SCREENS))
        for name, description in SCREENS.items():
            console.print(f"  [bold]{name:<{width}}[/bold]  {description}")
        return 0
    if not (args.screen or args.tickers or args.watchlist):
        parser.error("give one of --screen, --tickers or --watchlist")
    if args.top < 1:
        parser.error("--top must be at least 1")

    try:
        date = parse_analysis_date(args.date or datetime.date.today().isoformat())
        analysts = parse_analysts(args.analysts, AssetType.STOCK)
        if args.screen:
            source = f"screen {args.screen}"
            try:
                candidates = fetch_screen(args.screen, args.top, screen=screen)
            except ValueError:
                raise
            except Exception as exc:  # network or Yahoo response errors, whatever the HTTP client
                raise OSError(f"could not fetch the {args.screen} screen from Yahoo Finance: {exc}") from exc
            tickers = canonical_tickers([c.symbol for c in candidates])
        else:
            source = "watchlist" if args.watchlist else "tickers"
            raw = read_watchlist(args.watchlist) if args.watchlist else args.tickers.split(",")
            tickers = canonical_tickers([t for t in raw if t.strip()])
            candidates = [Candidate(t) for t in tickers]
    except (ValueError, OSError) as exc:
        console.print(f"[red]{exc}[/red]")
        return 2

    tickers = tickers[: args.top]
    candidates = candidates[: args.top]
    if not tickers:
        console.print("[yellow]No tickers to analyze.[/yellow]")
        return 1

    print_candidates(candidates)
    if args.dry_run:
        return 0

    console.print(
        f"\n{len(tickers)} full analyses dated {date}, one after another. Each makes "
        "dozens of AI calls and takes several minutes."
    )
    if not args.yes:
        if not sys.stdin.isatty():
            console.print("[red]Not running without --yes when there is no terminal to confirm.[/red]")
            return 2
        if input("Continue? [y/N] ").strip().lower() not in ("y", "yes"):
            return 1

    from tradingagents.default_config import DEFAULT_CONFIG

    config = DEFAULT_CONFIG.copy()

    def progress(index, total, ticker):
        console.rule(f"[{index}/{total}] {ticker}")

    results = analyze_all(tickers, date, analysts, config, graph_factory=graph_factory, progress=progress)

    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(config["results_dir"]) / "scans" / stamp
    title = f"TradingAgents scan: {source}, {date}"
    md_path, html_path = write_summary(results, out_dir, title)

    console.print()
    print_results(results)
    console.print(f"\nSummary: {html_path}\n         {md_path}")
    if not args.no_open and sys.platform == "darwin":
        subprocess.run(["open", str(html_path)], check=False)
    return 0 if any(r.rating != FAILED for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
