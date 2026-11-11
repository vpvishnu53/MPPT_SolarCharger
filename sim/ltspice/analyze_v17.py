"""Dead-time / shoot-through analysis of LTspice v1.7 (SimFiles/mppt_sim_1.7.raw/.log).

Run from the repo root after LTspice has produced the v1.7 .raw:
    sim/sil/.venv/Scripts/python sim/ltspice/analyze_v17.py

Metrics per step, taken on the switching period that starts at t = 9.98 ms (the circuit has settled):
  margin_A_ns : edge A (M1 turns off -> M2 turns on). Time from the LAST fall of M1's internal Vgs below Vth
                to the FIRST rise of M2's internal Vgs above Vth. Negative = both channels on.
  margin_B_ns : edge B (M2 turns off -> M1 turns on), same definition with the roles swapped.
                Using "last fall of the outgoing gate" means a Miller kick that re-lifts the outgoing gate
                above Vth after the incoming one is on correctly shows up as a negative margin.
  overlap_ns  : total time in the period with BOTH internal Vgs > Vth (direct shoot-through indicator).
  kick_L_V    : peak low-side internal Vgs in the 500 ns after the high side is commanded on (Miller kick).
  kick_H_V    : peak high-side internal Vgs-source in the 500 ns after the low side is commanded on.
Vth = 3.73 V is the vendor model's VTO; the internal gate is node 7 of the vendor subcircuit, i.e. after its
3.97 ohm internal gate resistance.
"""
import csv
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "sim"))

import plotstyle as ps  # noqa: E402
from ltspice_raw import parse_meas_log, read_raw  # noqa: E402

import matplotlib.pyplot as plt  # noqa: E402

ps.apply()
SIM = os.path.join(ROOT, "SimFiles")
OUT = os.path.join(HERE, "results")
TSW, DEAD, VTH, P0 = 10e-6, 200e-9, 3.73, 9.98e-3


def crossings(t, v, level, rising):
    a, b = v[:-1] - level, v[1:] - level
    idx = np.where((a < 0) & (b >= 0))[0] if rising else np.where((a >= 0) & (b < 0))[0]
    frac = (level - v[idx]) / (v[idx + 1] - v[idx])
    return t[idx] + frac * (t[idx + 1] - t[idx])


def edge_margin(t, v_out, v_in, t0, t1):
    w = (t >= t0) & (t <= t1)
    falls = crossings(t[w], v_out[w], VTH, rising=False)
    rises = crossings(t[w], v_in[w], VTH, rising=True)
    if len(rises) == 0:
        return float("nan")
    if len(falls) == 0:                       # outgoing gate never dropped below Vth in the window
        return -1e3 * (t1 - t0) * 1e6         # report as a large negative number (whole window overlapped)
    return (rises[0] - falls[-1]) * 1e9


