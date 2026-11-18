# Speaker script: Will the world hit 2°C before 2050?

Carbon Trading class project. 36 slides, about 52 minutes at 140 words a minute. The same text is in each slide's speaker notes. Hypothetical analysis; no trades were placed.

| Part | Slides | Time |
|---|---|---|
| Introduction | 1–3 | 4:10 |
| Part 1 · How Kalshi gets its number | 4–8 | 6:00 |
| Part 2 · How we get our number | 9–26 | 28:39 |
| Part 3 · What we could hypothetically do | 27–33 | 10:13 |
| Wrap-up | 34–36 | 3:12 |
| **Total** | 1–36 | **52:15** |

---

## Introduction

*Goal: Set up the question, why it matters and the plan. About 4:10.*

### Slide 1 · Will the world hit 2°C before 2050?
*~1:09*

Our question: what is the chance that any single year before 2050 is at least 2°C warmer than pre-industrial times? Kalshi, a regulated prediction market, has a contract on exactly that, and people trade it. Its price works as a probability: 70 cents means the market thinks about 70%.

We took the climate model we built in class (the Kaya identity, the carbon cycle and the temperature model from HW2 to HW5), rebuilt it in Python, connected it to real temperature data and the live Kalshi prices, and asked whether our model agrees with the market.

Three numbers to keep in mind for the whole talk. Kalshi says 70%. Our model, run 72 different ways, says about 81%. The same model with uncertainty widened to match the IPCC says 67%, almost exactly the market. Explaining that gap is the story of this presentation, in three parts: how Kalshi gets its number, how we get ours, and what you could hypothetically do with them.

### Slide 2 · Why test a class model against a market?
*~1:40*

Why do this at all? A prediction market and a climate model are two very different ways of forecasting the same thing, and each is strong where the other is weak.

The market is a crowd with money on the line. Anyone who thinks the price is wrong can trade against it, so the price ends up reflecting everything traders know, including information our model doesn’t have, like seasonal El Niño forecasts. But a market never tells you why it believes what it believes.

The model is the opposite. Every assumption is a number we chose in class: population, GDP growth, energy intensity, carbon intensity, the carbon cycle, climate sensitivity. We can change each one and see what happens. But a model only knows what we put in.

So the interesting part is the gap. If the model and the market disagree, one of them is missing something, and by changing the model’s assumptions we can find out which assumption closes the gap. That tells us both how much to trust the market and whether a trade would make sense.

This particular contract is a good test because it settles on public data from NASA, NOAA, Berkeley Earth and HadCRUT, it runs all the way to 2050, which is the horizon our course model is built for, and it asks exactly the question the HW5 model answers: how warm the world gets as CO₂ accumulates.

### Slide 3 · Three questions, in order
*~1:20*

The talk has three parts, and each answers one question.

Part 1: how does Kalshi get its number? We’ll look at what the contract pays, how the order book turns buyers and sellers into a price, and why that price is only roughly a probability once you count fees, spreads and how thin the market is.

Part 2: how do we get ours? We start from the class model, add real data and year-to-year noise, run it thousands of times, and turn all those futures into a probability density function. The share of the density past 2.00°C is our probability. Depending on how much uncertainty we allow, that’s between 67% and 81%.

Part 3: what could we do with the two numbers? We turn a forecast into a decision: buy Yes, buy No, or pass. Then we look at a few hypothetical strategies, and finally we personalise it: if you believe something specific will happen, for example that emissions fall to net zero, here’s what that does to the odds and to what you’d win or lose. Everything in part 3 is hypothetical; no trades were placed.

---

## Part 1 · How Kalshi gets its number

*Goal: Explain the contract, the order book and what the 70% really means. About 6:00.*

### Slide 4 · How does Kalshi get its number?
*~0:32*

Part 1. Before we can say whether the market is right, we need to understand where its number comes from. Kalshi doesn’t have a climate model. Its 70% is simply the price at which people are willing to buy and sell a contract that pays one dollar if a 2°C year happens before 2050. So we’ll look at the contract, how the price forms, and how far we can trust that price as a probability.

### Slide 5 · Kalshi’s contract KXWARMING-50
*~1:06*

Kalshi is a prediction market regulated by the CFTC. Each contract pays one dollar if the event happens and nothing if it doesn’t, so the price in cents reads as the market’s probability.

This contract is unusual in three ways that matter for modelling. First, it is about a single year, not a 20-year average the way the IPCC defines crossing 2°C, so a hot El Niño year could trigger it early. Second, two of the four datasets have to agree, and the datasets differ by about a tenth of a degree, so in practice the second-highest dataset decides it. Third, it uses the 1850–1900 baseline, so we had to put every dataset and our model on that baseline.

On 18 November 2026 you could buy Yes for 72 cents and sell for 68, so the midpoint is 70%. The market is thin: about 4,100 contracts open and only a handful of trades a day.

### Slide 6 · From an order book to 70%
*~1:48*

