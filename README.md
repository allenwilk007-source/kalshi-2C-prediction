# Course climate model vs Kalshi's 2 °C market

Goal: use the Carbon Trading course model (Kaya → carbon cycle → temperature) to
estimate P(world passes 2 °C before 2050), compare it with the Kalshi price, and
analyse how the contract could work as a hedge.

## Quick start: the dashboard

```bash
cd climate_kalshi
python serve.py
```

This opens **http://127.0.0.1:8000** in your browser and shows every result and chart. Nothing to
install: it uses Python's built-in web server and is only reachable from your own computer.

- **First time,** or if any results are missing, it runs the whole pipeline automatically. That takes
  about 3 minutes; the page shows each step's progress.
- **"Refresh data & re-run"** fetches the latest Kalshi prices and temperature data, then re-runs:
  `market.py` → `validate.py` → `phase2.py` … `phase7.py` → `phase9.py`.
- **Top of the page:** "Kalshi says vs our model says", then a table of every live Kalshi climate
  market the model can price (Phase 7).
- **Explore panel:** choose the climate view and emissions path, and whether 2049 counts. It shows the
  model's P(Yes) against the market's range after fees.
- **What if? (Phase 8):** HW5 running live in the browser. Drag the 9 Kaya rates or the climate
  parameters and the temperature path and P(2 °C) update instantly.
- **Options:** `python serve.py --run` forces a fresh run on start; `--port 8050` uses another port;
  `--no-browser` skips opening a browser. Stop the server with Ctrl+C.

Files: `serve.py` (server and pipeline runner) and `site/index.html` (the page). The last run's step
log is saved in `results/pipeline.json`.

## Files

| File | What it does |
|---|---|
| `extract_inputs.py` | Reads the HW5 sample-answer workbook once → `data/hw5_inputs.json` (historical emissions 1750–2020, UN population 2021–2100, 2020 Kaya base values) |
| `model.py` | Vectorised Python port of the workbook. `run(Params())` returns emissions, ppm, forcing and temperature 1750–2100; any parameter can be an array for Monte Carlo |
| `validate.py` | Compares every year of all four HW5 sheets (cols B, H, L, M). Current result: **PASS, worst relative error 7e-16** |

```bash
python extract_inputs.py
python validate.py
python model.py
```

Deterministic results (temperature measured from 1850):

| Sheet | 2050 | 2100 | First year ≥ 2 °C |
|---|---|---|---|
| Hw5 template | 2.14 | 4.60 | 2047 |
| scenario 1 hw5 | 2.16 | 5.00 | 2046 |
| scenario 2 - hw5 | 2.07 | 3.82 | 2048 |
| scenario 3 - hw5 (rich −3 %/yr, i.e. assignment Scenario 4) | 1.92 | 2.46 | 2055 |

Parameter 2 (1.15) implies an equilibrium climate sensitivity of 4.26 °C per CO₂ doubling,
which sits at the high end of the IPCC AR6 likely range (2.5–4 °C).

## The contract: `KXWARMING-50` (checked 2026-11-08 via Kalshi's public API)

- **Question:** "Will the world pass 2 degrees Celsius over pre-industrial levels before 2050?"
- **Rule:** Yes if the **annual** global mean surface temperature anomaly is **≥ +2.0 °C vs the
  1850–1900 average in any single calendar year** before 1 Jan 2050, i.e. 2049 or earlier.
- **Needs at least 2 of 4 sources:** NASA GISS, NOAA NCEI, Berkeley Earth, HadCRUT.
  In practice this means the **second-highest** dataset has to reach 2.0 °C.
- **Closes:** 1 Jan 2050, or **early as soon as the event happens**.
- **Book at check:** Yes bid **$0.65** / ask **$0.69**, last trade $0.69. Lifetime volume about
  21.6K contracts, open interest about 4.0K, **zero volume in the last 24 h**. This is a thin market.
