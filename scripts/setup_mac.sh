#!/usr/bin/env bash
# One-time setup for TradingAgents on macOS, using Google Gemini as the LLM.
#
#   bash scripts/setup_mac.sh
#
# Safe to run again: it reuses the existing environment and .env, and only asks
# for what is still missing. Nothing needs admin rights or Homebrew.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

ENV_FILE="$REPO_DIR/.env"
QUICK_MODEL="gemini-3.8-flash"
DEEP_MODEL="gemini-3.8-flash"

say()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m%s\033[0m\n' "$*"; }

# Set KEY=VALUE in .env, replacing any existing or commented-out line for KEY.
set_env() {
    local key="$1" value="$2" tmp
    tmp="$(mktemp)"
    grep -vE "^#?[[:space:]]*${key}=" "$ENV_FILE" > "$tmp" || true
    printf '%s=%s\n' "$key" "$value" >> "$tmp"
    mv "$tmp" "$ENV_FILE"
    chmod 600 "$ENV_FILE"
}

# Current value of KEY in .env, or empty.
get_env() {
    grep -E "^${1}=" "$ENV_FILE" 2>/dev/null | tail -n 1 | cut -d= -f2- || true
}

if [[ "$(uname -s)" != "Darwin" && -z "${SETUP_ALLOW_NON_MAC:-}" ]]; then
    echo "This script is for macOS. On Linux, follow the Installation section of README.md." >&2
    exit 1
fi

# 1. uv: installs Python 3.13 and the dependencies into .venv, without touching the system Python.
say "Checking for uv (Python installer)"
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
if ! command -v uv >/dev/null 2>&1; then
    echo "Installing uv into ~/.local/bin ..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi
uv --version

# 2. Python environment and TradingAgents itself.
say "Creating the Python environment in .venv"
if [[ ! -x .venv/bin/python ]]; then
    uv venv --python 3.13 .venv
fi
say "Installing TradingAgents and its dependencies (takes a few minutes the first time)"
uv pip install --python .venv/bin/python .

# 3. .env with Gemini defaults. The CLI reads these, so a run asks no setup questions.
say "Writing settings to .env"
if [[ ! -f "$ENV_FILE" ]]; then
    cp .env.example "$ENV_FILE"
fi
set_env TRADINGAGENTS_LLM_PROVIDER google
[[ -n "$(get_env TRADINGAGENTS_QUICK_THINK_LLM)" ]] || set_env TRADINGAGENTS_QUICK_THINK_LLM "$QUICK_MODEL"
[[ -n "$(get_env TRADINGAGENTS_DEEP_THINK_LLM)" ]]  || set_env TRADINGAGENTS_DEEP_THINK_LLM "$DEEP_MODEL"
[[ -n "$(get_env TRADINGAGENTS_GOOGLE_THINKING_LEVEL)" ]] || set_env TRADINGAGENTS_GOOGLE_THINKING_LEVEL high
[[ -n "$(get_env TRADINGAGENTS_OUTPUT_LANGUAGE)" ]]   || set_env TRADINGAGENTS_OUTPUT_LANGUAGE English
[[ -n "$(get_env TRADINGAGENTS_MAX_DEBATE_ROUNDS)" ]] || set_env TRADINGAGENTS_MAX_DEBATE_ROUNDS 1
[[ -n "$(get_env TRADINGAGENTS_MAX_RISK_ROUNDS)" ]]   || set_env TRADINGAGENTS_MAX_RISK_ROUNDS 1
# Free-tier Gemini keys hit rate limits (HTTP 429); retry instead of aborting the run.
[[ -n "$(get_env TRADINGAGENTS_LLM_MAX_RETRIES)" ]]   || set_env TRADINGAGENTS_LLM_MAX_RETRIES 6

# 4. Gemini API key, typed hidden and stored only in .env (which git ignores).
if [[ -n "${GOOGLE_API_KEY:-}" && -z "$(get_env GOOGLE_API_KEY)" ]]; then
    set_env GOOGLE_API_KEY "$GOOGLE_API_KEY"
fi
if [[ -z "$(get_env GOOGLE_API_KEY)" ]]; then
    say "Gemini API key"
    echo "Create one at https://aistudio.google.com/apikey (sign in with a Google account),"
    echo "then paste it here. Nothing will show as you paste; press Enter when done."
    read -r -s -p "GOOGLE_API_KEY: " key
    echo
    if [[ -n "$key" ]]; then
        set_env GOOGLE_API_KEY "$key"
    else
        warn "No key entered. Add GOOGLE_API_KEY=... to .env, or run this script again."
    fi
fi

# 5. SEC EDGAR asks callers for a contact address; optional, a default is sent otherwise.
if [[ -z "$(get_env SEC_EDGAR_USER_AGENT)" && -t 0 ]]; then
    say "SEC contact (optional)"
    echo "SEC EDGAR, the source of company financials, asks for a name and email."
    read -r -p "Your name and email, e.g. 'Jane Doe jane@example.com' (Enter to skip): " ua
    if [[ -n "$ua" ]]; then
        set_env SEC_EDGAR_USER_AGENT "\"$ua\""
    fi
fi

# 6. Smoke check.
say "Checking the install"
.venv/bin/tradingagents --help >/dev/null
echo "TradingAgents is installed."
echo
echo "Analyze a stock:   bash scripts/analyze.sh NVDA"
echo "Interactive menu:  source .venv/bin/activate && tradingagents"