Here’s exactly how Kalshi produces its number. There’s no model behind it, just an order book.

Each contract is a simple bet. A Yes contract pays one dollar if any year before 2050 reaches 2°C on Kalshi’s rule, and nothing otherwise. A No contract pays one dollar in the opposite case. Since exactly one of them pays, a Yes and a No together are always worth one dollar, and that keeps the two prices consistent.

On the right is the real order book from 18 November. The orange bars are people offering to sell Yes, the asks: 500 contracts at 72 cents, then more at 75, 76 and 84. The blue bars are people offering to buy Yes, the bids: only 20 contracts at 68 cents, then more down to 64. A trade only happens when a buyer accepts an ask or a seller accepts a bid.

The best bid is 68 and the best ask is 72, so the midpoint, 70 cents, is the market’s price. A contract that pays one dollar with probability p is worth about p dollars, so 70 cents reads as a 70% chance.

Why should we trust it at all? Because anyone who thinks 70% is wrong can trade against it and expect to profit, and that pressure pushes the price toward what the crowd as a whole believes. But notice how thin it is: only 20 contracts at the best bid, and 21,757 contracts traded in total since July 2025. The next slide shows why that matters.

### Slide 7 · A price isn’t quite a probability
*~1:09*

Before comparing, we had to turn the price into a probability properly. Four things matter.

Fees and the spread: buying Yes costs 72 cents plus a 1.4 cent fee, and selling gets 68 cents, so a fair belief could be anywhere from about 66% to 74%.

Interest: a contract that pays in 2050 ties up money for over 20 years, which would normally drag the price down a lot. But Kalshi pays 3.5% interest on open positions, close to Treasury bill rates, so the drag is only about one point.

Thin market: on 22 September 2026, one trader bought $1,344 of No in a single second, sweeping the order book from 76 cents down to 3 cents. The price has sat around 65 to 72 since. So the market’s probability rests on very little money.

Timing quirk: the contract expires on 8 January 2050, but agencies usually publish each year’s figure in mid-January, so 2049 might not count. That’s worth about 5 points.

### Slide 8 · Traders saw the hot year coming first
*~1:22*

To test whether the market reacts to data, we used Kalshi’s busier sister market, “Will 2026 be the hottest year ever?”, which has traded about 480,000 contracts. We rebuilt our 2026 forecast for every day of the year, using only the data that existed on that day.

The black line is the market and the red line is our data-only model. The market priced a record year at around 80 cents by August, while our model stayed below 40% until the exceptionally warm first days of November arrived. Daily moves barely line up, and the market tends to move a few days first.

Our reading: traders were using seasonal El Niño forecasts, which our model doesn’t have. That’s a useful lesson. A market can know things a model built only on past data can’t.

That wraps up Part 1. Kalshi’s 70% is the price a crowd of traders agrees on. Once fees and the spread are counted it really means anywhere from about 65% to 73%, it rests on a thin market, and it seems to use information like El Niño forecasts. Now for Part 2: how do we get our own number?

---

## Part 2 · How we get our number

*Goal: Go from the class model to a probability density, and compare it with Kalshi and the IPCC. About 28:39.*

### Slide 9 · How do we get our number?
*~0:34*

Part 2. Now our side. Instead of a crowd, we use the climate model we built in class. One run of the model gives one smooth path, which can’t give a probability. So we run it thousands of times with different plausible settings and realistic year-to-year noise, record the hottest reading each future would show the contract, and plot all of those readings as a probability density function. The share of that density at or above 2.00°C is our probability.

### Slide 10 · From the homework model to a market forecast
*~1:26*

Here is the whole pipeline in six steps. Everything is in Python, and it all runs from one command that opens a local dashboard and refreshes the data in about three minutes.

Step 1 rebuilds the HW5 spreadsheet exactly. Step 2 connects it to the real world: the four temperature datasets Kalshi settles on, and the year-to-year noise from El Niño and La Niña. Step 3 runs 100,000 versions of the future with different economic growth, energy use and climate sensitivity. Step 4 updates the starting point with 2026 data. Step 5 turns Kalshi’s price into a fair probability and checks 15 other Kalshi climate markets. Step 6 asks whether a student could have made money, hypothetically. At the end there’s an interactive Decision Lab where anyone can change these assumptions and make their own call.

Why build it this way? Each step answers one doubt about the last. Does the Python model really match the homework? Step 1 checks every year. Does a smooth model say anything about one noisy year? Step 2 adds the noise. How sure can we be? Step 3. Does this year’s heat change things? Step 4. Is the market price really a probability? Step 5.

### Slide 11 · The class model, line for line
*~1:07*

First we rebuilt the HW5 workbook in Python. Population, GDP per person, energy intensity and carbon intensity for rich, middle and poor countries give emissions. Emissions go into the five-box carbon cycle, which gives CO₂ in parts per million. Forcing is 5.35 times the log of concentration over 275, and the two-box model turns forcing into atmospheric and ocean temperature.

