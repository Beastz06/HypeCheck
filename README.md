# HypeCheck

**Is the buzz around a product backed by buyers who'll actually pay for it?**

HypeCheck is an agent that rates a consumer product the way an analyst rates a stock. It measures public attention, the stock's reaction, and what target buyers say they'd pay at the real price. Then it compares all three against a control product.

Built at *AI Hackathon: Hack the Unreachable* (Fordham Gabelli School of Business, 14 November 2026) for the **Investment Alpha** track: the gap between what's priced in and what key segments privately believe. Buyer research runs on [Flashpoint.AI](https://flashpoint.ai).

## Result: On (ONON) vs. Nike (NKE)

**Rating: IN LINE.** Gap +4 points vs. Nike, inside the ±15 band.

| Score | On (ONON) | Nike (NKE) |
| --- | --- | --- |
| Hype (0–100) | 0 | 0 |
| Market (0–100) | 47 | 52 |
| Wallet (0–80) | 11 | 15 |
| Hype − Wallet | −11 | −15 |
| Price tested | $160 (Cloudrunner 3) | $155 (Vomero 18) |

- **Attention is below last year's level for both.** On's Wikipedia views are at 0.88× and YouTube at 0.32×; Nike's are at 0.96× and 0.33×.
- **Buyers lean slightly to Nike.** At $160, 25 of 100 panelists would definitely (7) or probably (18) buy On. At $155, 38 of 100 would buy Nike (8 definitely, 30 probably).
- **The stock was flat.** On's share price moved −3.2% over 30 days (volume 1.99× normal); Nike's moved +2.3% (1.18×).

## How it works

One input (a product, a control product and their tickers), three signals and one rating.

| Signal | Question | Source | Formula |
| --- | --- | --- | --- |
| Hype | Has attention grown? | Wikipedia and YouTube views | Mean of the last 30 days ÷ median of the prior 12 months, per source, averaged. 1.0× scores 0; 3.0× scores 100. |
| Market | How did the stock react? | yfinance | 50 + 100 × 30-day price change, clipped to 0–100. Volume ratio shown alongside. |
| Wallet | Will target buyers pay the real price? | Flashpoint.AI survey, synthetic panel of 100 US runners aged 18–45 | 100 × (0.8 × "definitely would buy" + 0.3 × "probably would buy") ÷ respondents |
| Rating | Overhyped vs. the control? | | (Product Hype − Wallet) − (Control Hype − Wallet). Above +15 = OVERHYPED; below −15 = UNDER-THE-RADAR; otherwise IN LINE. |

Market is shown beside the rating but is not part of it. The stock is the market's reaction to the hype, which is the thing being tested, so including it would be circular.

## Backtest: GameStop, 30 days to 31 January 2021

| Measure | Value |
| --- | --- |
| Wikipedia attention vs. prior year | 27.2× |
| Share price, 30 days | +1,587% |
| Trading volume vs. normal | 14.4× |
| Hype / Market scores | 100 / 100 |

Three weeks later (19 February 2021) the stock was down 88%: $81.25 to $10.15, split-adjusted. This is a hindsight check, not a rating: the rating needs a Wallet score, and 2021 buyers can't be surveyed today.

## Run it

```bash
pip install requests yfinance
python hype_wallet.py      # pulls the signals, computes the scores, writes results.json
open dashboard.html        # renders results.json
```

Every API result is cached, so runs reproduce. `dashboard.html` also carries an embedded copy of the results, so it opens straight from the file.

## Files

| File | What it is |
| --- | --- |
| `hype_wallet.py` | Pulls Wikipedia, YouTube and stock data; computes Hype, Market, Wallet and the rating |
| `results.json` | The latest results (On vs. Nike, GameStop backtest) |
| `dashboard.html` | One-page research note: rating, scorecard, backtest |
| `AGENT_BUILD.md` | Build spec: formulas, Flashpoint survey brief, panel audience |
| `logos/` | Brand marks used on the dashboard |

## Data sources

| Need | Source | Cost |
| --- | --- | --- |
| Attention | Wikimedia Pageviews API, YouTube Data API | Free |
| Price and volume | yfinance | Free |
| Buyer intent | Flashpoint.AI survey and synthetic panel | Paid (the only paid step) |

## Limits

- **Wallet uses synthetic personas, not real buyers.** We haven't yet measured how closely they match real people for this category.
- **Stated intent overstates real buying.** The 0.8 / 0.3 weights are a rule of thumb, not a calibrated model.
- **Hype uses Wikipedia and YouTube only**, and it floors at 0 when attention is below last year's level.
- **Survey counts are entered by hand.** They come from the Flashpoint results page; the code doesn't call Flashpoint yet.
- **One product, one control and one backtest are a demonstration, not proof.** Nike's stock covers far more than running shoes.

## Next steps

1. Run the same survey on Flashpoint's human First Party Panel and compare it with the synthetic answers.
2. Calibrate the intent weights against real buying with Flashpoint Market Experiments.
3. Call Flashpoint's API from the agent, so one command runs the whole pipeline.
4. Add news volume, search trends and headline tone to Hype.
5. Rate a weekly watchlist of consumer products and alert when a rating changes.

*Not investment advice.*
