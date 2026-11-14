# Hype vs. Wallet — Agent Build Spec

Hand this file and `hype_wallet.py` to Claude Code. Goal: a working demo by 3:00 PM.

## What the agent does

Given a product, a control product and their tickers, it returns one verdict card:
is the attention on this product backed by buyers willing to pay for it?

| Score | Question it answers | Source |
|---|---|---|
| Hype (0–100) | How much has public attention grown? | Wikipedia pageviews, GDELT news volume, YouTube views |
| Market (0–100) | How have investors reacted? | yfinance price change and volume |
| Wallet (0–80) | Will the target buyer pay the real price? | Flashpoint.AI survey answered by a synthetic panel |

## Lineup

| Role | Product | Ticker | Wikipedia article | News query |
|---|---|---|---|---|
| Live demo | On running shoes | ONON | `On_(company)` (verify) | `"On Running"` |
| Control | Nike running shoes | NKE | `Nike,_Inc.` | `"Nike running"` |
| Backtest | GameStop, window ending 2021-01-31 | GME | `GameStop` | `GameStop` |

The backtest has Hype and Market only. Nobody can survey 2021 buyers today.

## Formulas

- **Trend ratio (per source):** mean of the last 30 days ÷ median of the 12 months before.
- **Hype:** average the ratios; 1.0 maps to 0 and 3.0 maps to 100 (`CAP` in the code).
- **Positive share:** Claude labels ~50 recent headlines; positive ÷ (positive + negative). Shown beside Hype, not folded in.
- **Market:** 50 + 100 × 30-day price change, clipped to 0–100. Show the volume ratio beside it.
- **Wallet:** 100 × (0.8 × "definitely would buy" + 0.3 × "probably would buy") ÷ respondents, at the real price.
- **Verdict:** (product Hype − Wallet) minus (control Hype − Wallet). Above +15 = OVERHYPED, below −15 = UNDER-THE-RADAR, else IN LINE.

## Flashpoint.AI steps

Auth: bearer token from the OAuth sign-in (lasts 24 hours). Ask a mentor how to copy it; set `FLASHPOINT_TOKEN`.

**Path A (fastest, do this first):** connect the MCP server to Claude Code and drive it in chat.

```
claude mcp add --transport http flashpoint https://api.flashpoint.ai/mcp
```

1. Ask for the survey using the brief below (tool: `tool_survey`).
2. Ask for the synthetic panel using the audience below, and have it take the survey (tool: `panel`).
3. Note the survey ID. The app reads results over REST:
   - `GET /api/v1/surveys/{id}/analytics/frequencies`
   - `POST /api/v1/surveys/{id}/analytics/crosstab` with `{"rowVariable": {"questionLabel": "Q3"}, "colVariable": {"questionLabel": "S2"}}`

**Path B (if time allows):** call the MCP tools from Python so the agent runs the survey itself.

```python
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

async with streamablehttp_client(
    "https://api.flashpoint.ai/mcp",
    headers={"Authorization": f"Bearer {TOKEN}"},
) as (read, write, _):
    async with ClientSession(read, write) as s:
        await s.initialize()
        print(await s.list_tools())   # read the argument names before calling anything
        # then: await s.call_tool("tool_survey", {...}) and await s.call_tool("panel", {...})
```

The argument names for `tool_survey` and `panel` are not in the docs excerpt we read. Print `list_tools()` first.
Do not use `generate_test_data`: it produces random answers, not personas.

### Survey brief (paste into `tool_survey`)

> Create a 2-minute consumer survey about running shoe brands. Replace the prices with the current retail prices.
>
> - S1. How often do you run or walk for exercise? (Daily / A few times a week / A few times a month / Rarely or never)
> - S2. Have you bought athletic shoes in the past 12 months? (Yes / No)
> - Q1. Which of these brands have you heard of? Select all. (On / Nike / Hoka / Brooks / Asics / None)
> - Q2. How interested are you in buying On running shoes? (1 Not at all – 5 Extremely)
> - Q3. On running shoes cost about $[ON_PRICE]. How likely are you to buy a pair in the next 12 months? (Definitely would / Probably would / Might or might not / Probably would not / Definitely would not)
> - Q4. How interested are you in buying Nike running shoes? (1–5)
> - Q5. Nike running shoes cost about $[NIKE_PRICE]. How likely are you to buy a pair in the next 12 months? (same 5-point scale)
> - Q6. Would you buy On running shoes at each price? Yes/No for each: $110, $140, $170, $200
> - Q7. Your next pair of running shoes will most likely be: (On / Nike / Hoka / Brooks / Asics / Other)
> - Q8. In a sentence, why would or wouldn't you buy On? (open text)
>
> Do not screen anyone out. Keep S1 and S2 for crosstabs.

### Synthetic panel audience (paste into `panel`)

> 100 US adults aged 18–45 who run or walk for exercise at least a few times a month and have bought athletic shoes in the past year. Mix of incomes, genders and regions. Have them take the survey.

If 100 is slow, run 50.

## App

One Streamlit page (`app.py`) that imports `hype_wallet.py`:

1. Inputs: product, control, tickers, Flashpoint survey ID. Pre-fill with On and Nike.
2. Verdict line at the top in plain words, e.g. "On: OVERHYPED relative to Nike". Use text labels, not color alone.
3. Three score tiles per product, side by side with the control.
4. Hype detail: ratio per source, a line chart of Wikipedia views, positive share.
5. Wallet detail: intent funnel (heard of → interested 4–5 → probably or definitely would buy) and the price ladder from Q6.
6. Backtest tab: GameStop Wikipedia views and price on one chart.
7. A short memo from Claude: verdict, the two strongest numbers, sample size, limits.
8. **Cache every API result to `cache/*.json`** and add a "use cached data" switch. Demo from cache.

## Build order

| Time | Task |
|---|---|
| 1:15–1:30 | Flashpoint token working; survey created; synthetic panel running |
| 1:15–1:45 | Run `python hype_wallet.py`; fix any response-shape errors; add the YouTube key if there is time |
| 1:45–2:30 | `app.py`: tiles, verdict, charts; Wallet from Flashpoint frequencies |
| 2:30–3:00 | Backtest tab, memo, cache, freeze |
| 3:00–3:30 | Push to a public GitHub repo, deck, rehearse |

## Cut order if behind

1. YouTube
2. Price ladder chart
3. Live calls in the demo (show cached results)

Never cut: the Flashpoint survey, the control comparison.

## Limits to state in the pitch

- Wallet comes from synthetic personas, not real buyers. Next step: validate against a human panel.
- Stated intent overstates real buying; the 0.8 / 0.3 weights are a rule of thumb.
- Trend ratios show attention growth, not its absolute level.
- One product and one control is a demonstration, not proof.
