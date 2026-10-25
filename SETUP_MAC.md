# Running TradingAgents on your Mac

A plain-English guide to setting up and using TradingAgents on macOS (tested for
Monterey 12.x), with Google Gemini as the AI model. You don't need the Claude
desktop app, Homebrew, or admin rights. Everything runs in Terminal.

> **Read this first.** TradingAgents does **not** place trades or connect to a
> broker. It researches a stock and gives a rating (Buy / Overweight / Hold /
> Underweight / Sell) with its reasoning. You decide what to do and place any
> trades yourself. The authors built it for research, and its output is
> [not financial advice](https://tauric.ai/disclaimer/). AI models can be
> confidently wrong, so treat a report as one input among several.

## How it works

Each run analyzes one stock as of one date, using a team of AI agents set up
like a trading firm:

1. **Analysts** (they work at the same time)
   - **Market**: price history and technical indicators (moving averages, MACD, RSI, ...) from Yahoo Finance.
   - **Sentiment**: StockTwits and Reddit posts, plus headlines.
   - **News**: company and world news that could move the stock.
   - **Fundamentals**: financial statements from SEC filings (US companies) or Yahoo.
2. **Bull and Bear researchers** debate the analysts' reports. A **Research Manager** weighs the debate and decides which side is stronger.
3. A **Trader** turns that into a concrete plan.
4. **Aggressive, Neutral and Conservative risk analysts** argue over the plan.
5. A **Portfolio Manager** makes the final call and gives a rating with its reasoning.

Every decision is saved to a memory log (`~/.tradingagents/memory/`). On later
runs, TradingAgents checks how earlier calls actually turned out (return versus
the S&P 500 over 5 trading days). It feeds those lessons back to the Portfolio
Manager.

The market data is free and needs no account. The AI part runs on Google's
servers through your Gemini API key, so the Mac just runs a small Python program.

## One-time setup

### 1. Get a Gemini API key

1. Go to <https://aistudio.google.com/apikey> and sign in with a Google account.
2. Click **Create API key** and copy it. Keep it private, like a password.

The free tier is enough to try it out. It has rate and daily limits, so a full
analysis may be slow or stop partway when you hit them. For regular use, turn on
billing for the key in Google AI Studio. Each analysis makes dozens of model
calls. Check Google's current Gemini pricing to see what that costs on your plan.

### 2. Download this project

Open **Terminal** (Applications → Utilities → Terminal) and run:

```bash
cd ~
git clone -b claude/inspiring-gauss-i0jmy7 https://github.com/nearhanfarhan/tauric-research.git
cd tauric-research
```

- If macOS asks to install "command line developer tools", click **Install**, wait for it to finish, then run the `git clone` line again.
- If the repository is private, git asks for your GitHub username and password. For the password, paste a [personal access token](https://github.com/settings/tokens), not your account password.
- **No git?** On the GitHub page for this repository, switch to the `claude/inspiring-gauss-i0jmy7` branch and choose **Code → Download ZIP**. Unzip it, then in Terminal run `cd ` (with a space) and drag the unzipped folder onto the Terminal window. Press Enter.

### 3. Run the setup script

```bash
bash scripts/setup_mac.sh
```

The script does four things:
- Installs [uv](https://docs.astral.sh/uv/), a small Python installer, into `~/.local/bin`.
- Uses uv to download Python 3.13 into the project folder. Your system Python is left alone.
- Installs TradingAgents and its libraries into the project's `.venv` folder. This takes a few minutes.
- Asks for your Gemini key (nothing shows as you paste it), plus an optional name and email for SEC EDGAR. It saves your settings in a private `.env` file in the project folder.

The `.env` file is never uploaded to GitHub. You can run the script again at any
time. It only asks for what's missing.

## Analyzing a stock

```bash
cd ~/tauric-research
bash scripts/analyze.sh NVDA
```

- You see the agents work live. A run usually takes 5–15 minutes.
- When it finishes, the full report opens in your browser.
- Reports are saved in `~/.tradingagents/logs/reports/<TICKER>_<date-time>/`. `complete_report.html` is the easiest to read.

More examples:

```bash
bash scripts/analyze.sh AAPL 2026-10-17           # as if it were that date
ANALYSTS=market,news bash scripts/analyze.sh TSLA # fewer analysts: faster, cheaper
bash scripts/analyze.sh AZN.L                     # non-US: use Yahoo's suffix (.L London, .TO Toronto, ...)
bash scripts/analyze.sh BTC-USD                   # crypto
```

To use the menu-driven version, where you pick analysts, depth and models
step by step, run:

```bash
source .venv/bin/activate
tradingagents
```

### Reading the result

The final rating is one of:

| Rating | Meaning |
|---|---|
| **Buy** | Strong conviction to enter or add to a position |
| **Overweight** | Favorable; build or increase the position gradually |
| **Hold** | Keep current position; no action |
| **Underweight** | Reduce exposure or take partial profits |
| **Sell** | Exit or avoid |

Read the Portfolio Manager's reasoning and the bull/bear debate, not just the
label. The reasoning tells you *why*, and whether it fits your own view and risk
tolerance.

## Making it know what you own (optional)

By default the agents don't know your holdings. To size advice against your real
position, create a file such as `my_book.json`:

```json
{
  "cash": 25000.0,
  "currency": "USD",
  "positions": [{"ticker": "NVDA", "quantity": 120, "average_price": 150.0}]
}
```

Then run:

```bash
source .venv/bin/activate
tradingagents --portfolio my_book.json
```

## Tuning (optional)

Edit `.env` in the project folder with any text editor (`open -e .env`):

| Setting | What it does |
|---|---|
| `TRADINGAGENTS_DEEP_THINK_LLM=gemini-3.1-pro-preview` | Stronger model for the two manager agents (costs more) |
| `TRADINGAGENTS_QUICK_THINK_LLM=gemini-3.5-flash-lite` | Cheaper, faster model for the analysts and debaters |
| `TRADINGAGENTS_MAX_DEBATE_ROUNDS=2` / `TRADINGAGENTS_MAX_RISK_ROUNDS=2` | Longer debates: more thorough, slower, costlier |
| `FRED_API_KEY=...` | Adds US macro data; [free key](https://fred.stlouisfed.org/docs/api/api_key.html) |
| `TRADINGAGENTS_GOOGLE_THINKING_LEVEL=minimal` | Less model "thinking": faster and cheaper |

## Checking how well it decides (optional)

One rating says little about whether the system is any good. A backtest runs it
over many past dates and scores the calls against what the stock did next:

```bash
source .venv/bin/activate
tradingagents backtest NVDA,AAPL --start 2026-06-01 --end 2026-08-01 --every 7
```

This runs one full analysis per ticker per date, so it uses many API calls.

## Updating

```bash
cd ~/tauric-research
git pull
git pull https://github.com/TauricResearch/TradingAgents.git main   # newest upstream release
bash scripts/setup_mac.sh
```

## Troubleshooting

| Problem | Fix |
|---|---|
| `uv: command not found` after setup | Close and reopen Terminal, or run `export PATH="$HOME/.local/bin:$PATH"` |
| `API key not valid` | Re-copy the key from AI Studio and fix `GOOGLE_API_KEY=` in `.env` |
| `429` / `RESOURCE_EXHAUSTED` | Free-tier limit reached. Wait and retry, use fewer analysts, or enable billing |
| `TradingAgents is not installed yet` | Run `bash scripts/setup_mac.sh` from the project folder |
| A report says data was "withheld" | Expected for past dates where data wasn't public yet. The project avoids look-ahead |

More detail on every option is in [README.md](README.md).