We checked it against every year of all four HW5 sheets, and the largest difference is about ten to the minus sixteen: rounding error. So everything later in the talk really is the class model.

On the HW5 template economy, where emissions keep climbing, the smooth model crosses 2°C in 2047 and reaches 4.6°C by 2100. The chart shows the model’s path against the four real datasets: it tracks 150 years of observations well. One thing we found: Parameter 2 implies about 4.3°C of warming per doubling of CO₂, at the high end of the IPCC range.

### Slide 12 · The class model: four equations, run every year
*~2:19*

Now the math, in five steps. Step one is the class model itself, exactly as in HW2 to HW5. I didn’t change any equation; I rebuilt the spreadsheet in Python and checked it.

Equation one is the Kaya identity. For rich, middle and poor countries, emissions are population times GDP per person times energy per dollar times CO₂ per unit of energy. Each of the three factors grows at its own rate in each region, so there are nine growth rates. Those are the economic inputs.

Equation two is the five-box carbon cycle. Each year’s emissions are split into five boxes: 13% stays forever, 20% decays with a 363-year lifetime, 32% with 74 years, 25% with 17 years and 10% with 2 years. One million tonnes of carbon adds 0.00047 ppm. CO₂ concentration is 275 plus what is in the boxes.

Equation three turns concentration into radiative forcing: 5.35 times the natural log of CO₂ over 275, in watts per square metre.

Equation four is the two-box temperature model. Each year the atmosphere moves a fraction p1 of the way toward its equilibrium, p2 times the forcing, and exchanges heat with the ocean through p3 and p4. Then we subtract the model’s own 1850–1900 average, because that’s the baseline Kalshi uses.

The table runs it on the HW5 economy. In 2026 the model emits 12 gigatonnes of carbon, CO₂ is 429 ppm, forcing is 2.38 and warming 1.34°C. By 2049 emissions reach 19.5 gigatonnes, CO₂ 526 ppm, and the smooth model reaches 2.09°C.

Why trust this step? We compared the Python output with every year of all four sheets of the HW5 workbook, 1750 to 2100. The largest difference is about 7 times ten to the minus 16, which is rounding error.

One thing to notice: p2 equal to 1.15 implies about 4.3°C of warming for a doubling of CO₂, at the high end of the IPCC’s range. That matters for steps four and five.

### Slide 13 · Real data, noise, and two views of the climate
*~1:16*

The class model draws one smooth line, but real temperatures bounce around by about a tenth of a degree from year to year because of El Niño, La Niña and volcanoes. We fitted that noise to the gap between the model and the four datasets, and back-tested it: fitting only to 1999 and simulating 2000–2025, 92% of real years fell inside the model’s 90% band.

Then uncertainty. We ran the model two ways. Fitted to history, it picks the climate settings that best reproduce 1880–2020 temperatures and trusts them completely. Because the class model only includes CO₂, that makes it very sure about the future warming rate. The IPCC-calibrated view uses the same model but deliberately trusts the fit less, widening the spread until 2041–2060 matches the IPCC AR6 range. The reason is that real warming also depends on aerosols and methane, which a CO₂-only model can’t see.

The chart shows the key point: both views centre on about 2.0°C for 2041–2060, which is the IPCC’s own best estimate for its middle scenario. They differ only in width.

### Slide 14 · 2026 is running hot
*~0:56*

The model’s starting point matters, so we updated it with 2026 data. NASA and NOAA have published through September and HadCRUT through July. For the missing months we used ERA5, Copernicus’s daily global temperature, through a regression linking ERA5 to each dataset. We back-tested this on 2023–2025 and widened the uncertainty until it was honest.

2026 comes out at about 1.52°C above pre-industrial, likely a record. October and early November were exceptionally warm, which looks like a developing El Niño. We found that warm late-year months carry into the next year, so 2027 should stay warm too.

But here’s the surprise: it barely changes the 2050 question. A hot year fades within a few years. What decides the 2040s is the long-run trend, and that comes from emissions and climate sensitivity.

### Slide 15 · One simulated future, year by year
*~2:24*

Step two turns the smooth model line into one realistic future, using the same rules Kalshi uses.

First, the anchor. The model doesn’t match the observed temperature exactly in recent years, so we measure the average gap between observations and the model over 2006 to 2025. For the class settings that gap, b, is only plus 0.02°C. Projections start from where the world actually is: model plus b.

Second, noise. Real temperatures bounce around the trend because of El Niño, La Niña and volcanoes. We modelled the gap between observations and the model as an AR(1) process: each year it keeps 53% of last year’s deviation from b and adds a new random shock with a standard deviation of about 0.1°C. Both numbers were estimated from the model’s errors over 1880 to 2025, so the noise is what history shows, not a guess.

Third, the start. 2026 isn’t finished, so we estimate it from the agencies’ published months plus the daily ERA5 reanalysis: 1.52°C give or take 0.02. Because late 2026 is unusually warm, part of that warmth carries into 2027, with weights we estimated from 1960 to 2025.

