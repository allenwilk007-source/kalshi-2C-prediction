"""Phase 4: what probability does Kalshi's price imply, and how does the model compare on the same footing?

    python phase4.py            # uses the latest cached snapshot (python market.py fetches a new one)

Analysis only: expected-return numbers describe the model vs the market, not a recommendation.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import pricing as pc
from market import fee, latest_snapshot, trade_series, walk_book
from model import Inputs
from phase3 import SPECS, climate_posteriors, kaya_setup, run_cell, setup

HERE = Path(__file__).resolve().parent
FIG = HERE / "figures"
OUT = HERE / "results"
SIZES = (1, 10, 100, 500, 1000)
HAIRCUTS = (0.0, 0.02, 0.05, 0.10)
CELLS = [k for k, (kind, wsd) in SPECS.items() if not (kind == "template" or (kind == "kaya" and wsd is None))]
HEADLINE = "Kaya randomised + 2019-24 weighting"


def wmean(x, w):
    return float((w * x).sum() / w.sum())


def main():
    FIG.mkdir(exist_ok=True)
    OUT.mkdir(exist_ok=True)
    snap = latest_snapshot()
    today = pc.year_fraction(datetime.fromisoformat(snap["fetched_utc"]))
    tn, apy = snap["treasury_nominal"], snap["kalshi_apy"]
    deltas = {
        "0: vs cash on Kalshi": 0.0,
        "T-bill - Kalshi APY": tn["1 Mo"] - apy,
        "20y Treasury - Kalshi APY": tn["20 Yr"] - apy,
        "T-bill, no APY": tn["1 Mo"],
        "20y Treasury, no APY": tn["20 Yr"],
    }
    D_HEAD = "T-bill - Kalshi APY"

    # ---------------------------------------------------------- market side
    book = {n: {"yes": walk_book(snap["yes_asks"], n), "no": walk_book(snap["no_asks"], n)} for n in SIZES}
    costs = {"top of book (10)": (book[10]["yes"]["all_in_per_contract"], book[10]["no"]["all_in_per_contract"]),
             "100 contracts": (book[100]["yes"]["all_in_per_contract"], book[100]["no"]["all_in_per_contract"])}

    # ---------------------------------------------------------- model cells
    inp = Inputs.load()
    st = setup(inp)
    posts, _, _ = climate_posteriors(st["grid"])
    ks = kaya_setup(st, inp)
    cells = {}
    for cv in ("history", "ipcc"):
        for label in CELLS:
            kind, wsd = SPECS[label]
            out, _ = run_cell(st, posts[cv], kind, ks, wsd, inp=inp)
            w, yes, first = out["w"], out["yes"], out["first"]
            c = {"p_yes_2049": wmean(yes, w), "p_yes_2048": wmean(np.nan_to_num(first, nan=9999) <= 2048, w)}
            c["p_only_2049"] = c["p_yes_2049"] - c["p_yes_2048"]
            c["mean_tau_yes"] = pc.mean_tau_yes(first, w, today)
            c["DY"] = {k: pc.discount_yes(first, w, d, today) for k, d in deltas.items()}
            c["_first"], c["_w"] = first, w
            cells[(label, cv)] = c
    head = cells[(HEADLINE, "ipcc")]
    DN = {k: pc.discount_no(d, today) for k, d in deltas.items()}
    tauN = pc.tau_no(today)

    # ---------------------------------------------------------- implied probabilities
    implied = {}
    for k in deltas:
        DY = head["DY"][k]
        implied[k] = {q: pc.implied_q(snap[f], DY, DN[k]) for q, f in (("bid", "yes_bid"), ("mid", "mid"), ("ask", "yes_ask"))}
        implied[k]["DY_range_across_cells"] = [min(c["DY"][k] for c in cells.values()), max(c["DY"][k] for c in cells.values())]
        implied[k]["DY"], implied[k]["DN"] = DY, DN[k]
    bands = {}
    for cname, (yc, nc) in costs.items():
        for k in deltas:
            for h in HAIRCUTS:
                bands[(cname, k, h)] = pc.no_trade_band(yc, nc, head["DY"][k], DN[k], h)

    # ---------------------------------------------------------- model vs market
    vs = {}
    yc, nc = costs["top of book (10)"]
    for (label, cv), c in cells.items():
        row = {}
        for k in ("0: vs cash on Kalshi", D_HEAD):
            DY = c["DY"][k]
            lo, hi = pc.no_trade_band(yc, nc, DY, DN[k])
            P = c["p_yes_2049"]
            row[k] = {
                "fair_price": pc.price_for_q(P, DY, DN[k]),
                "band": [lo, hi],
                "position": "above band (model > market)" if P > hi else ("below band (model < market)" if P < lo else "inside band"),
                "yes_side": pc.side_expected_return(P, DY, yc, c["mean_tau_yes"]),
                "no_side": pc.side_expected_return(1 - P, DN[k], nc, tauN),
            }
        vs[f"{label} | {cv}"] = {"p_yes_2049": c["p_yes_2049"], "p_yes_2048": c["p_yes_2048"],
                                 "p_only_2049": c["p_only_2049"], "mean_tau_yes": c["mean_tau_yes"], **row}

    # ---------------------------------------------------------- price history
    days, vwap, vol = trade_series(snap["trades"])
    last30 = days >= (days[-1] - np.timedelta64(30, "D"))
    hist = {"n_trades": len(snap["trades"]), "first_day": str(days[0]), "last_day": str(days[-1]),
            "contracts_in_api_history": float(vol.sum()), "lifetime_volume": snap["volume"],
            "vwap_first_day": float(vwap[0]), "vwap_last_day": float(vwap[-1]),
            "vwap_min": float(vwap.min()), "vwap_max": float(vwap.max()),
            "vwap_last_30d": float((vwap[last30] * vol[last30]).sum() / vol[last30].sum())}

    # ---------------------------------------------------------- print
    print(f"\nSnapshot {snap['dir']} (fetched {snap['fetched_utc']}); today = {today:.3f}")
    print(f"  Yes bid/ask {snap['yes_bid']:.2f}/{snap['yes_ask']:.2f}, mid {snap['mid']:.3f}, last {snap['last']:.2f}; "
          f"open interest {snap['open_interest']:.0f}; lifetime volume {snap['volume']:.0f}")
    print(f"  Treasury {tn['date']}: 1m {tn['1 Mo']:.2%}, 20y {tn['20 Yr']:.2%}; Kalshi APY {apy:.2%} (variable)")
    print(f"  Fee: 1 contract @0.69 = ${fee(0.69, 1):.2f}; 100 @0.69 = ${fee(0.69, 100):.2f}")
    print("\nCost to enter (all-in per contract, incl. fee):")
    print(f"  {'contracts':>9s} {'buy Yes':>9s} {'buy No':>9s}")
    for n in SIZES:
        y, no = book[n]["yes"], book[n]["no"]
        print(f"  {n:9d} {y['all_in_per_contract']:9.4f} {no['all_in_per_contract']:9.4f}"
              + ("" if y["complete"] and no["complete"] else "  (book too thin)"))

    print(f"\nPayment timing: Yes pays ~{head['mean_tau_yes']:.1f} yrs from now on average (IPCC headline); "
          f"No pays in {tauN:.1f} yrs")
    print("\nImplied probability q* (equal expected return on both sides):")
    print(f"  {'carry delta':28s} {'rate':>6s} {'D_Y':>6s} {'D_N':>6s} {'bid':>6s} {'mid':>6s} {'ask':>6s}")
    for k, d in deltas.items():
        r = implied[k]
        print(f"  {k:28s} {d:6.2%} {r['DY']:6.3f} {r['DN']:6.3f} {r['bid']:6.3f} {r['mid']:6.3f} {r['ask']:6.3f}")

    print("\nTrading band after fees and spread (beliefs where neither side beats the carry baseline):")
    for cname in costs:
        for k in deltas:
            lo, hi = bands[(cname, k, 0.0)]
            print(f"  {cname:17s} {k:28s} [{lo:.3f}, {hi:.3f}]")
    print("  Platform haircut h (both payouts x (1-h)), top of book, delta 0: " + "; ".join(
        f"h={h:.0%} [{bands[('top of book (10)', '0: vs cash on Kalshi', h)][0]:.3f}, "
        f"{bands[('top of book (10)', '0: vs cash on Kalshi', h)][1]:.3f}]" for h in HAIRCUTS))

    print(f"\nModel vs market (top-of-book costs; delta = 0 and {D_HEAD}):")
    print(f"  {'cell':52s} {'P(<=2049)':>9s} {'P(<=2048)':>9s} {'fair@0':>7s} {'fair@d':>7s}  position (delta 0)")
    for name, r in vs.items():
        print(f"  {name:52s} {r['p_yes_2049']:9.3f} {r['p_yes_2048']:9.3f} {r['0: vs cash on Kalshi']['fair_price']:7.3f} "
              f"{r[D_HEAD]['fair_price']:7.3f}  {r['0: vs cash on Kalshi']['position']}")
    print("\n  Expected annualised excess return of each side under each model (delta 0; analysis, not advice):")
    for name, r in vs.items():
        y, n = r["0: vs cash on Kalshi"]["yes_side"], r["0: vs cash on Kalshi"]["no_side"]
        print(f"  {name:52s} Yes {y['annualised_excess']:+7.2%}/yr  No {n['annualised_excess']:+7.2%}/yr")

    print(f"\nPrice history (public API returns {hist['n_trades']} trades, {hist['first_day']} to {hist['last_day']}; "
          f"{hist['contracts_in_api_history']:.0f} of {hist['lifetime_volume']:.0f} lifetime contracts):")
    print(f"  daily VWAP {hist['vwap_first_day']:.3f} -> {hist['vwap_last_day']:.3f}; range {hist['vwap_min']:.3f}-{hist['vwap_max']:.3f}; "
          f"last-30-day VWAP {hist['vwap_last_30d']:.3f}")

    figures(snap, book, cells, bands, deltas, implied, head, today, (days, vwap, vol), DN)

    results = {
        "snapshot": {k: snap[k] for k in ("dir", "fetched_utc", "yes_bid", "yes_ask", "mid", "last",
                                          "open_interest", "volume", "close_time", "latest_expiration_time")},
        "today": today, "deltas": deltas, "kalshi_apy": apy, "treasury": tn,
        "book": {str(n): v for n, v in book.items()},
        "implied_q": implied,
        "bands": {f"{c} | {k} | h={h}": v for (c, k, h), v in bands.items()},
        "model_vs_market": vs, "price_history": hist,
    }
    (OUT / "phase4.json").write_text(json.dumps(results, indent=1, default=float))
    print(f"\nwrote {OUT / 'phase4.json'} and figures/p4_*.png")


def figures(snap, book, cells, bands, deltas, implied, head, today, hist, DN):
    lo, hi = bands[("top of book (10)", "0: vs cash on Kalshi", 0.0)]

    # 1 price history
    days, vwap, vol = hist
    fig, ax = plt.subplots(figsize=(10, 4.5))
    ax.scatter(days, vwap, s=10 + 3 * np.sqrt(vol), color="k", alpha=0.6, label="daily VWAP (size = volume)")
    ax.axhspan(lo, hi, color="orange", alpha=0.25, label=f"current band after costs [{lo:.3f}, {hi:.3f}]")
    for cv, col in (("history", "C0"), ("ipcc", "C3")):
        p = cells[(HEADLINE, cv)]["p_yes_2049"]
        ax.axhline(p, color=col, lw=1.5, ls="--", label=f"model {cv}: {p:.3f}")
    ax.set(title="KXWARMING-50 trades vs model", ylabel="Yes price / probability", ylim=(0.5, 1.0))
    ax.legend(fontsize=8)
    fig.autofmt_xdate()
    fig.tight_layout(); fig.savefig(FIG / "p4_1_price_history.png", dpi=130); plt.close(fig)

    # 2 depth / cost to enter
    fig, ax = plt.subplots(figsize=(9, 4))
    sizes = np.unique(np.concatenate([np.arange(1, 50, 1), np.arange(50, 1501, 25)]))
    for side, col in (("yes_asks", "C3"), ("no_asks", "C0")):
        ys = [walk_book(snap[side], n) for n in sizes]
        ok = [r["complete"] for r in ys]
        ax.plot(sizes[ok], [r["all_in_per_contract"] for r, k in zip(ys, ok) if k], color=col,
                label=f"buy {'Yes' if side == 'yes_asks' else 'No'} (all-in per contract)")
    ax.set(xscale="log", xlabel="contracts", ylabel="$ per contract", title="Cost to enter vs size (thin book)")
    ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(FIG / "p4_2_depth.png", dpi=130); plt.close(fig)

    # 3 implied q vs delta
    fig, ax = plt.subplots(figsize=(9, 4))
    ds = np.linspace(0, 0.06, 61)
    f, w = head["_first"], head["_w"]
    for key, col in (("yes_bid", "C0"), ("mid", "k"), ("yes_ask", "C3")):
        qs = [pc.implied_q(snap[key], pc.discount_yes(f, w, d, today), pc.discount_no(d, today)) for d in ds]
        ax.plot(ds * 100, qs, color=col, label=key)
    for k, d in deltas.items():
        ax.axvline(d * 100, color="grey", lw=0.6, ls=":")
        ax.text(d * 100, 0.585, k, rotation=90, fontsize=6, va="bottom")
    ax.set(xlabel="carry delta, % per year", ylabel="implied probability q*", title="Implied probability vs cost of tying up capital")
    ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(FIG / "p4_3_implied_vs_delta.png", dpi=130); plt.close(fig)

    # 4 model cells vs band
    fig, ax = plt.subplots(figsize=(10, 5))
    names = [f"{l} | {cv}" for (l, cv) in cells]
    for i, ((l, cv), c) in enumerate(cells.items()):
        col = "C0" if cv == "history" else "C3"
        ax.plot(c["p_yes_2049"], i, "o", color=col)
        ax.plot(c["p_yes_2048"], i, "o", mfc="none", color=col)
    ax.axvspan(lo, hi, color="orange", alpha=0.3, label="market band after costs (delta 0)")
    ax.axvline(snap["mid"], color="k", lw=1, label=f"mid {snap['mid']:.2f}")
    ax.set_yticks(range(len(names)), names, fontsize=7)
    ax.set(xlabel="P(Yes)", xlim=(0.3, 1.0), title="Model P(Yes) (filled: years <= 2049, hollow: <= 2048) vs market")
    ax.legend(fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=2)
    fig.tight_layout(); fig.savefig(FIG / "p4_4_model_vs_band.png", dpi=130); plt.close(fig)

    # 5 payment timing
    fig, ax = plt.subplots(figsize=(9, 4))
    m = np.isfinite(f)
    ax.hist(pc.tau_yes(f[m], today), bins=np.arange(0, 25, 1), weights=w[m] / w.sum(), color="C3", alpha=0.6,
            label="Yes paid (IPCC headline)")
    ax.axvline(pc.tau_no(today), color="C0", lw=2, label="No paid (expiry)")
    ax.set(xlabel="years from now", ylabel="share of paths", title="When each side gets paid")
    ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(FIG / "p4_5_payment_timing.png", dpi=130); plt.close(fig)


if __name__ == "__main__":
    main()
