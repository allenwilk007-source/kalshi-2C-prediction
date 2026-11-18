# FECON 390 Final Project: Will the world hit a 2°C year before 2050? Our class model vs the Kalshi market

By: Allen Wilk

**Why did I do it:**

In class we built a climate model in Excel (HW2–HW5): the Kaya identity for emissions, a five-box carbon cycle, radiative forcing and a two-box temperature model. I wanted to know whether that homework model can say something useful about a real question that people are putting money on. Kalshi, a CFTC-regulated prediction market, lists a contract (KXWARMING-50) that pays $1 if any single calendar year before 2050 is at least 2.00°C warmer than the 1850–1900 average, and its price works as the crowd’s probability. A market and a model are opposite ways of forecasting: the market pools everything traders know but never explains itself, while the model shows every assumption but only knows what we put into it. Comparing the two shows which assumptions actually drive the answer, and whether the market price looks right.

**How Kalshi gets their numbers:**

Kalshi has no climate model; its number is a price. A Yes contract pays $1 if a 2°C year happens and a No contract pays $1 if it doesn’t, so one Yes plus one No is always worth $1 and the Yes price in cents reads as a probability. Traders post bids (offers to buy) and asks (offers to sell), and a trade happens when someone accepts one of them. On 18 November 2026 the best bid for Yes was 68¢ and the best ask 72¢, so the midpoint, 70¢, means the market thinks the chance is about 70%. The contract settles on public data: a year counts when at least two of four datasets (NASA GISS, NOAA, Berkeley Earth and HadCRUT) report at least 2.00°C, so in practice the second-highest dataset decides. Two caveats matter. Trading isn’t free: buying Yes costs 72¢ plus a 1.4¢ fee, and buying No costs 34.5¢ after fees, so any belief between about 65.5% and 73.4% is consistent with the price. And the market is thin: about 4,100 contracts are open, and one order of about $1,300 in September moved the price by 10 points.

**What is it and How I got my numbers (+customization):**

What it is: a Python version of our class model connected to real temperature data and live Kalshi prices, a dashboard that shows every result, and an interactive Decision Lab that runs the model in a web browser.

How I got my numbers:

1. I rebuilt the HW5 workbook in Python and checked it against every year of all four sheets (largest difference about 10⁻¹⁶, i.e. rounding error).
2. I connected it to the real world. I put the model on Kalshi’s 1850–1900 baseline, anchored it to observed temperatures over 2006–2025, and added year-to-year noise from El Niño and La Niña as an AR(1) process fitted to 1880–2025 (each year keeps 53% of the previous year’s deviation, plus a new shock of about 0.1°C). I copied Kalshi’s rule exactly: four datasets with their own offsets, rounded to 0.01, and a year counts when the second-highest is at least 2.00°C. Every simulation starts from 2026’s data (about 1.52°C so far).
3. I simulated thousands of futures. For my headline number I made 72 versions of the class model by changing the four inputs that matter most: climate sensitivity (p2 = 1.00, 1.15, 1.30), adjustment speed (p1 = 0.020, 0.0256, 0.032), emissions after 2024 (the HW5 economy, falling, flat or rising) and the land-use emissions the Kaya block leaves out (off or on). Each version runs 4,000 futures, 288,000 in total.
4. I used a probability density function. For each future I recorded its hottest contract reading between 2027 and 2049 and plotted the density of those readings. A future pays Yes exactly when its hottest reading is at least 2.00°C, so the probability of Yes is the area under the PDF to the right of 2.00°C. 232,668 of the 288,000 futures get there, which is 80.8%. The Excel workbook in the project shows this calculation with live formulas.
5. I made a second, more cautious estimate. A CO₂-only model fitted to history is over-confident, because aerosols and methane also shaped past warming. So I weighted 2,751 combinations of climate settings by the IPCC’s range for climate sensitivity and by how well each fits 1880–2020, then widened the uncertainty until the spread of 2041–2060 warming matched the IPCC AR6 report. That gives 67%.

Results: our 72-version model says 81%, the IPCC-calibrated version 67%, and Kalshi 70%. Every version agrees on the middle (the first 2°C year most likely around 2044); they differ in how wide the PDF is, and the width decides how much area falls past 2.00°C. If you trust the class model’s confidence, the market looks too low; with IPCC-sized uncertainty, the market looks fairly priced.

Customization: the Decision Lab lets anyone take my recommendation (Path A: 81% means a hypothetical Buy Yes, while the IPCC-calibrated 67% says Pass) or build their own forecast (Path B) by choosing the emissions path, how sure they are about the climate (or setting p1 and p2 directly), land-use emissions, the El Niño carry-over and whether 2049 counts. It reruns hundreds of model versions in about a tenth of a second and shows your probability next to Kalshi’s, a Yes / No / Pass call with what $100 would win or lose, a “play the future” simulation, a ranking of which assumption moves the odds most, the odds for any threshold and deadline, and a slider for the market price. For example, if you believe emissions fall to net zero by 2070, the chance drops to 44% and the call becomes Buy No (expected +$63 on $100); if you trust the 72-version class model, it is Buy Yes (expected +$10). Everything is hypothetical: no trades were placed.

**What I can envision this tool being used for:**

- Teaching: students can see how each homework parameter (climate sensitivity, emissions growth, land use) changes a real-world probability, and why the width of the uncertainty matters as much as the central estimate.
- Checking prediction-market prices: a transparent model gives a reference point for climate contracts. The same code already prices other Kalshi climate markets, such as the hottest-year market, monthly temperature records and CO₂ levels at Mauna Loa.
- Risk management and hedging: businesses exposed to warming, such as insurers, utilities and farms, could use these contracts as a hedge and a model like this to judge whether the price is fair. I also computed the social cost of carbon from the same model.
- Communicating policy: “if emissions fall to net zero by 2070, the odds of a 2°C year before 2050 drop from 67% to 44%” turns abstract scenarios into concrete numbers.
- Extending it: adding methane and aerosol forcing and seasonal El Niño forecasts, and tracking model vs market as new data arrives, would make it a live forecasting tool.