Fourth, Kalshi’s rule. Each dataset sits at a slightly different level: GISS 0.06 below the four-dataset average, NOAA 0.09 below, Berkeley 0.11 above, HadCRUT 0.04 above, measured over 1996 to 2025. Each dataset also gets a small error of its own. We round each to two decimals, as the agencies do, and a year counts when the second-highest of the four is at least 2.00, which is what “two of four datasets” means.

The table is one real simulated future with the class settings. In 2027 the El Niño noise is +0.21, but the second-highest dataset only reads 1.63. In 2040 a cool year, −0.12, keeps it at 1.70. In 2041 Berkeley alone reaches 1.98, but one dataset isn’t enough. In 2042 the trend is 1.86 and the noise +0.20, Berkeley reads 2.17 and HadCRUT 2.09, so the second-highest is 2.09: this future pays Yes in 2042.

### Slide 16 · From many futures to a probability and a PDF
*~2:09*

Step three is how one future becomes a probability, and where the probability density function comes in.

We repeat step two many times. Each future gets its own climate settings, its own economy and its own random noise. The probability is simply a count: the number of futures that have at least one Yes year, divided by the total. With 100,000 futures the standard error of that count is the square root of p times one minus p over N, about 0.15 points, so our numbers are accurate to roughly plus or minus 0.3 points.

The PDF: for each future, we record the highest reading the contract would ever see between 2027 and 2049, meaning the highest second-highest dataset. Call it M. The probability density function of M shows where all the futures end up. Here it is for the IPCC-calibrated view: it peaks around 2.07°C and most futures land between about 1.7 and 2.4.

The link between the two is exact. A future pays Yes if and only if its highest reading M is at least 2.00. So the probability of Yes is the area under the density to the right of the 2.00 line: 67% here. The other 33% of futures never reach 2°C before 2050.

Why use a PDF and not just the count? Because it shows the shape. Two forecasts can have the same middle but different widths, and the width decides how much area falls past 2.00. That’s the whole story of our 81% versus 67%.

A detail for accuracy: we always report the counted share. The curve is smoothed for display, and because readings are rounded to 0.01, the smoothing spreads the futures sitting at exactly 2.00 across both sides of the line. That’s why the smoothed area comes out at 66% while the count is 67.1%.

### Slide 17 · Where the model’s futures land
*~0:59*

This is the heart of the project. Each curve is a probability density: where one version of the model’s 100,000 futures land. On the x-axis is the highest reading the contract will see between 2027 and 2049. The contract pays Yes exactly when that peak is at or above 2.00°C, so the area to the right of the yellow line is the probability of Yes.

Look at the shapes. The class model as taught (purple) is tall and narrow and sits almost entirely right of 2°C: 99%. Fitted to history (blue) is a bit wider: 93%. The IPCC-calibrated version (red) has about the same middle, around 2.1°C, but a much wider spread, so a third of it falls below 2°C: 67%.

So the versions agree on where warming is headed. They disagree on how sure we can be.

### Slide 18 · Where 67% comes from: calibrating the uncertainty
*~2:55*

Step four explains the 67%, the number I’d defend most. The question is how uncertain we should be about the climate’s response, the two class parameters p1 and p2.

One: we set up a grid of 2,751 combinations, p1 from 0.010 to 0.060 and p2 from 0.50 to 1.80.

Two: the prior. Before looking at our data, we weight each combination by the IPCC AR6 assessment of climate sensitivity, which says 2 to 5°C per doubling of CO₂ is very likely. In the class model, sensitivity is 5.35 times ln 2 times p2, about 3.71 times p2, so the IPCC range maps onto p2.

Three: the likelihood. For each combination we run the class model over 1880 to 2020 and measure how well it matches the observed temperatures, allowing AR(1) errors. Settings that reproduce history get more weight.

If we simply multiply prior and likelihood, which is standard Bayesian updating, we get the history-fit view in the first row of the table. It’s very narrow: 2041–2060 warming between 1.92 and 2.13°C. That gives 93%. The problem is that a CO₂-only model fitted to history is over-confident: aerosols and methane also shaped past warming, and the model can’t see them, so the fit looks better than it really is.

Four: so we temper the likelihood, raising it to the power one over T. We chose T by bisection so that the 5-to-95% spread of 2041–2060 warming equals 0.67°C. That target comes from AR6 Table SPM.1 under SSP2-4.5: the 2041–2060 range is 1.6 to 2.5°C, a half-width of 0.45, and the 2021–2040 range is 1.2 to 1.8°C, a half-width of 0.30. Because our model is anchored to observed temperatures, the near-term part of that uncertainty is already pinned down, so we remove it in quadrature: two times the square root of 0.45 squared minus 0.30 squared, which is 0.67°C. T came out at 11.

