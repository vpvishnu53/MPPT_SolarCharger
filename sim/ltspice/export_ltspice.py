"""Export LTspice results: sweep CSVs, version-comparison plots and waveform PNGs.

Run from the repo root after LTspice has produced SimFiles/mppt_sim_<ver>.raw/.log:
    sim/sil/.venv/Scripts/python sim/ltspice/export_ltspice.py 1.6        (one version, waveforms from .raw)
    sim/sil/.venv/Scripts/python sim/ltspice/export_ltspice.py            (CSVs + comparison plots only)

Versions 1.5 and later share the same .meas set (duty x Vb sweep, 100 kHz, 200 ns).
The comparison plots include every such version whose .log exists, plus v1.4.
"""
import csv
import os
import sys

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
NEW_VERSIONS = ["1.5", "1.6"]          # same measurement set; extend when 1.7 exists
LABEL = {"1.4": "v1.4  (50 kHz, 100 ns, IRFZ44N, no diode)",
         "1.5": "v1.5  (100 kHz, 200 ns, Schottky, IRFZ44N)",
         "1.6": "v1.6  (as 1.5, IRF3205 vendor model)"}


def write_csv(path, rows):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        for r in rows:
            w.writerow({k: (f"{v:.5g}" if isinstance(v, float) else v) for k, v in r.items()})


def table_new(ver):
    p, m = parse_meas_log(os.path.join(SIM, f"mppt_sim_{ver}.log"))
    rows = [{"duty": float(q["duty"]), "vbat": float(q["vb"]),
             "vpv": m["vavg"][i], "ipv": m["iavg"][i], "ppv": m["pin"][i],
             "pconv_in": m["pconv"][i], "pout": m["pout"][i],
             "eff_total_pct": m["eff"][i], "eff_conv_pct": m["effconv"][i],
             "il_min": m["ilmin"][i], "il_max": m["ilmax"][i]} for i, q in enumerate(p)]
    write_csv(os.path.join(OUT, f"ltspice_v{ver}_sweep.csv"), rows)
    return rows


def table_14():
    p, m = parse_meas_log(os.path.join(SIM, "mppt_sim_1.4.log"))
    rows = [{"duty": float(q["duty"]), "vpv": m["vavg"][i], "ipv": m["iavg"][i],
             "ppv": m["pin"][i], "pout": m["pout"][i], "eff_pct": m["eff"][i]} for i, q in enumerate(p)]
    write_csv(os.path.join(OUT, "ltspice_v1.4_sweep.csv"), rows)
    return rows


def plot_compare(r14, new):
    """Panel power (left: 12 V, right: 14.4 V) and efficiency vs duty for each version."""
    colors = {"1.4": ps.C[0], "1.5": ps.C[1], "1.6": ps.C[2]}
    fig, ax = plt.subplots(2, 2, figsize=(11, 7.2), sharex=True)
    for col, vb in enumerate((12.0, 14.4)):
        a_p, a_e = ax[0, col], ax[1, col]
        if vb == 12.0:
            rr = [r for r in r14 if r["duty"] >= 0.6]
            a_p.plot([r["duty"] for r in rr], [r["ppv"] for r in rr], "-o", ms=4, color=colors["1.4"],
                     label=LABEL["1.4"])
            a_e.plot([r["duty"] for r in rr], [r["eff_pct"] for r in rr], "-o", ms=4, color=colors["1.4"])
        for ver, rows in new.items():
            rr = [r for r in rows if r["vbat"] == vb]
            a_p.plot([r["duty"] for r in rr], [r["ppv"] for r in rr], "-o", ms=4, color=colors[ver],
                     label=LABEL[ver])
            ok = [r for r in rr if r["ppv"] > 1.0]          # efficiency of ~0 W points is meaningless
            a_e.plot([r["duty"] for r in ok], [r["eff_total_pct"] for r in ok], "-o", ms=4, color=colors[ver])
        a_p.set_title(f"Vbat = {vb:g} V", fontsize=10)
        a_p.set_ylim(0, 14.5)
        a_e.set_ylim(94, 100.5)
        a_e.set_xlabel("Duty D")
    ax[0, 0].set_ylabel("PV power at panel (W)")
    ax[1, 0].set_ylabel("Efficiency panel -> battery (%)")
    ax[0, 0].legend(loc="lower right", fontsize=7.5)
    ax[1, 1].text(0.70, 94.4, "points below 1 W omitted", fontsize=7.5, color=ps.TEXT2)
    fig.suptitle("LTspice static duty sweeps, Iph = 0.8 A: v1.4 vs v1.5 vs v1.6",
                 fontsize=11, fontweight="bold")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "ltspice_compare_versions.png"))
    plt.close(fig)