def analyse():
    names, steps = read_raw(os.path.join(SIM, "mppt_sim_1.7.raw"))
    params, meas = parse_meas_log(os.path.join(SIM, "mppt_sim_1.7.log"))
    assert len(steps) == len(params)
    rows = []
    for i, (s, p) in enumerate(zip(steps, params)):
        rg, corner, cfg = float(p["rg"]), int(float(p["corner"])), int(float(p["cfg"]))
        case, split = cfg % 2, cfg // 2
        duty = 0.66 if case else 0.68
        ton = 94e-9 if corner else 120e-9
        t = s["time"]
        vh = s["V(m1:x1:7)"] - s["V(sw)"]
        vl = s["V(m2:x1:7)"]
        per = (t >= P0) & (t < P0 + TSW)
        tp, both = t[per], (vh[per] > VTH) & (vl[per] > VTH)
        overlap = float(np.sum(np.diff(tp)[both[:-1]])) * 1e9
        tA = P0 + duty * TSW
        mA = edge_margin(t, vh, vl, tA, tA + 1e-6)
        tB = P0 + TSW - DEAD
        mB = edge_margin(t, vl, vh, tB - 0.3e-6, tB + 1.0e-6)
        kl = (t >= P0 + TSW + ton) & (t <= P0 + TSW + ton + 0.5e-6)
        kh = (t >= tA + DEAD + ton) & (t <= tA + DEAD + ton + 0.5e-6)
        rows.append({
            "rg_ohm": rg, "corner": "pessimistic" if corner else "typical",
            "point": "14.4V D=0.66" if case else "12V D=0.68 (MPP)",
            "network": "split (Rg on, 1R+diode off)" if split else "symmetric Rg",
            "margin_A_ns": mA, "margin_B_ns": mB, "overlap_ns": overlap,
            "kick_L_V": float(vl[kl].max()), "kick_H_V": float(vh[kh].max()),
            "eff_total_pct": meas["eff"][i], "eff_conv_pct": meas["effconv"][i],
            "pin_W": meas["pin"][i], "il_avg_A": float(np.mean(s["I(L)"][per])),
        })
    with open(os.path.join(OUT, "ltspice_v1.7_deadtime.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        for r in rows:
            w.writerow({k: (f"{v:.4g}" if isinstance(v, float) else v) for k, v in r.items()})
    return rows, steps, params


def plot_summary(rows):
    fig, ax = plt.subplots(2, 2, figsize=(11, 7.5), sharex=True)
    combos = [("symmetric Rg", "typical", ps.C[1], "-o"), ("symmetric Rg", "pessimistic", ps.C[1], "--s"),
              ("split (Rg on, 1R+diode off)", "typical", ps.C[0], "-o"),
              ("split (Rg on, 1R+diode off)", "pessimistic", ps.C[0], "--s")]
    pt = "12V D=0.68 (MPP)"
    for net, cor, col, sty in combos:
        rr = sorted([r for r in rows if r["network"] == net and r["corner"] == cor and r["point"] == pt],
                    key=lambda r: r["rg_ohm"])
        x = [r["rg_ohm"] for r in rr]
        lab = f"{'split' if net.startswith('split') else 'symmetric'}, {cor}"
        ax[0, 0].plot(x, [max(r["margin_A_ns"], -400) for r in rr], sty, color=col, ms=5, label=lab)
        ax[0, 1].plot(x, [max(r["margin_B_ns"], -400) for r in rr], sty, color=col, ms=5, label=lab)
        ax[1, 0].plot(x, [r["kick_L_V"] for r in rr], sty, color=col, ms=5, label=lab)
        ax[1, 1].plot(x, [max(r["eff_conv_pct"], 80) for r in rr], sty, color=col, ms=5, label=lab)
    for a in (ax[0, 0], ax[0, 1]):
        a.axhline(0, color=ps.REF, lw=1)
        a.axhspan(-420, 0, color="#e34948", alpha=0.06)
        a.set_ylim(-420, 250)
    ax[0, 0].set_title("edge A: M1 off -> M2 on", fontsize=10)
    ax[0, 1].set_title("edge B: M2 off -> M1 on", fontsize=10)
    ax[0, 0].set_ylabel("margin (ns), < 0 = shoot-through")
    ax[1, 0].axhline(VTH, color=ps.REF, lw=1, ls="--")
    ax[1, 0].text(0.3, VTH + 0.25, "Vth 3.73 V", fontsize=8, color=ps.TEXT2)
    ax[1, 0].set_ylabel("low-side Vgs kick when M1 turns on (V)")
    ax[1, 1].set_ylabel("converter efficiency (%) (floored at 80)")
    ax[1, 1].set_ylim(79, 100)
    for a in ax[1]:
        a.set_xlabel("external gate resistor Rg (ohm)")
    ax[0, 0].legend(loc="lower left", fontsize=7.5)
    fig.suptitle("LTspice v1.7: dead-time margin with IR2110 timing + gate resistor (12 V MPP, D = 0.68, 200 ns)",
                 fontsize=11, fontweight="bold")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "ltspice_v1.7_deadtime_summary.png"))
    plt.close(fig)


def plot_edge(rows, steps, params):
    """Edge B waveforms (M1 turning on) for Rg = 10 ohm, typical corner, 12 V: symmetric vs split."""
    fig, ax = plt.subplots(2, 2, figsize=(11, 5.8), sharex=True)
    for col, cfg in enumerate((0, 2)):
        i = [k for k, p in enumerate(params)
             if float(p["rg"]) == 10 and int(float(p["corner"])) == 0 and int(float(p["cfg"])) == cfg][0]
        s = steps[i]
        t = s["time"]
        t0 = P0 + TSW - DEAD
        w = (t >= t0 - 0.2e-6) & (t <= t0 + 0.8e-6)
        x = (t[w] - (P0 + TSW)) * 1e9
        ax[0, col].plot(x, s["V(m1:x1:7)"][w] - s["V(sw)"][w], color=ps.C[0], label="M1 internal Vgs")
        ax[0, col].plot(x, s["V(m2:x1:7)"][w], color=ps.C[1], label="M2 internal Vgs")
        ax[0, col].axhline(VTH, color=ps.REF, lw=1, ls="--")
        ax[1, col].plot(x, s["V(sw)"][w], color=ps.C[2])
        ax[0, col].set_title("symmetric 10 ohm" if cfg == 0 else "split: 10 ohm on, 1 ohm + diode off", fontsize=10)
        ax[1, col].set_xlabel("ns from M1 turn-on command (driver output before delay)")
    ax[0, 0].set_ylabel("Vgs internal (V)")
    ax[1, 0].set_ylabel("V(SW) (V)")
    ax[0, 0].legend(loc="upper left", fontsize=8)
    fig.suptitle("Edge B (M2 off -> M1 on), Rg = 10 ohm, IR2110 typical, 12 V MPP: Miller kick on the low-side gate",
                 fontsize=11, fontweight="bold")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "ltspice_v1.7_edgeB_waveforms.png"))
    plt.close(fig)


if __name__ == "__main__":
    rows, steps, params = analyse()
    plot_summary(rows)
    plot_edge(rows, steps, params)
    for r in rows:
        print(f"{r['network'][:9]:9s} {r['corner'][:4]} {r['point'][:4]} Rg={r['rg_ohm']:>4g} "
              f"mA={r['margin_A_ns']:8.1f} mB={r['margin_B_ns']:8.1f} ovl={r['overlap_ns']:7.1f} "
              f"kickL={r['kick_L_V']:5.2f} kickH={r['kick_H_V']:5.2f} effc={r['eff_conv_pct']:8.2f} "
              f"IL={r['il_avg_A']:6.3f}")
