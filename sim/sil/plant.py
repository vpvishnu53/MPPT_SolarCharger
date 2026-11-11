"""Averaged, quasi-static plant for the SIL harness.

Chain: single-diode PV  ->  series Schottky  ->  averaged synchronous buck  ->  C + R battery.

PV model: identical to SimFiles/mppt_sim_1.5.asc
    I = Iph - Is*(exp(Vint/(N*Vt)) - 1) - Vint/Rsh,   Vpanel = Vint - I*Rs
    Is = 1n, N = 40, Rs = 0.35, Rsh = 1500, Vt at 27 C (LTspice default temp)
Schottky: LTspice standard.dio MBRS340 (Is = 22.6u, N = 1.094, Rs = 0.042)
Buck: ideal averaged CCM relation Vin_conv = Vbat_terminal / D, power balance
    Pout = eta * Pin_conv, eta from the LTspice v1.5 run (converter-only efficiency at the
    12 V MPP). Forced-CCM reverse operation is not modelled: the Schottky blocks it, so
    when Vbat/D exceeds what the panel can reach, Ipv = 0 and the charge current is 0.
Battery: terminal V = Vc + Rb*Ib, dVc/dt = Ib / Cb, Ib = Ichg - Iload.
    Cb is a scaled (small) capacitance so a charge cycle fits in minutes; see TIME_SCALE.

Quasi-static: the electrical states (Cin, L, Cout) are assumed settled within each 20 ms
P&O period, so each period is solved as a DC operating point. This is the averaged-model
time-scale separation argument; the LTspice v1.5 transient settles in well under 8 ms
from a cold start.
"""
import csv
import math
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))

# --- PV (same as LTspice) ---
IS_PV, N_PV, RS_PV, RSH_PV = 1e-9, 40.0, 0.35, 1500.0
VT = 1.380649e-23 * 300.15 / 1.602176634e-19        # 27 C, LTspice tnom/temp in the .log
# --- Schottky MBRS340 (LTspice standard.dio) ---
IS_D, N_D, RS_D = 22.6e-6, 1.094, 0.042
# --- PWM ---
PWM_COUNTS = 420


def eta_from_ltspice():
    """Converter-only efficiency at the 12 V MPP of the LTspice v1.5 sweep."""
    path = os.path.join(ROOT, "sim", "ltspice", "results", "ltspice_v1.5_sweep.csv")
    with open(path) as f:
        rows = [r for r in csv.DictReader(f) if float(r["vbat"]) == 12.0]
    best = max(rows, key=lambda r: float(r["ppv"]))
    return float(best["eff_conv_pct"]) / 100.0, float(best["duty"])


def pv_current(vint, iph):
    return iph - IS_PV * (math.exp(vint / (N_PV * VT)) - 1.0) - vint / RSH_PV


def diode_drop(i):
    if i <= 0.0:
        return 0.0
    return N_D * VT * math.log(i / IS_D + 1.0) + RS_D * i


def vint_open_circuit(iph):
    lo, hi = 0.0, 40.0
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if pv_current(mid, iph) > 0.0:
            lo = mid
        else:
            hi = mid
    return lo


def panel_point(vin_conv, iph, vint_oc):
    """Operating point for a given converter input voltage. Returns (Vpanel, Ipv)."""
    if vin_conv >= vint_oc:                     # panel cannot reach it: diode blocks, Ipv = 0
        return vint_oc, 0.0
    lo, hi = 0.0, vint_oc
    for _ in range(60):                         # Vin(vint) is monotonic increasing
        mid = 0.5 * (lo + hi)
        i = pv_current(mid, iph)
        vin = mid - i * RS_PV - diode_drop(i)
        if vin < vin_conv:
            lo = mid
        else:
            hi = mid
    i = max(pv_current(lo, iph), 0.0)
    return lo - i * RS_PV, i


def pv_curve(iph, n=4000):
    """Panel-terminal P-V curve (no diode)."""
    vint = np.linspace(0.0, vint_open_circuit(iph), n)
    i = iph - IS_PV * (np.exp(vint / (N_PV * VT)) - 1.0) - vint / RSH_PV
    v = vint - i * RS_PV
    return v, i, v * i


_pmax_cache = {}


def true_mpp(iph):
    """(Pmax, Vmp) at the panel terminals for a photocurrent iph."""
    key = round(iph, 6)
    if key not in _pmax_cache:
        if iph <= 1e-6:
            _pmax_cache[key] = (0.0, 0.0)
        else:
            v, i, p = pv_curve(iph)
            k = int(np.argmax(p))
            _pmax_cache[key] = (float(p[k]), float(v[k]))
    return _pmax_cache[key]


class Plant:
    def __init__(self, eta, vc0, cb, rb=0.08, iload=0.0):
        self.eta, self.vc, self.cb, self.rb, self.iload = eta, vc0, cb, rb, iload
        self.ichg = 0.0

    def solve(self, duty, pwm_on, iph):
        """Steady state for one control period. Returns dict of true (noise-free) values."""
        vint_oc = vint_open_circuit(iph) if iph > 0 else 0.0
        if not pwm_on or duty <= 0.0:
            ichg, vpanel, ipv = 0.0, vint_oc, 0.0
        else:
            d = round(duty * PWM_COUNTS) / PWM_COUNTS      # TIM1 CCR quantisation
            ichg = self.ichg
            for _ in range(8):                           # fixed point on the charge current
                vb = self.vc + self.rb * (ichg - self.iload)
                vin = vb / d
                vpanel, ipv = panel_point(vin, iph, vint_oc)
                ichg_new = self.eta * vin * ipv / vb if ipv > 0 else 0.0
                if abs(ichg_new - ichg) < 1e-7:
                    ichg = ichg_new
                    break
                ichg = 0.5 * (ichg + ichg_new)
        self.ichg = ichg
        vb = self.vc + self.rb * (ichg - self.iload)
        return {"vpv": vpanel, "ipv": ipv, "ppv": vpanel * ipv, "vbat": vb, "ichg": ichg,
                "pout": vb * ichg}

    def advance(self, dt):
        self.vc += (self.ichg - self.iload) * dt / self.cb