Five: we draw 20,000 climate settings from that tempered posterior, pair each with a randomised Kaya economy weighted to match real 2019–2024 emissions growth, and simulate 5 noise paths each from the 2026 start. That’s 100,000 futures, and 67.1% of them reach 2°C.

The table compares the views. The IPCC-calibrated row has a sensitivity range and a 2041–2060 range very close to the AR6 report’s own. The wide row flattens the likelihood as far as it will go; even then the spread is a little narrower than the full AR6 range, which we note as a limitation.

### Slide 19 · Our estimate: 72 versions of the class model
*~0:57*

This is how we get our headline number. We built it the way a modeller would: run the class model many times while changing its most important settings, and average. We changed four things: climate sensitivity (Parameter 2), how fast the atmosphere adjusts (Parameter 1), the emissions path (the HW5 economy, falling, flat or rising), and whether the land-use emissions the Kaya block leaves out are included. That makes 72 combinations, 4,000 futures each.

The table shows how much each setting moves the answer. Climate sensitivity matters most, from 58% to 98%. Emissions matter less than you might expect, because most warming before 2050 is already locked in.

Mixing all 72 together gives the curve on the right. Its mean says 80.8% chance of a 2°C year before 2050, about 11 points above Kalshi.

### Slide 20 · Where 81% comes from: 72 versions, equally weighted
*~2:07*

Step five explains the 81%, which is our headline “model” number and the one behind the hypothetical Yes trade.

Instead of a statistical posterior, this is a sensitivity ensemble, the way modellers often present results. We took the four inputs that matter most and gave each a low, central and high value around the class settings. Climate sensitivity p2: 1.00, 1.15 as in class, and 1.30. Adjustment speed p1: 0.020, 0.0256 as in class, and 0.032. Emissions after 2024: the HW5 economy, or falling, flat or rising paths. And whether to add back the roughly 1 billion tonnes of carbon a year of land-use emissions that the Kaya block leaves out. Three times three times four times two is 72 versions.

Each version is simulated exactly as in steps two and three: 4,000 futures with the class noise from the 2026 start, and P of v is the share of those futures that reach 2°C. Our estimate is the plain average of the 72 probabilities, which is the same as pooling all 288,000 futures: 80.8%.

The table on the right shows where it comes from. Each cell averages the eight emissions and land-use versions for one combination of p2 and p1. With low sensitivity and slow adjustment it’s 28%; with the class settings it’s 93%; with high values it’s essentially 100%. The average of the nine cells is 80.8%.

The choice a careful reader should question is the equal weighting. These 72 versions are not weighted by how well they fit history or by the IPCC’s ranges, and the grid is centred on the class p2, which implies about 4.3°C of warming per doubling, at the high end. That’s exactly why we also built the IPCC-calibrated 67% in step four, and why the deck presents both numbers.

### Slide 21 · Every version of the model next to Kalshi
*~0:47*

Here are all the headline numbers side by side. Kalshi’s price is 70%, and once you count Kalshi’s fee and the gap between the buy and sell prices, any belief between 66% and 74% is consistent with it. That’s the yellow band.

Our IPCC-calibrated model, 67%, sits inside the band: it agrees with the market. Our 72-version ensemble, 81%, sits above it. Fitted to history, 93%, and the class model exactly as taught, 99%, are well above.

The more confident the version, the higher the probability. That’s because the middle of every version is already a bit above 2°C, so a narrower distribution puts more of its weight above the line.

### Slide 22 · Four views of the same question
*~2:06*

This slide puts the four views side by side on five dimensions, because a single probability hides most of what’s going on.

Row one is the headline. Our 72-version model says 81%, the IPCC-calibrated version 67%, Kalshi 70%. The IPCC report itself doesn’t give this number at all, and row two explains why.

Row two: what counts as 2°C. Kalshi asks about any single calendar year, confirmed by two of four datasets. We copied that rule exactly in both versions of our model. The IPCC defines crossing 2°C as a 20-year average, which smooths out El Niño years. A single hot year comes several years before the 20-year average gets there, so Kalshi’s question is easier to reach than the IPCC’s.

Row three: timing. Both versions of our model put the first 2°C year at a median of 2044, with most futures between about 2038 and 2048. The IPCC’s middle scenario puts the 2041–2060 average at 2.0°C, which is the same story told with a 20-year average. Kalshi’s price doesn’t tell us when, only whether.

Row four: the range. This is where the two versions of our model really differ. The highest reading before 2050 ranges from 1.89 to 2.43°C in the 72-version model but from 1.74 to 2.43°C in the IPCC-calibrated one. Same top, longer bottom tail, so fewer futures make it to 2°C. The IPCC’s own range for 2041–2060 is 1.6 to 2.5°C, close to our IPCC-calibrated version, which is why we built it.

Row five: what each view can see. Our model sees CO₂ and random year-to-year noise. The market sees whatever traders know, including El Niño forecasts. The IPCC uses all greenhouse gases, aerosols and dozens of full climate models. That’s why we trust the IPCC’s width more than our own.