def plot_waveforms(ver, steps, params):
    for duty in (0.70, 0.85):
        for vb in (12.0, 14.4):
            idx = [i for i, p in enumerate(params)
                   if abs(float(p["duty"]) - duty) < 1e-9 and abs(float(p["vb"]) - vb) < 1e-9][0]
            s = steps[idx]
            t = s["time"]
            t0 = 9.97e-3
            m = t >= t0
            tt = (t[m] - t0) * 1e6
            fig, axes = plt.subplots(3, 2, figsize=(10, 6.5), sharex="col",
                                     gridspec_kw={"width_ratios": [2.2, 1]})
            toff = 9.99e-3 + duty * TSW          # high-side turn-off in the last period
            zm = (t >= toff - 0.3e-6) & (t <= toff + 0.6e-6)
            tz = (t[zm] - toff) * 1e9
            for col, (x, sel) in enumerate(((tt, m), (tz, zm))):
                a = axes[0, col]
                a.plot(x, s["V(g1h)"][sel] - s["V(sw)"][sel], color=ps.C[0], label="Vgs high-side (M1), at driver")
                a.plot(x, s["V(g2l)"][sel], color=ps.C[1], label="Vgs low-side (M2), at driver")
                a.set_ylabel("Gate-source (V)")
                axes[1, col].plot(x, s["V(sw)"][sel], color=ps.C[2])
                axes[1, col].set_ylabel("V(SW) (V)")
                axes[2, col].plot(x, s["I(L)"][sel], color=ps.C[6])
                axes[2, col].axhline(0, color=ps.REF, lw=0.8)
                axes[2, col].set_ylabel("I(L) (A)")
            axes[0, 0].legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=2)
            axes[2, 0].set_xlabel("time from 9.97 ms (us)")
            axes[2, 1].set_xlabel("ns from high-side turn-off command")
            axes[0, 1].set_title(f"zoom: {DEAD*1e9:.0f} ns dead time", fontsize=9, fontweight="normal")
            ipp = s["I(L)"][m].max() - s["I(L)"][m].min()
            fig.suptitle(f"LTspice v{ver} waveforms, D = {duty:.2f}, Vbat = {vb:g} V, 100 kHz "
                         f"(I(L) ripple {ipp:.2f} A pp, min {s['I(L)'][m].min():.2f} A)",
                         fontsize=11, fontweight="bold", color=ps.TEXT)
            fig.tight_layout()
            fig.savefig(os.path.join(OUT, f"ltspice_v{ver}_waveforms_D{duty:.2f}_V{vb:g}.png"))
            plt.close(fig)
            print(f"v{ver} D={duty} Vb={vb}: IL pp {ipp:.3f} A, IL min {s['I(L)'][m].min():.3f} A, "
                  f"Vsw min {s['V(sw)'][m].min():.2f} V, Vsw max {s['V(sw)'][m].max():.2f} V")


if __name__ == "__main__":
    r14 = table_14()
    new = {v: table_new(v) for v in NEW_VERSIONS if os.path.exists(os.path.join(SIM, f"mppt_sim_{v}.log"))}
    plot_compare(r14, new)
    for ver in sys.argv[1:]:
        names, steps = read_raw(os.path.join(SIM, f"mppt_sim_{ver}.raw"))
        params, _ = parse_meas_log(os.path.join(SIM, f"mppt_sim_{ver}.log"))
        assert len(steps) == len(params), (len(steps), len(params))
        plot_waveforms(ver, steps, params)
    print("written to", OUT)
