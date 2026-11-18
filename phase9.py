"""Phase 9: does the Kalshi market react to temperature data, and how do model and market compare over time?

    python phase9.py      # results/phase9.json, results/history.jsonl, figures/p9_*.png
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from history import candle_series, fetch_candles, lead_lag, rolling_kxgtemp
from market import latest_snapshot
from nowcast import backtest, load_monthly

HERE = Path(__file__).resolve().parent
FIG = HERE / "figures"
OUT = HERE / "results"
HIST = OUT / "history.jsonl"
SWEEP = date(2026, 9, 22)


def forward_fill(dates, values, days):
    """Value on each day = last observed value on or before that day (NaN before the first)."""
    out, j, last = [], 0, np.nan
    for d in days:
        while j < len(dates) and dates[j] <= d:
            last = values[j]
            j += 1
        out.append(last)
    return np.array(out, dtype=float)


def append_tracking(snap):
    """One line per pipeline run: market vs model for the two main contracts."""
    p4 = json.loads((OUT / "phase4.json").read_text()) if (OUT / "phase4.json").exists() else None
    p5 = json.loads((OUT / "phase5.json").read_text()) if (OUT / "phase5.json").exists() else None
    if not (p4 and p5):
        return
    rows = [json.loads(l) for l in HIST.read_text().splitlines()] if HIST.exists() else []
    if any(r.get("snapshot") == snap["dir"] for r in rows):
        return
    h = p5["p_yes"]["Kaya randomised + 2019-24 weighting"]
    kx = p5["kxgtemp_26"]
    rec = {"snapshot": snap["dir"], "time": snap["fetched_utc"],
           "kxwarming_mid": p4["snapshot"]["mid"], "model_ipcc": h["ipcc"]["p_yes"], "model_history": h["history"]["p_yes"],
           "kxgtemp_mid": (kx["bid"] + kx["ask"]) / 2, "kxgtemp_model": p5["p_kxgtemp_model"]}
    with HIST.open("a") as f:
        f.write(json.dumps(rec) + "\n")


def main():
    FIG.mkdir(exist_ok=True)
    OUT.mkdir(exist_ok=True)
    snap = latest_snapshot()
    today = datetime.fromisoformat(snap["fetched_utc"]).date()

    # ---------------------------------------------------------------- prices
    gt = candle_series(fetch_candles("KXGTEMP", "KXGTEMP-26-P0", date(2025, 6, 1)))
    wm = candle_series(fetch_candles("KXWARMING", "KXWARMING-50", date(2025, 6, 1)))

    # ---------------------------------------------------------------- rolling model for KXGTEMP-26
    mon, (era5, _) = load_monthly()
    _, rms = backtest(mon, era5)
    days = [date(2026, 1, 5) + timedelta(days=i) for i in range((today - date(2026, 1, 5)).days + 1)]
    roll = rolling_kxgtemp(mon, era5, days, rms)
    model = np.array([r["p"] for r in roll])
    market = forward_fill(gt[0], gt[1], days)
    ok = ~np.isnan(market)
    dm, dk = np.diff(market[ok]), np.diff(model[ok])
    ll = lead_lag(dm, dk, 7)
    best = max(ll, key=lambda k: (ll[k] if ll[k] == ll[k] else -9))
    # release days: the day GISS publishes a new 2026 month (as assumed) -> market move around it
    rel = [i for i in range(1, len(roll)) if roll[i]["giss_months_published"] > roll[i - 1]["giss_months_published"]]
    events = []
    for i in rel:
        if i + 3 < len(days) and not np.isnan(market[i - 1]) and not np.isnan(market[i + 3]):
            events.append({"date": days[i].isoformat(), "month": roll[i]["giss_months_published"],
                           "model_change": float(model[i] - model[i - 1]),
                           "market_change_next3d": float(market[i + 3] - market[i - 1])})
    agree = [np.sign(e["model_change"]) == np.sign(e["market_change_next3d"]) for e in events
             if abs(e["model_change"]) > 0.01 and abs(e["market_change_next3d"]) > 0.005]
    gap = model[ok] - market[ok]
    news = {"days": int(ok.sum()), "corr_levels": float(np.corrcoef(model[ok], market[ok])[0, 1]),
            "mean_abs_gap": float(np.mean(np.abs(gap))), "gap_last": float(gap[-1]),
            "corr_daily_changes_same_day": ll[0], "lead_lag": ll, "best_lag_days": int(best),
            "release_events": events,
            "release_sign_agreement": (float(np.mean(agree)) if agree else None), "n_release_events_used": len(agree)}

    # ---------------------------------------------------------------- KXWARMING-50 history
    wd, wp, wv, woi = wm
    pre = [p for d, p in zip(wd, wp) if d < SWEEP]
    post = [p for d, p in zip(wd, wp) if d > SWEEP]
    wstats = {"first_day": wd[0].isoformat(), "last_day": wd[-1].isoformat(), "days": len(wd),
              "price_first": float(wp[0]), "price_last": float(wp[-1]),
              "mean_before_sweep": float(np.mean(pre)) if pre else None,
              "mean_after_sweep": float(np.mean(post)) if post else None,
              "total_volume": float(wv.sum()), "open_interest_last": float(woi[-1])}
    append_tracking(snap)
    track = [json.loads(l) for l in HIST.read_text().splitlines()] if HIST.exists() else []

    # ---------------------------------------------------------------- print
    print(f"\nKXGTEMP-26 ('2026 hottest year'): market vs the model as it would have read each day, {days[0]} to {days[-1]}")
    print(f"  levels correlation {news['corr_levels']:.2f}; mean |model - market| {news['mean_abs_gap']:.3f}; today's gap {news['gap_last']:+.3f}")
    print(f"  daily changes: same-day corr {ll[0]:+.2f}; lead-lag (k>0 = model leads market by k days): "
          + " ".join(f"{k:+d}:{v:+.2f}" for k, v in ll.items()))
    print(f"  best lag {best:+d} days")
    print(f"  GISS release days (assumed 15th): {len(events)} events; model and market moved the same way in "
          + (f"{news['release_sign_agreement']:.0%} of {len(agree)}" if agree else "n/a"))
    for e in events:
        print(f"    {e['date']} (month {e['month']} published): model {e['model_change']:+.3f}, market next 3 days {e['market_change_next3d']:+.3f}")
    print(f"\nKXWARMING-50: {wstats['days']} days {wstats['first_day']} to {wstats['last_day']}; price {wstats['price_first']:.2f} -> {wstats['price_last']:.2f}; "
          f"mean {wstats['mean_before_sweep']:.3f} before the 22 Sep sweep vs {wstats['mean_after_sweep']:.3f} after")
    print(f"  tracking file: {len(track)} pipeline run(s) recorded in results/history.jsonl")

    figures(days, model, market, roll, events, ll, wm, track)
    res = {"kxgtemp": news, "kxgtemp_daily": [{"date": d.isoformat(), "model": float(m), "market": (None if np.isnan(k) else float(k))}
                                             for d, m, k in zip(days, model, market)],
           "kxwarming": wstats,
           "kxwarming_daily": [{"date": d.isoformat(), "price": float(p), "volume": float(v)} for d, p, v in zip(wd, wp, wv)],
           "tracking": track,
           "assumptions": "ERA5 to D-2; GISS/NOAA month m from the 15th of m+1; HadCRUT month m from the 15th of m+3"}
    (OUT / "phase9.json").write_text(json.dumps(res, indent=1, default=float))
    print(f"\nwrote {OUT / 'phase9.json'} and figures/p9_*.png")


def figures(days, model, market, roll, events, ll, wm, track):
    fig, ax = plt.subplots(figsize=(11, 4.5))
    ax.plot(days, market, color="k", lw=1.6, label="Kalshi KXGTEMP-26 price")
    ax.plot(days, model, color="C3", lw=1.6, label="model, using only data available that day")
    for e in events:
        ax.axvline(date.fromisoformat(e["date"]), color="grey", lw=0.6, ls=":")
    ax.set(ylim=(0, 1), ylabel="P(2026 is GISS's hottest year)", title="Did the market track the data? (dotted: assumed GISS release days)")
    ax.legend(fontsize=8)
    fig.autofmt_xdate()
    fig.tight_layout(); fig.savefig(FIG / "p9_1_kxgtemp_vs_model.png", dpi=130); plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 3.8))
    ks = list(ll)
    ax.bar(ks, [ll[k] for k in ks], color=["C3" if k > 0 else ("k" if k == 0 else "C0") for k in ks])
    ax.axhline(0, color="k", lw=0.5)
    ax.set(xlabel="lag k (days); k > 0: model moves first", ylabel="corr of daily changes",
           title="Lead-lag between model and market (KXGTEMP-26)")
    fig.tight_layout(); fig.savefig(FIG / "p9_2_lead_lag.png", dpi=130); plt.close(fig)

    wd, wp, wv, _ = wm
    fig, ax = plt.subplots(figsize=(11, 4.5))
    ax.plot(wd, wp, color="k", lw=1.4, label="Kalshi KXWARMING-50 price")
    ax2 = ax.twinx()
    ax2.bar(wd, wv, color="grey", alpha=0.3, width=1)
    ax2.set_ylabel("contracts traded", color="grey")
    ax.axvline(SWEEP, color="C1", ls="--", lw=1)
    ax.annotate("22 Sep 2026: one order\nswept the book", (SWEEP, 0.55), textcoords="offset points", xytext=(6, 0), fontsize=8, color="C1")
    if track:
        tt = [datetime.fromisoformat(t["time"]).date() for t in track]
        ax.plot(tt, [t["model_ipcc"] for t in track], "o", color="C3", label="model (IPCC view), each pipeline run")
    ax.set(ylim=(0.4, 1.0), ylabel="Yes price / probability", title="KXWARMING-50 since listing")
    ax.legend(fontsize=8, loc="lower left")
    fig.autofmt_xdate()
    fig.tight_layout(); fig.savefig(FIG / "p9_3_kxwarming_history.png", dpi=130); plt.close(fig)


if __name__ == "__main__":
    main()
