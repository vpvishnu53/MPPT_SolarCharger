"""Shoot-through check for a stepped duty x Vb LTspice run that saves the internal gate nodes
V(m1:x1:7) and V(m2:x1:7) (v1.8 and later).

Usage (repo root):  sim/sil/.venv/Scripts/python sim/ltspice/overlap_report.py 1.8 [dead_ns] [ton_ns]
Writes sim/ltspice/results/ltspice_v<ver>_overlap.csv. Metric definitions as in analyze_v17.py.
"""
import csv
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)

import analyze_v17 as a  # noqa: E402  (crossing / margin helpers, constants)


def report(ver, dead=300e-9, ton=120e-9):
    names, steps = a.read_raw(os.path.join(a.SIM, f"mppt_sim_{ver}.raw"))
    params, meas = a.parse_meas_log(os.path.join(a.SIM, f"mppt_sim_{ver}.log"))
    rows = []
    for i, (s, p) in enumerate(zip(steps, params)):
        duty, vb = float(p["duty"]), float(p["vb"])
        t = s["time"]
        vh = s["V(m1:x1:7)"] - s["V(sw)"]
        vl = s["V(m2:x1:7)"]
        per = (t >= a.P0) & (t < a.P0 + a.TSW)
        both = (vh[per] > a.VTH) & (vl[per] > a.VTH)
        ov = float(np.sum(np.diff(t[per])[both[:-1]])) * 1e9
        tA = a.P0 + duty * a.TSW
        mA = a.edge_margin(t, vh, vl, tA, tA + 1.2e-6)
        tB = a.P0 + a.TSW - dead
        mB = a.edge_margin(t, vl, vh, tB - 0.3e-6, tB + 1.2e-6)
        kl = (t >= a.P0 + a.TSW + ton) & (t <= a.P0 + a.TSW + ton + 0.5e-6)
        rows.append({"duty": duty, "vbat": vb, "margin_A_ns": mA, "margin_B_ns": mB, "overlap_ns": ov,
                     "kick_L_V": float(vl[kl].max()), "ppv_W": meas["pin"][i],
                     "eff_total_pct": meas["eff"][i], "eff_conv_pct": meas["effconv"][i]})
    path = os.path.join(a.OUT, f"ltspice_v{ver}_overlap.csv")
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        for r in rows:
            w.writerow({k: f"{v:.4g}" for k, v in r.items()})
    return rows


if __name__ == "__main__":
    ver = sys.argv[1]
    dead = float(sys.argv[2]) * 1e-9 if len(sys.argv) > 2 else 300e-9
    ton = float(sys.argv[3]) * 1e-9 if len(sys.argv) > 3 else 120e-9
    for r in report(ver, dead, ton):
        print(f"D={r['duty']:.2f} Vb={r['vbat']:4.1f}  mA={r['margin_A_ns']:7.1f} mB={r['margin_B_ns']:7.1f} "
              f"ovl={r['overlap_ns']:5.1f} kickL={r['kick_L_V']:.2f}  Ppv={r['ppv_W']:7.3f} "
              f"eff={r['eff_total_pct']:7.2f} effc={r['eff_conv_pct']:7.2f}")
