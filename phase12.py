"""Phase 12 (class project): can small, regular trades make money on KXWARMING-50?

    python phase12.py      # results/phase12.json, figures/p12_*.png

HYPOTHETICAL ONLY: a classroom back-test on Kalshi's public price history. Not investment advice.

Three "small constant" methods, each $10 a week from the day the market listed (June 2025):
  1. Weekly buy at the ask        dollar-cost averaging; pays the taker fee (rounded up per order)
  2. Weekly limit order           a resting bid one cent above the best bid; fills only if a trade happens
                                  at or below it within the week; makers pay no fee on this market
  3. Spread capture               rest a bid (best bid + 1c) and an offer (best ask - 1c) each week for
                                  10 contracts; profit when both sides fill (buy low, sell high)
Each is valued two ways: expected profit if held to settlement (under our 80.8% ensemble estimate and
under the 67.1% IPCC-calibrated estimate), and what you'd get selling today at the bid.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from market import fee, latest_snapshot

HERE = Path(__file__).resolve().parent
FIG = HERE / "figures"
OUT = HERE / "results"
CANDLES = HERE / "data" / "market" / "candles" / "KXWARMING-50.json"
WEEKLY = 10.0          # dollars per week
SPREAD_SIZE = 10       # contracts per side for spread capture


def f(x):
    return float(x) if x not in (None, "") else float("nan")


def load_days():
    rows = []
    for c in json.loads(CANDLES.read_text()):
        rows.append({"date": datetime.fromtimestamp(c["end_period_ts"], timezone.utc).date(),
                     "bid": f(c.get("yes_bid", {}).get("close_dollars")), "ask": f(c.get("yes_ask", {}).get("close_dollars")),
                     "low": f(c.get("price", {}).get("low_dollars")), "high": f(c.get("price", {}).get("high_dollars")),
                     "vol": f(c.get("volume_fp")) or 0.0})
    rows.sort(key=lambda r: r["date"])
    return rows


def backtest(days, mid_now, bid_now):
    weeks = list(range(0, len(days), 7))
    dca = {"contracts": 0, "spent": 0.0, "fees": 0.0, "orders": 0, "buys": []}
    lim = {"contracts": 0, "spent": 0.0, "fees": 0.0, "orders": 0, "filled": 0, "buys": []}
    spr = {"bought": 0, "sold": 0, "cash": 0.0, "inventory": 0, "round_trips": 0}
    for w in weeks:
        d = days[w]
        win = days[w:w + 7]
        a, b = d["ask"], d["bid"]
        if not (0 < a < 1) or not (0 < b < 1):
            continue
        # 1. buy at the ask
        n = max(1, math.floor(WEEKLY / (a + 0.02)))
        fe = fee(a, n)
        dca["contracts"] += n
        dca["spent"] += n * a + fe
        dca["fees"] += fe
        dca["orders"] += 1
        dca["buys"].append((d["date"].isoformat(), a, n))
        # 2. resting bid one cent above the best bid (maker: no fee); fills if a trade prints at or below it
        px = round(min(b + 0.01, a - 0.01), 2)
        n2 = max(1, math.floor(WEEKLY / px))
        lim["orders"] += 1
        lows = [x["low"] for x in win if x["low"] == x["low"]]
        vol = sum(x["vol"] for x in win)
        if lows and min(lows) <= px + 1e-9 and vol >= n2:
            lim["contracts"] += n2
            lim["spent"] += n2 * px
            lim["filled"] += 1
            lim["buys"].append((d["date"].isoformat(), px, n2))
        # 3. spread capture: bid at b+1c, offer at a-1c, 10 contracts each side
        pb, pa = round(min(b + 0.01, a - 0.02), 2), round(max(a - 0.01, b + 0.02), 2)
        highs = [x["high"] for x in win if x["high"] == x["high"]]
        if lows and min(lows) <= pb + 1e-9 and vol >= SPREAD_SIZE:
            spr["bought"] += SPREAD_SIZE
            spr["inventory"] += SPREAD_SIZE
            spr["cash"] -= SPREAD_SIZE * pb
        if highs and max(highs) >= pa - 1e-9 and spr["inventory"] >= SPREAD_SIZE and vol >= SPREAD_SIZE:
            spr["sold"] += SPREAD_SIZE
            spr["inventory"] -= SPREAD_SIZE
            spr["cash"] += SPREAD_SIZE * pa
            spr["round_trips"] += 1
    return dca, lim, spr


def value(pos, p_ens, p_ipcc, bid_now):
    n, s = pos["contracts"], pos["spent"]
    return {"contracts": n, "spent": s, "avg_cost": s / n if n else float("nan"),
            "expected_profit_ensemble": n * p_ens - s, "expected_profit_ipcc": n * p_ipcc - s,
            "sell_now_at_bid": n * bid_now - fee(bid_now, n) - s if n else 0.0,
            "fees": pos.get("fees", 0.0), "orders": pos["orders"], "filled_orders": pos.get("filled", pos["orders"])}


def main():
    FIG.mkdir(exist_ok=True)
    OUT.mkdir(exist_ok=True)
    snap = latest_snapshot()
    p11 = json.loads((OUT / "phase11.json").read_text())
    p10 = json.loads((OUT / "phase10.json").read_text())
    p_ens = p11["ensemble"]["p_yes"]
    p_ipcc = p10["variants"]["ipcc"]["p_yes"]
    p_hist = p10["variants"]["history"]["p_yes"]
    p_class = p10["variants"]["class_hw5"]["p_yes"]
    mid, bid, ask = snap["mid"], snap["yes_bid"], snap["yes_ask"]
    days = load_days()
    dca, lim, spr = backtest(days, mid, bid)
    v_dca, v_lim = value(dca, p_ens, p_ipcc, bid), value(lim, p_ens, p_ipcc, bid)
    spread = {**{k: v for k, v in spr.items()}, "inventory_value_at_bid": spr["inventory"] * bid,
              "profit_marked_at_bid": spr["cash"] + spr["inventory"] * bid,
              "expected_profit_ensemble": spr["cash"] + spr["inventory"] * p_ens,
              "expected_profit_ipcc": spr["cash"] + spr["inventory"] * p_ipcc}
    fee_table = [{"contracts": n, "fee": fee(ask, n), "fee_per_contract": fee(ask, n) / n} for n in (1, 2, 5, 10, 25, 100)]
    # going forward: $10/week for a year at today's prices
    fwd = {}
    for name, px, fe_per in (("buy at the ask", ask, fee(ask, 13) / 13), ("limit order at the bid + 1c", bid + 0.01, 0.0)):
        n = 52 * math.floor(WEEKLY / (px + fe_per))
        cost = n * (px + fe_per)
        fwd[name] = {"price": px, "all_in": px + fe_per, "contracts_per_year": n, "spent": cost,
                     "expected_ensemble": n * p_ens - cost, "expected_ipcc": n * p_ipcc - cost,
                     "break_even_probability": px + fe_per}
    weekly_volume = float(np.mean([sum(d["vol"] for d in days[i:i + 7]) for i in range(0, len(days), 7)]))
    res = {"snapshot": snap["dir"], "hypothetical": True, "weekly_dollars": WEEKLY,
           "estimates": {"kalshi_mid": mid, "kalshi_bid": bid, "kalshi_ask": ask, "ensemble": p_ens, "ipcc": p_ipcc,
                         "history": p_hist, "class_hw5": p_class, "kalshi_band": p11.get("kalshi") and None},
           "period": [days[0]["date"].isoformat(), days[-1]["date"].isoformat()],
           "dca_at_ask": v_dca, "limit_orders": v_lim, "spread_capture": spread,
           "fee_by_order_size": fee_table, "forward_one_year": fwd, "avg_weekly_volume": weekly_volume}
    b10 = json.loads((OUT / "phase10.json").read_text())["kalshi"]["band"]
    res["estimates"]["kalshi_band"] = b10

    # ---------------------------------------------------------------- print
    print("\nHYPOTHETICAL back-test: $10 a week on KXWARMING-50", res["period"])
    print(f"  estimates: ours (ensemble) {p_ens:.1%}, IPCC-calibrated {p_ipcc:.1%}, Kalshi mid {mid:.1%} (bid {bid:.2f} / ask {ask:.2f})")
    for name, v in (("1. weekly buy at the ask", v_dca), ("2. weekly limit order (bid + 1c)", v_lim)):
        print(f"  {name}: {v['filled_orders']}/{v['orders']} orders filled, {v['contracts']} contracts for ${v['spent']:.2f} "
              f"(avg {v['avg_cost']:.3f}, fees ${v['fees']:.2f})")
        print(f"       expected at settlement: ${v['expected_profit_ensemble']:+.2f} with our 80.8% | ${v['expected_profit_ipcc']:+.2f} with IPCC 67.1% | "
              f"sell today at the bid: ${v['sell_now_at_bid']:+.2f}")
    s = spread
    print(f"  3. spread capture: bought {s['bought']}, sold {s['sold']} ({s['round_trips']} round trips), cash ${s['cash']:+.2f}, "
          f"inventory {s['inventory']} -> marked at bid ${s['profit_marked_at_bid']:+.2f}")
    print("  fee per contract by order size at the ask: " + ", ".join(f"{r['contracts']}: {r['fee_per_contract'] * 100:.2f}c" for r in fee_table))
    print(f"  average weekly volume {weekly_volume:.0f} contracts")
    for k, v in fwd.items():
        print(f"  next 12 months, {k}: {v['contracts_per_year']} contracts for ${v['spent']:.0f} -> expected ${v['expected_ensemble']:+.0f} (ours) / "
              f"${v['expected_ipcc']:+.0f} (IPCC); break-even needs P > {v['break_even_probability']:.1%}")
    figures(res, days, dca, lim)
    (OUT / "phase12.json").write_text(json.dumps(res, indent=1, default=float))
    print(f"\nwrote {OUT / 'phase12.json'} and figures/p12_*.png")


def figures(res, days, dca, lim):
    e = res["estimates"]
    # 0. the headline comparison
    fig, ax = plt.subplots(figsize=(10, 4.6))
    items = [("Kalshi market\n(mid price)", e["kalshi_mid"], "#111827"), ("IPCC-calibrated\nmodel", e["ipcc"], "#dc2626"),
             ("Our ensemble\n(72 versions, mean)", e["ensemble"], "#ea580c"), ("Fitted to\nhistory", e["history"], "#2563eb"),
             ("Class model\nas taught", e["class_hw5"], "#7c3aed")]
    x = np.arange(len(items))
    bars = ax.bar(x, [v * 100 for _, v, _ in items], color=[c for _, _, c in items], width=0.6)
    ax.axhspan(e["kalshi_band"][0] * 100, e["kalshi_band"][1] * 100, color="#eab308", alpha=0.25,
               label=f"Kalshi range after fees ({e['kalshi_band'][0]:.0%}-{e['kalshi_band'][1]:.0%})")
    for b, (_, v, _) in zip(bars, items):
        ax.annotate(f"{v:.0%}", (b.get_x() + b.get_width() / 2, v * 100), ha="center", va="bottom", fontsize=12, fontweight="bold")
    ax.set_xticks(x, [n for n, _, _ in items], fontsize=9)
    ax.set(ylim=(0, 108), ylabel="P(any year ≥ 2°C before 2050), %",
           title="Our model says ~80%; once uncertainty is IPCC-sized it lands on Kalshi's ~70%")
    ax.legend(fontsize=8, loc="upper left")
    fig.tight_layout(); fig.savefig(FIG / "p12_0_estimates.png", dpi=130); plt.close(fig)

    # 1. weekly buys over the price history
    fig, ax = plt.subplots(figsize=(11, 4.6))
    dd = [d["date"] for d in days]
    ax.plot(dd, [d["ask"] for d in days], color="#6b7280", lw=1, label="Yes ask (daily close)")
    ax.plot(dd, [d["bid"] for d in days], color="#9ca3af", lw=1, ls=":", label="Yes bid")
    bx = [datetime.fromisoformat(t).date() for t, _, _ in dca["buys"]]
    ax.scatter(bx, [p for _, p, _ in dca["buys"]], s=14, color="#dc2626", label="weekly buy at the ask", zorder=3)
    lx = [datetime.fromisoformat(t).date() for t, _, _ in lim["buys"]]
    ax.scatter(lx, [p for _, p, _ in lim["buys"]], s=14, color="#2563eb", marker="s", label="limit order filled", zorder=3)
    ax.axhline(e["ensemble"], color="#ea580c", ls="--", lw=1.4, label=f"our estimate {e['ensemble']:.0%}")
    ax.axhline(e["ipcc"], color="#dc2626", ls="--", lw=1.4, label=f"IPCC-calibrated {e['ipcc']:.0%}")
    ax.set(ylim=(0.5, 0.95), ylabel="price / probability", title="$10 a week since listing: what we'd have paid")
    ax.legend(fontsize=7, ncol=2)
    fig.autofmt_xdate()
    fig.tight_layout(); fig.savefig(FIG / "p12_1_weekly_buys.png", dpi=130); plt.close(fig)

    # 2. expected profit by method and belief
    fig, ax = plt.subplots(figsize=(10, 4.6))
    names = ["Weekly buy\nat the ask", "Weekly limit\norder (no fee)", "Spread\ncapture"]
    ens = [res["dca_at_ask"]["expected_profit_ensemble"], res["limit_orders"]["expected_profit_ensemble"], res["spread_capture"]["expected_profit_ensemble"]]
    ipc = [res["dca_at_ask"]["expected_profit_ipcc"], res["limit_orders"]["expected_profit_ipcc"], res["spread_capture"]["expected_profit_ipcc"]]
    now = [res["dca_at_ask"]["sell_now_at_bid"], res["limit_orders"]["sell_now_at_bid"], res["spread_capture"]["profit_marked_at_bid"]]
    x = np.arange(3)
    for off, vals, col, lab in ((-0.27, ens, "#ea580c", "held to 2050, if our 81% is right"),
                                (0.0, ipc, "#dc2626", "held to 2050, if the IPCC 67% is right"),
                                (0.27, now, "#6b7280", "sold today at the bid")):
        bs = ax.bar(x + off, vals, 0.26, color=col, label=lab)
        for b, v in zip(bs, vals):
            ax.annotate(f"${v:+.0f}", (b.get_x() + b.get_width() / 2, v), ha="center", va="bottom" if v >= 0 else "top", fontsize=8)
    ax.axhline(0, color="k", lw=0.8)
    ax.set_xticks(x, names)
    ax.set(ylabel="profit / loss ($)", title=f"Small regular trades since {res['period'][0]}: it depends entirely on whose probability is right")
    ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(FIG / "p12_2_methods.png", dpi=130); plt.close(fig)

    # 3. fee per contract by order size
    fig, ax = plt.subplots(figsize=(8, 4))
    ft = res["fee_by_order_size"]
    ax.bar([str(r["contracts"]) for r in ft], [r["fee_per_contract"] * 100 for r in ft], color="#6b7280")
    for i, r in enumerate(ft):
        ax.annotate(f"{r['fee_per_contract'] * 100:.2f}¢", (i, r["fee_per_contract"] * 100), ha="center", va="bottom", fontsize=9)
    ax.set(xlabel="contracts per order", ylabel="fee per contract (cents)",
           title="Kalshi rounds each order's fee up to the cent: tiny orders pay more")
    fig.tight_layout(); fig.savefig(FIG / "p12_3_fees.png", dpi=130); plt.close(fig)


if __name__ == "__main__":
    main()