- **Fees:** quadratic (Kalshi's standard ∝ P·(1−P) schedule).

### What this means for the modelling

1. **Single year, not a 20-year mean.** The model has to simulate year-to-year noise
   (El Niño and similar), not just the smooth trend.
2. **Baseline.** GISS (1951–80) and NCEI (20th century) don't publish a native 1850–1900
   anomaly, so each dataset has to be re-baselined. The model's own zero is 1850.
3. **"2 of 4".** The datasets differ by about 0.05–0.1 °C. Model each one's offset, or
   at least haircut the threshold.
4. **Early close.** Yes pays as soon as the threshold is hit, which shortens the
   capital lock-up on Yes paths. That matters when turning the price into a probability.

## Phase 2: observations, calibration, noise, and the 2-of-4 rule

```bash
python observations.py   # downloads the 4 datasets once into data/obs/raw (manifest has URL + SHA-256)
python test_phase2.py    # 9 plain-Python tests
python phase2.py         # results table, sensitivities, back-test, figures/, results/phase2.json
```

| File | What it does |
|---|---|
| `observations.py` | Downloads GISS, NOAA, Berkeley (air column) and HadCRUT 5.1.0.0. Keeps only complete calendar years and re-baselines to 1850–1900. GISS starts in 1880, so it is aligned to the other three over 1880–1900 |
| `calibrate.py` | Re-baselines the model and computes residuals. Version B refits p2 (and p1 if a likelihood-ratio test supports it) by grid MLE with AR(1) errors over 1880–2025 |
| `noise.py` | AR(1) fit, dataset offsets δₖ and noise τₖ, path simulation, and the contract rule (second-highest dataset, rounded half up to 0.01, ≥ 2.00, any year ≤ 2049) |
| `phase2.py` | Runs it all: 4 variants × 100,000 paths, 5 sensitivities, a back-test (fit to 1999, simulate 2000–2025), and 6 figures |

Data notes (downloaded 2026-11-08):
- **Berkeley** has no 2025 value yet; the summary file its data page links stops at 2024.
- **HadCRUT 5.0.2.0** stops at Feb 2025, so I used 5.1.0.0.
- **2024 on the 1850–1900 baseline:** GISS 1.47, NOAA 1.42, Berkeley 1.62, HadCRUT 1.53.

### Results (Kaya path fixed at the HW5 template)

| Variant | p2 | ECS | P(Yes by 2049) | Median first year | 10–90 % |
|---|---|---|---|---|---|
| A course model | 1.15 | 4.26 | **0.978** | 2045 | 2041–2048 |
| A + emissions gap filled | 1.15 | 4.26 | 0.992 | 2044 | 2040–2047 |
| B fitted | 1.23 | 4.56 | **1.000** | 2042 | 2038–2045 |
| B + emissions gap filled | 1.23 | 4.56 | 1.000 | 2041 | 2038–2044 |
| Kalshi `KXWARMING-50` | | | 0.65–0.69 | | |

- **Noise:** AR(1) with φ ≈ 0.53 and σ ≈ 0.099 °C. Excess kurtosis is −0.7, so Normal shocks; Student-t makes no difference.
- **Dataset offsets** vs the 4-dataset mean: Berkeley +0.107, HadCRUT +0.038, GISS −0.057, NOAA −0.087. HadCRUT is usually the second-highest, so the common signal needs to reach about 1.96 °C.
- **Sensitivities** (GISS baseline method, Berkeley water column, offset window, volcano masking, t-shocks): A ranges 0.958–0.981, B 0.996–1.000. The Berkeley water column has the biggest effect.
- **Resolution wording matters:** on the same A paths, "any 1 dataset" gives 0.998, "4-dataset mean" 0.936, and a 20-year mean 0.000.
- **Back-test** (fit to 1999, simulate 2000–2025):
  - **A:** 92 % of observed years fall inside the 5–95 % band. The model runs about 0.08 °C cool over 2016–25 (simulated mean 1.17 vs observed 1.25).
  - **B:** 100 % coverage, and the 2016–25 mean is spot on (1.25).
  - **Both:** record-year counts and the spread of annual changes match history.

**Why the probability is so much higher than the market's:** Phase 2 holds the economic path at the HW5
template, where emissions keep climbing (43 Gt CO₂ in 2025, 72 Gt in 2049). The course model's
sensitivity (ECS 4.26) also sits at the high end of the IPCC range. On that single path the
smooth model already crosses 2 °C in 2047, and noise only brings the crossing forward. These numbers are
therefore **conditional on the HW5 scenario**. Phase 3 replaces the single path with distributions
over emissions and climate sensitivity, which is where the real disagreement with the market will be
tested.

## Phase 3: uncertainty in emissions and climate response

```bash
python test_phase3.py    # 8 plain-Python tests (incl. point-mass reproduces Phase 2's 0.978)
python phase3.py         # tables, diagnostics, sensitivities, figures/p3_*.png, results/phase3.json
```

| File | What it does |
|---|---|
| `priors.py` | Kaya prior (HW5 template rates ± the workbook's own decade-to-decade sd); weights from actual 2019→24 emissions growth; the (p1, p2) climate grid with an IPCC AR6 ECS prior (very likely 2–5 °C) and a 1880–2020 AR(1) likelihood; tempering by bisection |
| `scenarios.py` | Actual 2021–24 emissions (OWID/Global Carbon Budget ratios on the course's Kaya 2019 level), then four paths taken from AR6 Box SPM.1's descriptions: falling (SSP1-2.6-like), flat (2-4.5), rising (3-7.0), doubling (5-8.5) |
| `phase3.py` | 20,000 parameter draws × 5 noise paths per cell, for 2 climate variants × 7 emission specs, plus sensitivities and 7 figures |

**Two climate variants:**
- **History-fit:** the course model fitted to 1880–2020 (prior × likelihood). Under the Flat path it
  gives 2041–60 = 2.02 °C and 2021–40 = 1.49 °C; AR6 SSP2-4.5 says 2.0 and 1.5. The centres match,
  but the range [1.92–2.13] is much narrower than AR6's 1.6–2.5, because a CO₂-only model can't
  express aerosol uncertainty.
- **IPCC-calibrated:** the likelihood is tempered (T = 11) so the 2041–60 spread matches AR6's,
  net of the part already observed (target width 0.67). This gives 1.94 [1.59–2.26], ECS 3.3 [2.3–4.9].

**Anchoring (a change made during implementation):** every draw continues from its own 2006–2025
average miss against observations, not its 1880–2020 average. Without this, draws that fit history
poorly started at today's temperature and then drifted back toward a curve up to about 0.2 °C off.
In the IPCC variant that drift lowered P(Yes) artificially. With anchoring, the median contract
reading rises smoothly: 1.43 (2026) → 1.50 (2030) → 1.76 (2040) → 2.00 (2049).

### Results: P(Yes by 2049), weighted Kaya = headline

| Emissions | History-fit | IPCC-calibrated |
|---|---|---|
| HW5 template | 0.983 | 0.742 |
| Kaya randomised, unweighted | 0.944 | 0.730 |
| **Kaya randomised + 2019–24 weighting** | **0.926** | **0.666** |
| Falling (SSP1-2.6-like) | 0.594 | 0.436 |
| Flat (SSP2-4.5-like) | 0.848 | 0.591 |
| Rising (SSP3-7.0-like) | 0.915 | 0.647 |
| Doubling (SSP5-8.5-like) | 0.984 | 0.744 |
| **Kalshi bid / ask** | **0.65 / 0.69** | |

Monte Carlo standard errors are ≤ 0.003. The median first year is 2043–2046 in every cell.

- **Weighting to real emissions** brings 2049 emissions down from the template's 71.6 Gt CO₂ to a
  weighted median of 53.9 [42.1–71.8]. ESS is 7,028 of 20,000. The weight's tolerance barely matters
  (0.663–0.682 IPCC).
- **Sensitivities (IPCC variant):** land-use gap filled 0.721. With the full AR6 width (no
  "already observed" adjustment) P(Yes) is 0.530, but even an unconstrained prior only reaches a width
  of 0.83, not 0.90, so that case is flagged.
- **What drives it:** the climate's warming rate dominates. Model warming 2025→49, bottom vs top
  quintile, moves P(Yes) from 0.18 to 1.00 in the IPCC variant. Emissions move it from 0.61 to 0.71.
  Individual Kaya rates matter less than ±0.04.

**Limitation:** once weighted to 2019–24, the randomised Kaya model almost never produces falling
emissions (5th percentile ≈ 42 Gt in 2049). Decade variability since 1960 contains no policy-driven
decline, so that world is covered only by the Falling scenario.

### Reading it against the market
- **The course model as fitted to history** says about 0.93, well above the 0.65–0.69 price.
- **With uncertainty calibrated to the IPCC,** it says about 0.67, inside the bid–ask.

So the "disagreement" in Phase 2 came almost entirely from how confident you are about the
climate's warming rate. The market is priced roughly like an IPCC-spread view with emissions somewhere
between Flat and Rising. Phase 4 still needs to convert the price into a probability (fees, spread,
24 years of locked capital, early close) before calling anything mispriced.

## Phase 4: what probability the price implies

```bash
python market.py         # new public snapshot -> data/market/<UTC>/ (no login; API keys not needed)
python test_phase4.py    # 8 plain-Python tests (fee schedule, book walking, implied q, band)
python phase4.py         # tables, figures/p4_*.png, results/phase4.json
```

| File | What it does |
|---|---|
| `market.py` | Public Kalshi market, order book and trade history, plus Treasury nominal/real curves; `fee()` (taker fee = ⌈0.07·C·P·(1−P)⌉ to the cent), `walk_book()`, daily VWAP |
| `pricing.py` | Payment timing (Yes paid ~mid-Jan after the qualifying year; No at 2050 expiry), discount factors for a carry rate δ, implied q*, the trading band, each side's expected excess return |
| `phase4.py` | Reuses `phase3.run_cell` (same 20,000 × 5 paths) for 10 model cells |

**Inputs (snapshot 2026-11-09 00:11 UTC):**
- **Quote:** Yes 0.65/0.69.
- **Kalshi APY:** 3.50 % (variable) on cash and positions.
- **Treasuries:** T-bill 4.02 %, 20-yr 5.29 %.
- **Payment timing:** Yes pays on average 17.7 yrs from now; No pays in 23.2 yrs.

**Implied probability** (the belief at which both sides earn the same expected return):

| Carry δ | Rate | Bid | Mid | Ask |
|---|---|---|---|---|
| 0, vs cash on Kalshi | 0 % | 0.650 | **0.670** | 0.690 |
| T-bill − Kalshi APY | 0.52 % | 0.643 | **0.664** | 0.684 |
| 20-yr − Kalshi APY | 1.79 % | 0.627 | 0.647 | 0.668 |
| T-bill, no APY | 4.02 % | 0.595 | 0.616 | 0.638 |
| 20-yr, no APY | 5.29 % | 0.576 | 0.597 | 0.619 |

**Trading band after fees and spread** (top of book, 10 contracts: 70.5¢ for Yes, 36.6¢ for No):
- **δ = 0:** **[0.634, 0.705]**. 100 contracts widens it to [0.626, 0.720]; a 5 % platform haircut to [0.615, 0.742].
- **δ = 0.52 %:** [0.587, 0.773].
- **Without Kalshi's APY:** at 4–5 % carry the band runs past 0 and 1, so almost no belief makes either side worth more than T-bills. Long-dated contracts like this only work because Kalshi pays interest on positions.

**Model vs market** (δ = 0, top of book):

| Model cell | P(≤ 2049) | P(≤ 2048) | vs band | Yes / No expected excess return |
|---|---|---|---|---|
| **IPCC-calibrated, weighted Kaya** | **0.666** | 0.617 | **inside** | −0.3 % / −0.4 % per yr |
| IPCC-calibrated, Flat | 0.591 | 0.539 | below | −1.0 % / +0.5 % |
| IPCC-calibrated, Rising | 0.647 | 0.596 | inside | −0.5 % / −0.2 % |
| IPCC-calibrated, Doubling | 0.744 | 0.698 | above | +0.3 % / −1.5 % |
| IPCC-calibrated, Falling | 0.436 | 0.392 | below | −2.6 % / +1.9 % |
| **History-fit, weighted Kaya** | **0.926** | 0.879 | **above** | +1.5 % / −6.7 % per yr |
| History-fit, Flat | 0.848 | 0.778 | above | +1.0 % / −3.7 % |
| History-fit, Falling | 0.594 | 0.521 | below | −0.9 % / +0.5 % |

These are model-vs-market comparisons, not recommendations.

**What Phase 4 adds:**
1. **Under the IPCC-calibrated view the market looks fairly priced.** 0.666 sits inside the
   0.634–0.705 band, and both sides expect to slightly underperform cash on Kalshi.
2. **Even the strongest disagreement is worth little per year.** The history-fit view (0.93 vs 0.67)
   is worth only about +1.5 %/yr on Yes, because the payoff is 18 years away.
3. **The 2049 timing quirk is worth about 5 points.** Expiry is 2050-01-08, but annual values usually
   publish mid-January. If 2049 can't count, the IPCC headline falls from 0.666 to 0.617.
4. **The price is set by very little money.**
   - The public API returns trades back to 2 Sep 2026 only: 4,758 of 21,615 lifetime contracts.
   - At **15:00:48 UTC on 22 Sep 2026** a single order bought No across 29 levels, sweeping Yes bids
     from 0.76 down to 0.03: **2,545 contracts for $1,344**, over half the volume in that history.
   - The price had traded at about 0.74–0.84 before the sweep and has held at about 0.65–0.69 since.
   - So one trader's roughly $1.3K order moved the market's "probability" about 10 points.

**Risk premium (interpretation):** Yes pays in a fast-warming world. If that world is economically
worse, Yes works as insurance and can trade above the true probability, so the quote is a
risk-neutral number. Phase 5 picks this up.

## Phase 5: 2026 nowcast, and how well the contract hedges climate damages

```bash
python test_phase5.py    # 8 plain-Python tests
python phase5.py         # nowcast, cross-check, updated P(Yes), hedge analysis; figures/p5_*.png, results/phase5.json
```

| File | What it does |
|---|---|
| `nowcast.py` | Monthly GISS/NOAA/HadCRUT plus Copernicus ERA5 daily (Climate Pulse). Each unpublished 2026 month is filled by an ERA5 bridge regression (1991–2025) with AR(1), cross-dataset-correlated errors; a partial November gets extra variance, and December is an AR(1) forecast. Also: back-test, `KXGTEMP-26` probability, El Niño momentum fit |
| `hedge.py` | Damage coefficient from the course SCC spreadsheet (`Impact` at 2.5 °C, Tol weights), quadratic damages, minimum-variance hedge, book capacity |
| `phase5.py` | Runs it all; P(Yes) cells now simulate 2027–2049 from the 2026 nowcast state |

Changes to earlier code (Phase 3 output verified identical, 0 differences): `noise.simulate(first_shift=…)`,
`phase3.run_draws(start=…)`, and `market.fetch` also saves `KXGTEMP-26`.

### A. Nowcast (data to 6 Nov 2026)
- **Monthly data available:** GISS and NOAA through September, HadCRUT through July. ERA5 has
  October at +0.90 °C and 1–6 November at +1.11 °C (vs 1991–2020).
- **2026 annual, 1850–1900 basis:** GISS 1.51, NOAA 1.43, HadCRUT 1.55. Common signal **1.53 ± 0.03**,
  up from 1.39 in 2025.
- **Back-test** (2023–25, using only data known on about 8 November each year): all 9 dataset-years
  within ±2 sd, but misses were 1.27× the stated sd and shared a sign across datasets. So bridge errors
  now share a component (correlation 0.72), and the predictive spread is widened ×1.27. That brings the
  back-test root-mean-square z-score to 1.00.
- **Cross-check against `KXGTEMP-26`** (GISS 2026 above 1.28 and above 2025): **model 0.883 vs market
  0.819/0.838**, a gap of +5.5 points.
- **El Niño momentum** (1960–2025): r(Y+1) = 0.29·r(Y) + 0.66·(Q4 − annual)(Y), t = 5.4, so it's used for
  the 2026→2027 step. Late 2026 runs +0.26 °C above the 2026 average, which keeps 2027 warm: median
  common signal 1.59, against 1.49 without momentum.

### P(KXWARMING-50 = Yes): 2025 start → 2026 nowcast start
Band after costs at the 2026-11-09 snapshot (Yes 0.65/0.70): [0.634, 0.715].

| Emissions | History-fit | IPCC-calibrated | IPCC, if 2049 can't count | IPCC vs band |
|---|---|---|---|---|
| **Kaya + 2019–24 weighting** | 0.926 → 0.927 | **0.666 → 0.672** | 0.622 | inside |
| Falling (SSP1-2.6-like) | 0.594 → 0.595 | 0.436 → 0.439 | 0.395 | below |
| Flat (SSP2-4.5-like) | 0.848 → 0.848 | 0.591 → 0.594 | 0.542 | below |
| Rising (SSP3-7.0-like) | 0.915 → 0.914 | 0.647 → 0.649 | 0.598 | inside |
| Doubling (SSP5-8.5-like) | 0.984 → 0.984 | 0.744 → 0.747 | 0.703 | above |

A record-warm 2026 barely moves a contract that will be decided in the 2040s. The 2026 anomaly
(+0.19 °C above trend) fades within a few years; only the trend reaches 2 °C.

During implementation I caught a double-count. The first momentum version added the Q4 term on top of
each draw's own persistence, which gave 0.684. The consistent version replaces the first year's
persistence with the momentum model.

### B. Hedging a hypothetical climate-damage exposure
- **Exposure:** income that falls with global damages, D(T) = a·T².
- **Damage coefficient:** from the SCC spreadsheet, a weighted median a = 0.242 %/°C²
  (−1.51 % at 2.5 °C; 5–95 %: −4.65 % to +0.50 %).
- **Loss per $1M of income in 2049:** a·(T₂₀₄₉² − T₂₀₂₆²).

| IPCC headline, per $1M income | Hedge effectiveness R² | Loss sd before → after |
|---|---|---|
| Linear temperature swap, damage coefficient known | 0.980 | $2,465 → $351 |
| Linear temperature swap, damage coefficient uncertain | 0.063 | $15,401 → $14,910 |
| `KXWARMING-50` Yes, damage coefficient known | 0.417 | $2,465 → $1,883 |
| **`KXWARMING-50` Yes, damage coefficient uncertain** | **0.028** | $15,401 → $15,182 |

**What this shows:**
1. **The binary 2 °C threshold throws away more than half of the temperature risk** a linear
   instrument could remove (R² 0.42 vs 0.98).
2. **Uncertainty about how much warming costs** (the spread of `Impact` across the literature)
   swamps temperature uncertainty. No temperature contract can hedge it, which cuts even a perfect
   temperature hedge to R² 0.06.
3. **The minimum-variance hedge is about 5,500 contracts per $1M of income,** but the visible book
   holds only 515 contracts at ≤ 0.71 and 967 at ≤ 0.76. That's enough for about **$0.1–0.2M** of
   income. Expected cost is +$237 per $1M under the IPCC view (−$721 under history-fit, where Yes
   looks cheap).
4. **Under the history-fit view it hedges even less** (R² 0.003), because Yes is nearly certain and
   so carries almost no information about how bad the damage will be.

So, as a hedge for real climate-damage exposure, this contract is too binary and too thin, and
damage-function uncertainty dominates anyway. That's analysis of a hypothetical exposure, not a
recommendation.

## Still to do

- [x] Phase 2: calibrate to observed annual temperatures, fit an AR(1) noise term, handle baselines
- [x] Phase 3: Monte Carlo over Kaya rates and climate response (+ noise) → P(Yes)
- [x] Phase 4: price → implied probability (fees, spread, time value, early close)
- [x] Phase 5: 2026 nowcast + `KXGTEMP-26` check; climate-damage hedge analysis
- [x] Phase 6: social cost of carbon from the class model vs Tol's database
- [x] Phase 7: scanner of every modelable Kalshi climate market
- [x] Phase 8: in-browser what-if model
- [x] Phase 9: market history and news test

## Phase 6: the social cost of carbon from the class model

`scc.py`, `phase6.py`, `test_phase6.py` (6 tests).

**Method:**
- Extend the class model to 2300: after 2100, population is flat, income per person grows 1 %/yr,
  and emissions fall linearly to zero by 2200. The extended model reproduces `run()` exactly to 2100.
- Add 1 GtC in 2027 and follow the extra warming.
- Damages: D = a·T² with a from the SCC spreadsheet's `Impact` column, applied to Kaya GDP.
- Discount with Ramsey (ρ + 1.4·g) or constant rates.
- 4,000 draws per climate view, with weighted Kaya draws and random damage coefficients.

| Discounting | Class model, IPCC view: median $/tC [5–95 %] | Tol database: median / mean |
|---|---|---|
| ρ 0 % | 205 [−41–852] | 860 / 1,438 |
| ρ 1 % | 89 [−17–363] | 151 / 311 |
| **ρ 1.5 %** | **66 [−12–270]** (≈ $18/tCO₂) | 143 / 213 |
| ρ 3 % | 34 [−6–135] | 29 / 53 |
| constant 3 % | 152 [−22–844] | |

**What it shows:**
- **Same order as the literature at 3 %,** but well below its long tail at low discount rates.
- **The damage coefficient explains 77 % of the spread** (96 % in the history view), the same
  finding as Phase 5's hedge analysis.
- **Worlds whose trend crosses 2 °C by 2049** have a median SCC of $84 vs $50/tC.
- **Sensitivities at ρ 1.5 %:** η = 1 gives 108; η = 2 gives 37; counting damages only to 2100 gives 48.
- About 6 % of draws are negative, because a few studies find net benefits from warming.

## Phase 7: every Kalshi climate market

`scanner.py`, `phase7.py`, `test_phase7.py` (5 tests).

**Coverage:** 22 live contracts across 5 series: `KXWARMING`, `KXGTEMP`, `KXHMONTH`,
`KXHMONTHRANGE` and `KXCO2LEVEL`. Each comes from the public order book; strikes are read from the
API (`strike_type`, `floor_strike`, `cap_strike`).
- **Temperature contracts:** the 2026 nowcast, with ERA5-bridged monthly draws for NOAA.
- **CO₂ contracts:** the class carbon cycle (weighted Kaya draws) mapped onto Mauna Loa
  (MLO = 49.9 + 0.891 × model ppm), plus:
  - MLO's seasonal cycle and AR(1) noise
  - the El Niño effect on growth (+2.8 ppm/yr per +1 °C anomaly, fitted 1980–2020)
  - a random-walk trend term calibrated so the forecast spread matches history at 12/24/36 months
    (model 0.64/0.87/1.05 ppm vs historical 0.74/0.90/0.99)

**Findings:**
- **Most temperature contracts agree** with the market after fees.
- **CO₂ ≥ 445/450/455/460 before 2030:** the model gives about 0–1.5 % against the market's 5–24 %,
  the largest disagreements. Reaching them needs about 4 ppm/yr of growth, which has never
  happened.
- **CO₂ ≥ 440:** 80 % on monthly means, 97 % on daily, vs market 78–86 %. The rule doesn't say
  which reading counts.
- **`KXGTEMP-27` has the same rule text as `KXGTEMP-26`** (both "2026 hottest year") but trades at a
  different price.

## Phase 8: what-if model in the browser

`site/model.js` is a JavaScript port of `model.py` (same equations and order of operations) with a
4,000–8,000-path Monte Carlo of the contract (anchored, AR(1), 2-of-4, rounding). It loads
`/api/model-inputs` and `results/slider_context.json` (written by Phase 5).

**Checked:**
- Temperature path vs Python: **maximum difference 0** over 1750–2100.
- HW5-template P(Yes): JS 0.993 vs Python 0.993.
- While dragging it runs 1,500 paths, then 8,000 when the slider is released.

## Phase 9: market history and news test

`history.py`, `phase9.py`, `test_phase9.py` (4 tests). Uses public daily candles from Kalshi.
- **`KXGTEMP-26`:** the nowcast is re-run for every day of 2026 using only that day's data (ERA5 two
  days behind; GISS/NOAA month m from the 15th of m+1; HadCRUT from the 15th of m+3).
  - The market priced a record 2026 months before the data showed it: about 80¢ by late August, while
    the data-only model stayed below 40 % until the very warm first days of November.
  - Daily moves barely line up; the best lead–lag correlation is about 0.15, with the market about
    3 days ahead.
  - Traders were most likely using El Niño forecasts; the model and market have agreed since November.
- **`KXWARMING-50`:** averaged 0.78 before the 22 Sep 2026 sweep and 0.67 after.
- **Tracking:** every pipeline run appends market vs model to `results/history.jsonl`, shown on the
  dashboard.

**Fix made during Phase 9:** the ERA5 monthly AR(1) used to forecast months not yet observed now
reverts to the warming trend, not the 1991–2025 average (which sits about 0.6 °C below today). This
moved the Phase 5 nowcast's P(2026 record) from 0.88 to 0.84, now in line with the market.

## Phase 10: temperature distributions across model versions

`phase10.py`, `test_phase10.py` (5 tests). On the dashboard: **Distributions** (interactive; toggle versions,
switch metric).

**Method:** 12 versions of the model each simulate 100,000 futures from the 2026 nowcast with Kalshi's
exact rule. For each, a weighted density is drawn of two quantities:
- **The highest contract reading 2027–2049** (second-highest dataset, rounded as published). The
  area right of 2.00 °C is exactly P(Yes); a test checks this equality in every version.
- **The 2049 temperature.**

Kalshi on 18 Nov 2026: 0.68/0.72, mid **70 %**, range after fees 66–74 %.

| Version | P(2 °C before 2050) | vs Kalshi | Peak reading, median [5–95 %] | 2049 temp | Shift to match |
|---|---|---|---|---|---|
| Class model as taught (HW5 economy) | 99.3 % | +29 | 2.20 [2.06–2.36] | 2.11 | −0.15 °C |
| Class settings, real-data emissions | 96.1 % | +26 | 2.15 [2.01–2.32] | 2.05 | −0.10 |
| Fitted to history | 92.7 % | +23 | 2.15 [1.98–2.34] | 2.05 | −0.09 |
| **IPCC-calibrated (headline)** | **67.1 %** | **−3 (agrees)** | 2.08 [1.75–2.43] | 1.97 | +0.02 |
| Blend 50/50 history + IPCC | 79.9 % | +10 | 2.12 [1.83–2.38] | 2.02 | −0.05 |
| IPCC, full AR6 width | 53.7 % | −16 | 2.02 [1.67–2.50] | 1.89 | +0.10 |
| IPCC + land-use emissions | 72.6 % | +3 (agrees) | 2.12 [1.77–2.48] | 2.01 | −0.01 |
| IPCC, falling / flat / rising / doubling emissions | 43.8 / 59.3 / 64.9 / 74.6 % | | | 1.83 / 1.91 / 1.95 / 2.03 | |

"Shift to match" is how far a version's whole distribution would have to slide for its probability to
equal Kalshi's mid; negative means the version runs hotter than the market. Every version's middle sits
at about 2.0–2.2 °C. They differ mainly in width: the narrow class-model versions put almost all of
their mass above 2.0, while the IPCC versions spread into slower-warming futures.

## Phase 11: hypothetical trade idea (class project)

`phase11.py`, `test_phase11.py` (5 tests). On the dashboard: **Trade idea**. **Hypothetical, for a class
presentation. Not investment advice; nothing places orders.**

**Our estimate:** an ensemble of the class model with its important settings changed.
- Climate sensitivity (Parameter 2): 1.00 / 1.15 / 1.30
- Adjustment speed (Parameter 1): 0.020 / 0.0256 / 0.032
- Emissions: HW5 economy / falling / flat / rising
- Missing land-use emissions: off / on

That's 72 versions × 4,000 futures, each from the 2026 nowcast with Kalshi's rule. The estimate is
the mean of the ensemble PDF: **80.8 %** that some year reaches 2 °C before 2050, against Kalshi's
70 % (18 Nov 2026). The PDF's mean peak reading is 2.14 °C. Sensitivity matters most (58 % → 98 %),
then adjustment speed, then emissions.

**Strategy A, value bet:** buy Yes at 0.72 (0.734 with the fee).
- Edge: +7.4 ¢ per contract.
- Hypothetical $1,000 (1,362 contracts): **+$362** if 2 °C is reached, **−$1,000** if not;
  expected **+$100** (about 0.55 %/yr over ~18 years, plus Kalshi's 3.5 % interest on the position).
- Kelly sizing: 28 % of a bankroll (half-Kelly 14 %).
- Reality checks: only ~500 contracts sit near the ask, and with the IPCC-calibrated estimate (67 %)
  the same trade has negative edge.

**Strategy B, hedge:** 70 % Yes on 2 °C + 30 % No on "CO₂ ≥ 445 ppm before 2030". The model gives
CO₂ ≥ 445 about 1.3 % vs the market's 20 %. High CO₂ goes with fast warming, so the No leg mostly
pays in the slow-warming worlds where the 2 °C bet loses.
- If 2 °C is not reached: **−$638** instead of −$1,000.
- Expected: +$127.

**Strategy C, arbitrage check:** `KXGTEMP-26` and `KXGTEMP-27` both ask whether 2026 is GISS's
record year. Buying Yes on one and No on the other pays exactly $1, so it's arbitrage whenever the
two cost less than $1 after fees. On 18 Nov 2026 they cost about $1.02–1.03, so there's no arbitrage;
the prices would need to drift 2–3 ¢ further apart (the dashboard shows the live figure). Risk: if Kalshi treats "-27" as a 2027 market, they
stop being the same bet.

## Phase 12: small regular trades (class project)

`phase12.py`, `test_phase12.py` (5 tests). On the dashboard: **Small trades**. **Hypothetical back-test on
Kalshi's public price history; not investment advice.**

**Setup:** $10 a week from listing (6 Jun 2025) to 18 Nov 2026, three methods, each valued under our
80.8 % and under the IPCC-calibrated 67.1 %.

| Method | Contracts (avg cost) | If 81 % | If 67 % | Sold today |
|---|---|---|---|---|
| Weekly buy at the ask (taker fee) | 731 (0.799) | +$6 | −$94 | −$98 |
| Weekly limit order, bid + 1 ¢ (no maker fee) | 691 (0.756) | +$36 | −$58 | −$63 |
| Spread capture, 10 contracts a side | 52 round trips | +$14 | +$12 | +$12 |

**Findings:**
- **Fees are rounded up per order,** so 1 contract pays 2 ¢ against 1.42 ¢ in a 100-contract order.
- **Going forward,** buying at the ask needs P > 73.5 % to break even, and limit orders need
  P > 69 %, right at the market.
- **Verdict:** small regular bets only pay if the narrow class-model view (81 %) is right. The
  IPCC-calibrated model agrees with the market, so on that view they lose slowly. The only edge
  that doesn't depend on who's right is spread capture: about $10 a year at these sizes, assuming
  fills that a thin market may not give.

`figures/p12_0_estimates.png` is the headline chart (Kalshi 70 % vs IPCC-calibrated 67 % vs ensemble
81 % vs history-fit 93 % vs class model 99 %), shown on the dashboard and in the presentation deck.