### Slide 23 · Change the deadline or the threshold
*~1:35*

Kalshi only asks one question: 2.00°C by 2049. But our simulations answer every version of it, so we can see where the two versions of our model agree and where they don’t.

Left table: change the deadline. Almost nobody thinks a 2°C year comes before 2035: 2% in our ensemble, 4% in the IPCC-calibrated view. By 2040 it’s still only about one in six. The odds climb fast through the 2040s, because that’s when the long-run trend reaches 2°C and any El Niño year can push a single reading over.

Right table: change the threshold. 1.8°C by 2049 is nearly certain in both views. 2.2°C is about a one-in-three chance, and 2.5°C is very unlikely in both.

The interesting pattern is in the callout. The IPCC-calibrated view is wider, not lower. So it gives more chance to the extremes: a 2°C year before 2035, or a reading of 2.5°C. But it gives less chance to the middle-of-the-road outcome of reaching 2°C by 2049. That’s because the middle of both views sits just above 2°C. When you widen a distribution whose middle is just above a line, you push more of it below the line.

This is the clearest way to see that the disagreement is about confidence, not direction. You can try any deadline and threshold in the Decision Lab’s odds explorer.

### Slide 24 · One factor at a time, from the IPCC-calibrated 67%
*~1:39*

Which assumptions actually matter? We started from the IPCC-calibrated forecast, 67%, and changed one factor at a time while keeping everything else fixed. Each bar shows how far that one factor can move the answer. The gold line is Kalshi’s 70%.

Climate certainty is by far the biggest. With the full IPCC width the answer drops to 54%; trusting the class model’s fit to history raises it to 93%. So the single most important question isn’t about economics or policy, it’s how confident we are about the climate’s response.

Emissions come second: from 44% if emissions fall to net zero by 2070, to 75% if they double by 2050. That’s a big range, but notice it’s smaller than you might expect. Most of the warming that matters before 2050 is already locked in by CO₂ that’s already in the air, because CO₂ stays there for centuries.

Land-use emissions, which the class Kaya model leaves out, add about 5 points. Whether 2049 counts, because its data may arrive after the contract expires, is worth about 5 points the other way. And the El Niño carry-over from this year’s warm end barely matters for the 2040s: a hot year fades within a few years.

This is why the deck keeps coming back to confidence. You can rerun this chart from any starting point, and click any option to switch to it, in the Decision Lab.

### Slide 25 · How we tested it, and what it assumes
*~2:12*

Before comparing with the market, here is how we checked the numbers and the assumptions behind them, because each one could change the answer.

The checks. First, the Python model reproduces the HW5 workbook in every year of all four sheets, so we really are using the class model. Second, we tested the noise model out of sample: we fitted it using data only up to 1999, simulated 2000 to 2025, and 92% of the real years fell inside the model’s 90% band, so the year-to-year spread is about right. Third, the method that estimates 2026 before the year is over was back-tested on 2023 to 2025, and we widened its uncertainty by about a third until the errors matched. Fourth, there are 63 automated tests across the project, and the browser version used in the Decision Lab matches Python to within 0.2 points. Fifth, with 100,000 simulated futures the sampling error is only about plus or minus 0.3 points.

The assumptions. The class model only has CO₂ forcing, so the effects of aerosols, methane and other gases are absorbed into p2 and the anchor; that’s the main reason a history fit is over-confident. The noise is assumed to be AR(1) with normal shocks, and the differences between the four datasets are held at their 1996–2025 averages. We use no El Niño forecasts beyond carrying part of the late-2026 warmth into 2027, and the market probably does. The 81% gives all 72 versions equal weight, which is a modelling choice. And the 67% depends on how we calibrated the spread to the IPCC, which is also a choice, though one tied to a published assessment.

None of these assumptions changes the middle of the forecast much, about 2°C in the mid-to-late 2040s. They mostly change the width, and the width is what decides whether the probability is 67% or 81%.

### Slide 26 · Our model says 81% . With IPCC-sized uncertainty it says 67% . Kalshi says 70% .
*~1:04*

This is the one slide to remember. Our ensemble of the class model says about 81% chance of a 2°C year before 2050. But when we widen the model’s uncertainty to match the IPCC’s ranges, the same model says 67%, which is almost exactly what the market says, 70%.

So there are two ways to read it. If you trust the class model’s narrow view, the market is too low and Yes is cheap. If you think the IPCC’s wider uncertainty is right, which most climate scientists would, the market is fairly priced. Every version of our model agrees on the middle, about 2°C around 2045 to 2050. They differ only on how confident to be.

That closes Part 2. We now have two numbers: the market’s 70%, and ours, between 67% and 81% depending on how much uncertainty we allow. Part 3 asks what someone could hypothetically do with them.

---

## Part 3 · What we could hypothetically do

