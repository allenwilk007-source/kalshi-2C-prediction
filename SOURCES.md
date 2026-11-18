# Sources

Everything the project uses, grouped by what it is used for. Data were downloaded in November 2026; the Kalshi order book
used throughout is the snapshot of 18 November 2026.

## The market

| Source | Used for |
|---|---|
| **Kalshi**, contract KXWARMING-50, “Will the world pass 2 degrees Celsius over pre-industrial levels before 2050?” — market page and rules, https://kalshi.com/markets/kxwarming/global-warming/kxwarming-50 | The question, the settlement rule (≥ 2.0°C on at least two of four agencies), the screenshot |
| **Kalshi Trade API v2** (public market data), https://api.elections.kalshi.com/trade-api/v2 | Order book, trades, daily price history, other Kalshi climate markets (`market.py`, `history.py`, `scanner.py`) |
| **Kalshi fee schedule** (taker fee = 0.07 × contracts × price × (1 − price), rounded up to the cent) | Cost of buying Yes or No, the fair range after fees |
| **U.S. Department of the Treasury**, Daily Treasury Par Yield Curve Rates, https://home.treasury.gov/resource-center/data-chart-center/interest-rates/ | Discounting a payout in 2050 |

## Global temperature (the four datasets Kalshi settles on)

| Source | Used for |
|---|---|
| **NASA GISS**, GISTEMP v4, https://data.giss.nasa.gov/gistemp/ | Annual and monthly global temperature |
| **NOAA NCEI**, NOAAGlobalTemp via Climate at a Glance, https://www.ncei.noaa.gov/access/monitoring/climate-at-a-glance/global/ | Annual and monthly global temperature |
| **Berkeley Earth**, Land/Ocean temperature, https://berkeleyearth.org/data/ | Annual global temperature |
| **Met Office Hadley Centre / CRU**, HadCRUT5 (5.1.0.0), https://www.metoffice.gov.uk/hadobs/hadcrut5/ | Annual and monthly global temperature |
| **Copernicus Climate Change Service / ECMWF**, ERA5 daily global surface air temperature (Climate Pulse), https://pulse.climate.copernicus.eu/ | Filling 2026 months the agencies had not yet published |

All four datasets were put on the 1850–1900 baseline that Kalshi uses.

## Emissions and CO₂

| Source | Used for |
|---|---|
| **Our World in Data**, CO₂ and Greenhouse Gas Emissions dataset (based on the Global Carbon Budget), https://github.com/owid/co2-data | Actual 2019–2024 emissions growth, used to weight the economic scenarios |
| **Global Carbon Project**, Global Carbon Budget, https://globalcarbonbudget.org/ | Underlying emissions data (via Our World in Data) |
| **NOAA Global Monitoring Laboratory**, Mauna Loa CO₂ (monthly and daily), https://gml.noaa.gov/ccgg/trends/ | Pricing Kalshi’s CO₂-level market |

## The model and its parameters

| Source | Used for |
|---|---|
| **FECON 390 Carbon Trading, Duke University (Prof. Daniel Egger), Homework 2–5 and the HW5 sample-answer workbook** | The class model: Kaya identity, 5-box carbon cycle, radiative forcing, two-box temperature model, and the baseline inputs (`data/hw5_inputs.json`). The Python version matches the workbook in every year, 1750–2100 (`validate.py`). |
| **Kaya, Y. (1990).** Impact of carbon dioxide emission control on GNP growth: interpretation of proposed scenarios. IPCC Energy and Industry Subgroup, Response Strategies Working Group, Paris. | The Kaya identity |
| **IPCC (2021).** Summary for Policymakers. In *Climate Change 2021: The Physical Science Basis*. Contribution of Working Group I to the Sixth Assessment Report. Cambridge University Press. | Climate sensitivity range (very likely 2–5°C) and Table SPM.1 warming ranges (SSP2-4.5: 1.2–1.8°C for 2021–2040, 1.6–2.5°C for 2041–2060), used to calibrate the 67% view |
| **IPCC (2023).** *AR6 Synthesis Report: Climate Change 2023*, Summary for Policymakers. | Background on scenarios and warming |

## Social cost of carbon (bonus analysis)

| Source | Used for |
|---|---|
| **Tol, R.S.J.** The social cost of carbon. University of Sussex (working paper, 2023). | Comparing the model’s SCC with the literature |
| **Tol, R.S.J.** Database for the meta-analysis of the social cost of carbon (v2026.1), and the course spreadsheet `socialcostcarbon.xlsx` | Damage coefficients and the 14,141 published SCC estimates |
| **Tol, R.S.J.** *Climate Economics: Economic Analysis of Climate, Climate Change and Climate Policy*, 3rd ed. Edward Elgar. | Background on damages and discounting |

## Software

Python with NumPy, Matplotlib and openpyxl; the Tool Dashboard runs in the browser with no libraries. Fonts: Barlow
Condensed and Inter (Google Fonts). The Kalshi-style colors were taken from Kalshi’s public market page; this project is
not affiliated with or endorsed by Kalshi.
