#!/usr/bin/env bash
# Run TradingAgents on a shortlist (Yahoo screen or your own tickers) and rank the ratings.
#
#   bash scripts/scan.sh --list-screens
#   bash scripts/scan.sh --screen undervalued_large_caps --top 5 --dry-run
#   bash scripts/scan.sh --watchlist watchlist.txt
#
# Run with --help for every option.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

if [[ ! -x .venv/bin/python ]]; then
    echo "TradingAgents is not installed yet. Run: bash scripts/setup_mac.sh" >&2
    exit 1
fi

exec .venv/bin/python scripts/scan.py "$@"