*Goal: Turn the numbers into Yes / No / Pass, test strategies, and show what changes if you believe X. About 10:13.*

### Slide 27 · What could we do with these numbers?
*~0:37*

Part 3. We now have two numbers: Kalshi’s 70%, and ours, 67% to 81% depending on how much uncertainty we allow. What could someone do with them? First we’ll set out the rule that turns a probability into a decision. Then we’ll test a few hypothetical strategies. Finally we’ll personalise it: if you believe a particular thing will happen, what does that do to the odds and to your payoff? All of this is a classroom exercise. We placed no trades, and none of it is investment advice.

### Slide 28 · When is a price worth trading?
*~1:33*

Before any trade idea, here’s the rule that turns a forecast into a decision, and it explains why some of our estimates say trade and others say don’t.

A Yes contract pays $1 if a 2°C year happens. Buying one costs the 72-cent ask plus Kalshi’s fee of about 1.4 cents, so 73.4 cents in total. If you believe the chance is more than 73.4%, each contract is worth more to you than it costs: buy Yes.

A No contract pays $1 if it doesn’t happen. It costs 34.5 cents including the fee. That’s worth it only if you believe the chance of No is more than 34.5%, in other words the chance of Yes is less than 65.5%.

Between 65.5% and 73.4% neither side is worth buying. The market’s 70% isn’t one number, it’s a band, because the bid–ask spread and the fee eat any small edge.

Now place our estimates on the line. The IPCC-calibrated view, 67%, and Kalshi’s 70% are both inside the pass zone: on that view the market is fairly priced. Our 72-version model, 81%, and the history fit, 93%, are both in the buy-Yes zone. So whether there’s a trade at all depends entirely on which version of our model you trust. The next slides look at the trade if you believe 81%.

### Slide 29 · Value bet: buy Yes if we believe 81%
*~1:09*

The simplest strategy: if you believe our 81% and the market charges 73.4 cents including the fee, buying Yes has an expected profit of 7.4 cents per contract.

With a hypothetical $1,000 you’d buy 1,362 contracts. If any year hits 2°C before 2050 you collect $1,362, a profit of $362. If not, you lose the $1,000. The expected profit is about $100. But it takes on average 17 years to pay, so per year it’s small, plus Kalshi pays 3.5% interest on the position in the meantime. The Kelly formula would put 28% of a bankroll on it; half of that is the usual cautious version.

The chart shows the catch. The bet is only profitable if your probability is above the 73.4% cost. Our ensemble says 81%, so yes. Our own IPCC-calibrated estimate says 67%, and on that view the bet loses about 6 cents a contract. So the trade depends entirely on which version of our model you trust.

### Slide 30 · Softening the loss, and an arbitrage check
*~1:21*

Strategy B adds a hedge. Kalshi also has a market on whether CO₂ at Mauna Loa reaches 445 ppm before 2030. Our CO₂ model gives that about 1%, but the market prices it around 21%, so buying No looks cheap. CO₂ that high would only happen with very fast emissions and warming, so this leg tends to lose only in worlds where the 2°C bet wins, and pays in the slow-warming worlds where it loses. Splitting $1,000 seventy-thirty, the bad case improves from losing $1,000 to losing $638, and the good case falls from +$362 to +$315.

Strategy C is a true arbitrage check. Kalshi lists two separate contracts that both ask whether 2026 will be NASA’s record year. Buying Yes on one and No on the other pays exactly $1 whatever happens, so if the pair ever costs less than $1 after fees, it’s free money. Today it costs $1.019, so there is no arbitrage. It would take a move of about 2 cents. One risk: one of the two tickers says “27”, and if Kalshi treats it as a 2027 market they stop being the same bet.

### Slide 31 · $10 a week since June 2025: would it have paid?
*~1:24*

We also tested the idea of small, constant trades, using Kalshi’s real price history since the contract listed in June 2025, with $10 a week.

Method 1 buys at the asking price every week, like dollar-cost averaging. You’d have paid 80 cents on average, because the price was higher last year. If our 81% is right you just about break even; if the IPCC’s 67% is right you’re down $94; sold today you’d be down $98.

Method 2 posts a limit order one cent above the best bid each week. Patient buyers pay no fee on this market and get a better price, about 76 cents, so it does better: +$36 or −$58.

Method 3 is spread capture: quote both a buy and a sell price each week and earn the gap when both fill. It’s the only one that doesn’t depend on who’s right about the climate. It made about $12 in 17 months, assuming both sides fill, which is optimistic in a market this thin.

Verdict: small regular bets only pay if our 81% is right. The only model-free edge is acting as a patient market maker, and here that’s worth about $10 a year.

### Slide 32 · If you believe X, here’s what happens
*~2:07*

This is the personal version of the whole project. Pick the row that matches what you believe will happen, and read across: the chance of a 2°C year it implies, the hypothetical call, and what $100 would do.

Start from the highlighted row. If you think the IPCC-calibrated view is right, the chance is 67%, inside the band the market price allows, so you’d pass: the price is fair to you.

