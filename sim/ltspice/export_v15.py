"""Export LTspice v1.5 results: waveform PNGs, 1.4 vs 1.5 comparison plot, CSV tables.

Run from the repo root (after LTspice has produced SimFiles/mppt_sim_1.5.raw/.log):
    sim/sil/.venv/Scripts/python sim/ltspice/export_v15.py
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
os.makedirs(OUT, exist_ok=True)
TSW = 10e-6
DEAD = 200e-9


def tables():
    p15, m15 = parse_meas_log(os.path.join(SIM, "mppt_sim_1.5.log"))
    p14, m14 = parse_meas_log(os.path.join(SIM, "mppt_sim_1.4.log"))
    rows15 = []
    for i, p in enumerate(p15):
        rows15.append({
            "duty": float(p["duty"]), "vbat": float(p["vb"]),
            "vpv": m15["vavg"][i], "ipv": m15["iavg"][i], "ppv": m15["pin"][i],
            "pconv_in": m15["pconv"][i], "pout": m15["pout"][i],
            "eff_total_pct": m15["eff"][i], "eff_conv_pct": m15["effconv"][i],
            "il_min": m15["ilmin"][i], "il_max": m15["ilmax"][i],
        })
    rows14 = []
    for i, p in enumerate(p14):
        rows14.append({"duty": float(p["duty"]), "vpv": m14["vavg"][i], "ipv": m14["iavg"][i],
                       "ppv": m14["pin"][i], "pout": m14["pout"][i], "eff_pct": m14["eff"][i]})
    with open(os.path.join(OUT, "ltspice_v1.5_sweep.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows15[0]))
        w.writeheader()
        for r in rows15:
            w.writerow({k: (f"{v:.5g}" if isinstance(v, float) else v) for k, v in r.items()})
    with open(os.path.join(OUT, "ltspice_v1.4_sweep.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows14[0]))
        w.writeheader()
        for r in rows14:
            w.writerow({k: f"{v:.5g}" for k, v in r.items()})
    return rows14, rows15


def plot_compare(rows14, rows15):
    fig, ax = plt.subplots(figsize=(7, 4))
    d14 = [r["duty"] for r in rows14 if r["duty"] >= 0.6]
    p14 = [r["ppv"] for r in rows14 if r["duty"] >= 0.6]
    ax.plot(d14, p14, "-o", color=ps.C[0], ms=5, label="v1.4  (50 kHz, 100 ns, no diode, 12 V)")
    for k, vb in enumerate((12.0, 14.4)):
        rr = [r for r in rows15 if r["vbat"] == vb]
        ax.plot([r["duty"] for r in rr], [r["ppv"] for r in rr], "-o", color=ps.C[1 + k], ms=5,
                label=f"v1.5  (100 kHz, 200 ns, Schottky, {vb:g} V)")
        best = max(rr, key=lambda r: r["ppv"])
        ax.annotate(f"max {best['ppv']:.2f} W @ D={best['duty']:.2f}", (best["duty"], best["ppv"]),
                    textcoords="offset points", xytext=((-95, 10) if vb == 12.0 else (-40, 10)),
                    fontsize=8, color=ps.TEXT2)
    best14 = max(rows14, key=lambda r: r["ppv"])
    ax.annotate(f"max {best14['ppv']:.2f} W @ D={best14['duty']:.2f}", (best14["duty"], best14["ppv"]),
                textcoords="data", xytext=(0.80, 10.0), fontsize=8, color=ps.TEXT2,
                arrowprops=dict(arrowstyle="-", color=ps.REF, lw=0.7))
    ax.set_xlabel("Duty D")
    ax.set_ylabel("PV power at panel terminals (W)")
    ax.set_title("LTspice static duty sweep: PV power vs duty (Iph = 0.8 A)")
    ax.set_ylim(0, 15)
    ax.legend(loc="lower right")
    fig.savefig(os.path.join(OUT, "ltspice_p_vs_duty_v14_v15.png"))
    plt.close(fig)


def plot_waveforms(steps, params):
    for duty in (0.70, 0.85):
        for vb in (12.0, 14.4):
            idx = [i for i, p in enumerate(params)
                   if abs(float(p["duty"]) - duty) < 1e-9 and abs(float(p["vb"]) - vb) < 1e-9][0]
            s = steps[idx]
            t = s["time"]
            t0 = 9.97e-3
            m = t >= t0
            tt = (t[m] - t0) * 1e6
            vgs1 = s["V(g1h)"][m] - s["V(sw)"][m]
            vgs2 = s["V(g2l)"][m]

            fig, axes = plt.subplots(3, 2, figsize=(10, 6.5), sharex="col",
                                     gridspec_kw={"width_ratios": [2.2, 1]})
            # zoom window around high-side turn-off of the last period
            toff = 9.99e-3 + duty * TSW
            zm = (t >= toff - 0.3e-6) & (t <= toff + 0.6e-6)
            tz = (t[zm] - toff) * 1e9
            for col, (x, sel) in enumerate(((tt, m), (tz, zm))):
                g1 = s["V(g1h)"][sel] - s["V(sw)"][sel]
                g2 = s["V(g2l)"][sel]
                a = axes[0, col]
                a.plot(x, g1, color=ps.C[0], label="Vgs high-side (M1)")
                a.plot(x, g2, color=ps.C[1], label="Vgs low-side (M2)")
                a.set_ylabel("Gate-source (V)")
                axes[1, col].plot(x, s["V(sw)"][sel], color=ps.C[2])
                axes[1, col].set_ylabel("V(SW) (V)")
                axes[2, col].plot(x, s["I(L)"][sel], color=ps.C[6])
                axes[2, col].axhline(0, color=ps.REF, lw=0.8)
                axes[2, col].set_ylabel("I(L) (A)")
            axes[0, 0].legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=2)
            axes[2, 0].set_xlabel("time from 9.97 ms (us)")
            axes[2, 1].set_xlabel("ns from high-side turn-off")
            axes[0, 1].set_title(f"zoom: {DEAD*1e9:.0f} ns dead time", fontsize=9, fontweight="normal")
            ipp = s["I(L)"][m].max() - s["I(L)"][m].min()
            fig.suptitle(f"LTspice v1.5 waveforms, D = {duty:.2f}, Vbat = {vb:g} V, 100 kHz "
                         f"(I(L) ripple {ipp:.2f} A pp, min {s['I(L)'][m].min():.2f} A)",
                         fontsize=11, fontweight="bold", color=ps.TEXT)
            fig.tight_layout()
            fig.savefig(os.path.join(OUT, f"ltspice_v1.5_waveforms_D{duty:.2f}_V{vb:g}.png"))
            plt.close(fig)
            print(f"D={duty} Vb={vb}: IL pp {ipp:.3f} A, IL min {s['I(L)'][m].min():.3f} A, "
                  f"Vsw min {s['V(sw)'][m].min():.2f} V")


if __name__ == "__main__":
    r14, r15 = tables()
    plot_compare(r14, r15)
    names, steps = read_raw(os.path.join(SIM, "mppt_sim_1.5.raw"))
    params, _ = parse_meas_log(os.path.join(SIM, "mppt_sim_1.5.log"))
    assert len(steps) == len(params), (len(steps), len(params))
    plot_waveforms(steps, params)
    print("written to", OUT)
