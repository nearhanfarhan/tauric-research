#!/usr/bin/env bash
# Run a full TradingAgents analysis for one ticker and open the report.
#
#   bash scripts/analyze.sh NVDA              # analysis dated today
#   bash scripts/analyze.sh AAPL 2026-10-17   # analysis dated in the past
#
# Settings (provider, models, depth) come from .env, written by setup_mac.sh.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

if [[ $# -lt 1 ]]; then
    echo "Usage: bash scripts/analyze.sh TICKER [YYYY-MM-DD]" >&2
    exit 1
fi
TICKER="$(printf '%s' "$1" | tr '[:lower:]' '[:upper:]')"
DATE="${2:-$(date +%Y-%m-%d)}"
ANALYSTS="${ANALYSTS:-market,sentiment,news,fundamentals}"

if [[ ! -x .venv/bin/tradingagents ]]; then
    echo "TradingAgents is not installed yet. Run: bash scripts/setup_mac.sh" >&2
    exit 1
fi

REPORTS_DIR="${TRADINGAGENTS_RESULTS_DIR:-$HOME/.tradingagents/logs}/reports"
marker="$(mktemp)"

.venv/bin/tradingagents \
    --ticker "$TICKER" \
    --date "$DATE" \
    --analysts "$ANALYSTS" \
    --save --html --no-show

# Open the report this run just saved.
page="$(find "$REPORTS_DIR" -name complete_report.html -newer "$marker" 2>/dev/null | head -n 1 || true)"
rm -f "$marker"
if [[ -n "$page" ]]; then
    echo "Report: $page"
    if command -v open >/dev/null 2>&1; then
        open "$page"
    fi
fi