Now move up the table, to beliefs that make 2°C less likely. If you believe emissions fall to net zero by 2070, the chance drops to 44%. No costs 34.5 cents, and you think No happens 56% of the time, so you’d buy No. $100 buys 289 No contracts: you’d win $189 if no year reaches 2°C, lose $100 if one does, and expect about $63. The same logic gives Buy No if you think uncertainty is as wide as the full IPCC range, if emissions stay flat, or if 2049’s data comes too late to count.

Move down the table, to beliefs that make 2°C more likely. Adding back land-use emissions gets you to 73%, still just inside the band, so still pass. If emissions double by 2050, or if you trust our 72-version class model, or the class model’s fit to history, you’d buy Yes: $100 buys 136 Yes contracts, worth +$36 if a 2°C year happens and −$100 if not. The expected gain grows the more confident you are: $2, $10, $26.

Two lessons. First, the payoff shape doesn’t change, only which side you’re on and how often you expect to win. Second, every Yes bet risks $100 to make $36, so it only makes sense if you’re quite sure. The Decision Lab lets you combine beliefs, not just change one at a time.

### Slide 33 · The Decision Lab: make your own call
*~2:00*

Everything in this talk can be tried live. We built a Decision Lab that runs the class model directly in a web browser, using 400 versions of the climate and the economy, and recomputes a forecast in about a tenth of a second.

There are two paths. Path A takes our recommendation: it shows our 81% against Kalshi’s 70%, explains why that means buy Yes, shows the IPCC-calibrated second opinion that says pass, and then lets you play out the future. Each play draws one of the simulated futures and reads the contract year by year, so you can watch whether the bet pays. Play 100 at once and you see the odds turn into money: roughly 80 wins out of 100 for our model.

Path B lets you build your own forecast step by step: choose the emissions path, how sure you are about the climate, whether to add land-use emissions, the El Niño carry-over, and whether 2049 counts. You get your own probability against Kalshi’s and a Yes, No or Pass call with what you could win or lose.

Then four tools: play the future, an odds explorer for any threshold and deadline, a chart of what moves the odds where you can click any option to switch to it, and a price slider that shows where your call flips if the market moves.

Every number in the Lab matches our Python results to within a fraction of a point. As always, it’s hypothetical: nothing places a trade.

That’s Part 3. The numbers only turn into a decision once you say what you believe, and the Lab lets anyone do that. Let me finish with what we learned.

---

## Wrap-up

*Goal: What we learned, the limits, and the bonus SCC slide. About 3:12.*

### Slide 34 · What we learned
*~1:01*

Four things to take away.

One: the course model is a good model. Once connected to real data it reproduces 150 years of observations, and its middle estimate, about 2°C in the late 2040s, matches the IPCC.

Two: the disagreement with the market is about confidence, not direction. Our ensemble says 81%, the market 70%. But the IPCC-calibrated version of the same model says 67%, inside the market’s range.

Three: the market looks fairly priced but it’s small. One modest order moved it by ten points, and it seems to use information like El Niño forecasts that our model doesn’t have.

Four: there’s no easy money. Every trade we looked at only pays if you believe the narrow class-model view over the IPCC’s uncertainty. The only strategy that doesn’t depend on that, earning the bid–ask spread, makes about ten dollars a year here.

### Slide 35 · What the model can’t do (yet)
*~1:06*

To be honest about the limits. The class model only tracks CO₂, so the effects of aerosols and methane are hidden inside Parameter 2. That’s exactly why we needed the IPCC-calibrated version. The model knows nothing about El Niño forecasts, which the market clearly uses. Damage estimates in the literature range from small benefits to losses of more than 20% of GDP, so any money figure for climate damage is very uncertain. And our trading back-tests assume orders get filled at the prices we chose, which is optimistic in a thin market.

Next steps would be to add non-CO₂ forcing and seasonal El Niño forecasts, keep tracking how our model and the market move as new data arrives (the dashboard already records every run), and extend the scanner as Kalshi lists new climate contracts.

Everything here is a hypothetical class analysis. We didn’t place any trades, and none of it is investment advice. Thank you.

### Slide 36 · The social cost of carbon from our model
*~1:04*

Our very first question this semester was how to predict the social cost of carbon, so we asked the class model directly. We added one extra gigatonne of carbon in 2027 and followed the extra warming all the way to 2300. We turned that warming into damages using the 14,000 estimates in the course spreadsheet from Tol’s database, then discounted the damages back to today using the net-present-value method from HW1.

At a 1.5% pure rate of time preference, the model gives about $66 per tonne of carbon, or $18 per tonne of CO₂. Tol’s published estimates at the same discount rate have a median of $143. At 3% we get $34 against Tol’s $29, the same ballpark.

The biggest lesson: about three quarters of the uncertainty comes from how costly warming is, the damage function, not from the climate science or the economics. Discounting choices matter a lot too.
