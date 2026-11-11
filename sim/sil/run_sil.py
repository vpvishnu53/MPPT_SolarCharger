"""Software-in-the-loop runs: firmware control logic (C, via ctypes) + averaged Python plant.

Usage (repo root):
    sh sim/sil/build.sh
    sim/sil/.venv/Scripts/python sim/sil/run_sil.py
Outputs: sim/sil/results/*.png and sil_summary.csv
"""
import csv
import ctypes as ct
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))

import charger_lib as cl  # noqa: E402
import plant as pl  # noqa: E402
import plotstyle as ps  # noqa: E402

import matplotlib.pyplot as plt  # noqa: E402

ps.apply()
OUT = os.environ.get("SIL_OUT") or os.path.join(HERE, "results")   # SIL_OUT: used by tools/selftest.py
os.makedirs(OUT, exist_ok=True)

DT = 0.020                 # P&O / control period (DECIDED: 20 ms)
STIFF = 1e9                # battery capacitance for "fixed-voltage battery" runs
CB_SCALED = 10.0           # F, scaled SLA capacitance for run d
# A real 2.2 Ah SLA moves ~1.8 V of OCV over its charge range: C_eq ~ 7920 C / 1.8 V ~ 4400 F.
TIME_SCALE = 4400.0 / CB_SCALED
NOISE = {"vpv": 0.006, "vbat": 0.006, "ibat": 0.001}   # 1-sigma: ~1 ADC LSB through the divider; INA219 ~1 mA
EXTRA = {"vpv": 0.0, "vbat": 0.0, "ibat": 0.0}

LIB = cl.load()
ETA, LT_MPP_DUTY = pl.eta_from_ltspice()
SUMMARY = []


def simulate(T, iph_fn, cfg_over=None, vc0=12.0, cb=STIFF, iload=0.0, noise=True, meas_hook=None, seed=1):
    cfg = cl.default_cfg(LIB, **(cfg_over or {}))
    ch = cl.Charger()
    LIB.charger_init(ct.byref(ch), ct.byref(cfg))
    plant = pl.Plant(ETA, vc0, cb, iload=iload)
    rng = np.random.default_rng(seed)
    duty, pwm = 0.0, 0
    n = int(round(T / DT))
    log = {k: np.zeros(n) for k in ("t", "iph", "state", "duty", "pwm", "vpv", "ipv", "ppv", "pmax",
                                    "vmp", "vbat", "ichg", "vc", "fault")}
    m = cl.Meas()
    for k in range(n):
        t = k * DT
        iph = iph_fn(t)
        r = plant.solve(duty, pwm, iph)
        pmax, vmp = pl.true_mpp(iph)
        mv = {"vpv": r["vpv"], "vbat": r["vbat"], "ibat": r["ichg"]}
        if noise:
            for key in mv:
                mv[key] += rng.normal(0.0, NOISE[key])
        if meas_hook:
            meas_hook(t, mv)
        m.vpv, m.vbat, m.ibat = mv["vpv"], mv["vbat"], mv["ibat"]
        for key, val in (("t", t), ("iph", iph), ("duty", duty), ("pwm", pwm), ("vpv", r["vpv"]),
                         ("ipv", r["ipv"]), ("ppv", r["ppv"]), ("pmax", pmax), ("vmp", vmp),
                         ("vbat", r["vbat"]), ("ichg", r["ichg"]), ("vc", plant.vc)):
            log[key][k] = val
        duty = LIB.charger_update(ct.byref(ch), ct.byref(m))
        pwm = ch.pwm_on
        log["state"][k] = ch.state
        log["fault"][k] = ch.fault
        plant.advance(DT)
    log["counts"] = np.round(log["duty"] * cl.PWM_COUNTS)
    return log


def state_axis(ax, log):
    ax.step(log["t"], log["state"], where="post", color=ps.C[6])
    ax.set_yticks(range(6))
    ax.set_yticklabels(cl.STATE_NAMES, fontsize=7)
    ax.set_ylim(-0.5, 5.5)
    ax.set_ylabel("FSM state")


def segment_metrics(log, t0, t1, tail=2.0, vb=None, steps=1):
    """eff_ss: mean Ppv/Pmax over the last `tail` s. t_settle: first time after t0 that the duty
    is within max(2, step) counts of the true-MPP duty (only when vb is given, i.e. MPPT runs).
    ratio_min_1s: worst Ppv/Pmax in the first second after t0 (with PWM on)."""
    seg = (log["t"] >= t0) & (log["t"] < t1)
    ss = (log["t"] >= t1 - tail) & (log["t"] < t1)
    eff_ss = float(np.mean(log["ppv"][ss]) / np.mean(log["pmax"][ss]))
    eseg = float(np.sum(log["ppv"][seg]) / np.sum(log["pmax"][seg]))
    first = seg & (log["t"] < t0 + 1.0) & (log["pwm"] > 0)
    rmin = float(np.min(log["ppv"][first] / np.maximum(log["pmax"][first], 1e-9))) if first.any() else float("nan")
    t_settle = float("nan")
    if vb is not None:
        target = np.array([mpp_duty(i, vb) for i in log["iph"][seg]]) * cl.PWM_COUNTS
        ok = (np.abs(log["counts"][seg] - target) <= max(2, steps)) & (log["pwm"][seg] > 0)
        hit = np.where(ok)[0]
        t_settle = float(log["t"][seg][hit[0]] - t0) if len(hit) else float("nan")
    return {"eff_ss": eff_ss, "t_settle": t_settle, "ratio_min_1s": rmin, "energy_eff": eseg,
            "dither_counts_pp": float(np.ptp(log["counts"][ss])),
            "dither_vpv_pp": float(np.ptp(log["vpv"][ss])),
            "dither_p_pp": float(np.ptp(log["ppv"][ss]))}


def iph_steps(t):
    return 0.8 if t < 4.0 else (0.5 if t < 8.0 else 0.8)


NO_CC = {"i_cc": 2.0}   # MPPT-only runs: CC limit moved out of the way (i_oc 1.5 A still active)


# ---------------------------------------------------------------- run a
def run_a():
    log = simulate(12.0, iph_steps, NO_CC, vc0=12.0)
    fig, ax = plt.subplots(4, 1, figsize=(9, 8.5), sharex=True)
    ax[0].plot(log["t"], log["pmax"], "--", color=ps.REF, lw=1.2, label="true MPP (panel)")
    ax[0].plot(log["t"], log["ppv"], color=ps.C[0], label="P&O: panel power")
    ax[0].set_ylabel("Ppv (W)")
    ax[0].legend(loc="lower right")
    ax[1].plot(log["t"], log["vmp"], "--", color=ps.REF, lw=1.2, label="Vmp (true)")
    ax[1].plot(log["t"], log["vpv"], color=ps.C[1], label="Vpv")
    ax[1].set_ylabel("Vpv (V)")
    ax[1].legend(loc="upper right")
    dmpp = np.array([mpp_duty(i, 12.0) for i in log["iph"]])
    ax[2].plot(log["t"], dmpp * 420, "--", color=ps.REF, lw=1.2, label="duty at true MPP")
    ax[2].plot(log["t"], np.where(log["pwm"] > 0, log["counts"], np.nan), color=ps.C[2], label="CCR1 (counts of 420)")
    ax[2].set_ylabel("duty (counts)")
    ax[2].legend(loc="lower right")
    ax[3].plot(log["t"], log["iph"], color=ps.C[3])
    ax[3].set_ylabel("Iph (A)")
    ax[3].set_xlabel("time (s)")
    for a in ax:
        for tb in (4.0, 8.0):
            a.axvline(tb, color=ps.GRID, lw=1.0)
    fig.suptitle("SIL run a: irradiance step Iph 0.8 -> 0.5 -> 0.8 A (12 V battery, step 1 count, CC limit off)",
                 fontsize=11, fontweight="bold")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "sil_a_irradiance_step.png"))
    plt.close(fig)
    for name, (t0, t1) in (("a 0.8A start", (0, 4)), ("a 0.8->0.5A", (4, 8)), ("a 0.5->0.8A", (8, 12))):
        SUMMARY.append({"run": name, **segment_metrics(log, t0, t1, vb=12.0)})
    return log


_dmpp_cache = {}


def mpp_duty(iph, vb):
    """Duty that puts the panel at its true MPP for battery voltage vb (ideal averaged)."""
    key = (round(iph, 6), vb)
    if key not in _dmpp_cache:
        pmax, vmp = pl.true_mpp(iph)
        if pmax <= 0:
            _dmpp_cache[key] = np.nan
        else:
            imp = pmax / vmp
            vin = vmp - pl.diode_drop(imp)
            # battery terminal = Vc + Rb*Ichg (Rb = 0.08 ohm, stiff Vc = vb), Ichg from power balance
            vt = vb
            for _ in range(20):
                vt = vb + 0.08 * ETA * vin * imp / vt
            _dmpp_cache[key] = vt / vin
    return _dmpp_cache[key]


# ---------------------------------------------------------------- run b
def run_b():
    logs = {}
    for steps in (1, 2, 4):
        for noisy in (True, False):
            log = simulate(12.0, iph_steps, {**NO_CC, "po_step": steps / 420.0}, vc0=12.0, noise=noisy)
            if noisy:
                logs[steps] = log
            tag = "noise" if noisy else "no noise"
            for name, (t0, t1) in (("0.8A", (0, 4)), ("0.5A", (4, 8)), ("0.8A again", (8, 12))):
                SUMMARY.append({"run": f"b step {steps} ({tag}) {name}",
                                **segment_metrics(log, t0, t1, vb=12.0, steps=steps)})
    fig = plt.figure(figsize=(11, 5.2))
    gs = fig.add_gridspec(3, 2, width_ratios=[1.5, 1])
    a0 = fig.add_subplot(gs[:, 0])
    dm = mpp_duty(0.5, 12.0) * 420
    for j, steps in enumerate((1, 2, 4)):
        log = logs[steps]
        ratio = 100 * log["ppv"] / np.maximum(log["pmax"], 1e-9)
        a0.plot(log["t"], ratio, color=ps.C[j], lw=1.2, label=f"step {steps} count{'s' if steps > 1 else ''}")
        a = fig.add_subplot(gs[j, 1])
        w = (log["t"] >= 6.5) & (log["t"] < 8.0)
        a.axhline(dm, color=ps.REF, ls="--", lw=1.0)
        a.step(log["t"][w], log["counts"][w], where="post", color=ps.C[j], lw=1.4)
        a.set_ylim(dm - 9, dm + 9)
        a.set_ylabel(f"step {steps}", fontsize=8)
        if j == 0:
            a.set_title("CCR1 counts at Iph = 0.5 A (dashed: true MPP)", fontsize=10)
        if j < 2:
            a.tick_params(labelbottom=False)
        else:
            a.set_xlabel("time (s)")
    a0.set_ylim(98, 100.1)
    a0.set_ylabel("Ppv / Pmax (%)")
    a0.set_xlabel("time (s)")
    a0.set_title("tracking efficiency (Iph 0.8 -> 0.5 -> 0.8 A)", fontsize=10)
    a0.legend(loc="lower right")
    fig.suptitle("SIL run b: P&O step size 1 / 2 / 4 counts (with measurement noise)",
                 fontsize=11, fontweight="bold")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "sil_b_step_size.png"))
    plt.close(fig)


# ---------------------------------------------------------------- run c
def run_c():
    def iph(t):
        return 0.8 if t < 4.0 else (0.35 if t < 8.0 else 0.8)
    log = simulate(12.0, iph, None, vc0=12.6)
    fig, ax = plt.subplots(4, 1, figsize=(9, 8), sharex=True)
    ax[0].plot(log["t"], log["pmax"], "--", color=ps.REF, lw=1.2, label="available (true MPP)")
    ax[0].plot(log["t"], log["ppv"], color=ps.C[0], label="drawn from panel")
    ax[0].set_ylabel("Ppv (W)")
    ax[0].set_ylim(-0.5, 16.5)
    ax[0].legend(loc="upper center", ncol=2)
    ax[1].axhline(0.6, color=ps.REF, ls="--", lw=1.0)
    ax[1].text(0.1, 0.62, "CC limit 0.6 A", fontsize=8, color=ps.TEXT2)
    ax[1].plot(log["t"], log["ichg"], color=ps.C[1])
    ax[1].set_ylabel("Ichg (A)")
    ax[2].plot(log["t"], np.where(log["pwm"] > 0, log["counts"], np.nan), color=ps.C[2])
    ax[2].set_ylabel("duty (counts)")
    state_axis(ax[3], log)
    ax[3].set_xlabel("time (s)")
    for a in ax:
        for tb in (4.0, 8.0):
            a.axvline(tb, color=ps.GRID, lw=1.0)
    ax[0].text(1.5, 2, "full sun\nIph 0.8 A", fontsize=8, color=ps.TEXT2, ha="center")
    ax[0].text(6.0, 2, "partial sun\nIph 0.35 A", fontsize=8, color=ps.TEXT2, ha="center")
    ax[0].text(10.0, 2, "full sun", fontsize=8, color=ps.TEXT2, ha="center")
    fig.suptitle("SIL run c: full sun (CC limit active) vs partial sun (MPPT active), 12.6 V battery",
                 fontsize=11, fontweight="bold")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "sil_c_full_vs_partial_sun.png"))
    plt.close(fig)
    for name, (t0, t1) in (("c full sun", (0, 4)), ("c partial sun", (4, 8)), ("c full sun again", (8, 12))):
        seg = (log["t"] >= t1 - 2) & (log["t"] < t1)
        states = sorted({cl.STATE_NAMES[int(s)] for s in log["state"][seg]})
        SUMMARY.append({"run": name, **segment_metrics(log, t0, t1),
                        "ichg_mean": float(np.mean(log["ichg"][seg])), "states": "/".join(states)})
    return log


# ---------------------------------------------------------------- run d
def run_d():
    T = 260.0
    log = simulate(T, lambda t: 0.8, None, vc0=12.6, cb=CB_SCALED, iload=0.05)
    fig, ax = plt.subplots(4, 1, figsize=(9, 8.5), sharex=True)
    ax[0].axhline(14.4, color=ps.REF, ls="--", lw=1.0)
    ax[0].axhline(13.6, color=ps.REF, ls="--", lw=1.0)
    ax[0].text(T * 0.995, 14.45, "absorption 14.4 V", fontsize=8, color=ps.TEXT2, ha="right")
    ax[0].text(T * 0.995, 13.65, "float 13.6 V", fontsize=8, color=ps.TEXT2, ha="right")
    ax[0].plot(log["t"], log["vbat"], color=ps.C[0], label="terminal Vbat")
    ax[0].plot(log["t"], log["vc"], color=ps.C[4], lw=1.2, label="internal (OCV) Vc")
    ax[0].set_ylabel("V")
    ax[0].legend(loc="lower center", ncol=2)
    ax[1].axhline(0.6, color=ps.REF, ls="--", lw=1.0)
    ax[1].axhline(0.11, color=ps.REF, ls=":", lw=1.0)
    ax[1].text(T * 0.995, 0.62, "CC 0.6 A", fontsize=8, color=ps.TEXT2, ha="right")
    ax[1].text(T * 0.995, 0.13, "tail 0.11 A", fontsize=8, color=ps.TEXT2, ha="right")
    ax[1].plot(log["t"], log["ichg"], color=ps.C[1])
    ax[1].set_ylabel("Ichg (A)")
    ax[2].plot(log["t"], np.where(log["pwm"] > 0, log["counts"], np.nan), color=ps.C[2])
    ax[2].set_ylabel("duty (counts)")
    state_axis(ax[3], log)
    ax[3].set_xlabel(f"simulated time (s)   [battery capacitance scaled: 1 s here ~ {TIME_SCALE:.0f} s real]")
    fig.suptitle("SIL run d: CC -> CV 14.4 V -> taper -> float 13.6 V (full sun, 50 mA IoT load)",
                 fontsize=11, fontweight="bold")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "sil_d_cc_cv_float.png"))
    plt.close(fig)
    st = log["state"].astype(int)

    def first(state):
        idx = np.where(st == state)[0]
        return float(log["t"][idx[0]]) if len(idx) else float("nan")
    fl = st == 4
    late = fl & (log["t"] > T - 20)
    SUMMARY.append({"run": "d charge cycle",
                    "t_cc": first(2), "t_cv": first(3), "t_float": first(4),
                    "vbat_max": float(log["vbat"].max()),
                    "vbat_float_mean_last20s": float(np.mean(log["vbat"][late])) if late.any() else float("nan"),
                    "ichg_float_mean_last20s": float(np.mean(log["ichg"][late])) if late.any() else float("nan"),
                    "time_scale": TIME_SCALE})
    return log


# ---------------------------------------------------------------- run e
def run_e():
    def iph(t):
        if t < 2.0:
            return 0.8
        if t < 5.0:
            return 0.8 * (5.0 - t) / 3.0          # dusk ramp
        if t < 8.0:
            return 0.0                           # night
        if t < 11.0:
            return 0.8 * (t - 8.0) / 3.0          # dawn ramp
        return 0.8

    def hook(t, mv):
        if t >= 14.0:
            mv["vbat"] = 15.6                    # injected: battery-sense overvoltage (e.g. battery disconnected)
    T = 16.0
    log = simulate(T, iph, None, vc0=12.6, meas_hook=hook)
    fig, ax = plt.subplots(4, 1, figsize=(9, 8.5), sharex=True)
    ax[0].plot(log["t"], log["iph"], color=ps.C[3])
    ax[0].set_ylabel("Iph (A)")
    ax[1].plot(log["t"], log["vpv"], color=ps.C[0], label="Vpv (panel side)")
    ax[1].plot(log["t"], log["vbat"], color=ps.C[1], label="Vbat (true)")
    ax[1].set_ylabel("V")
    ax[1].legend(loc="lower left", ncol=2)
    ax[2].plot(log["t"], log["ichg"], color=ps.C[2], label="Ichg")
    ax[2].plot(log["t"], log["pwm"] * 0.1, color=ps.C[6], lw=1.0, label="PWM enabled (x0.1)")
    ax[2].set_ylabel("A")
    ax[2].legend(loc="upper right", ncol=2)
    state_axis(ax[3], log)
    ax[3].set_xlabel("time (s)")
    for a in ax:
        a.axvline(14.0, color=ps.GRID, lw=1.0)
    ax[0].text(14.1, 0.4, "fault injected:\nVbat sense = 15.6 V", fontsize=8, color=ps.TEXT2)
    fig.suptitle("SIL run e: dusk -> night -> dawn (PWM shutdown / restart), then latched FAULT",
                 fontsize=11, fontweight="bold")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "sil_e_night_and_fault.png"))
    plt.close(fig)
    st = log["state"].astype(int)
    t = log["t"]
    idle_after_sun = np.where((st == 0) & (t > 2.0))[0]
    t_idle = float(t[idle_after_sun[0]]) if len(idle_after_sun) else float("nan")
    restarts = int(np.sum((st[1:] == 1) & (st[:-1] == 0) & (t[1:] > 8.0) & (t[1:] < 14.0)))
    dawn = np.where((st == 1) & (t > 8.0))[0]
    t_fault = np.where(st == 5)[0]
    SUMMARY.append({"run": "e night/fault",
                    "t_shutdown": t_idle, "iph_at_shutdown": float(iph(t_idle)),
                    "t_restart": float(t[dawn[0]]) if len(dawn) else float("nan"),
                    "restarts_at_dawn": restarts,
                    "t_fault": float(t[t_fault[0]]) if len(t_fault) else float("nan"),
                    "fault_code": cl.FAULT_NAMES[int(log["fault"][-1])],
                    "pwm_on_after_fault": int(log["pwm"][t > 14.1].max())})
    return log


def write_summary():
    keys = []
    for r in SUMMARY:
        for k in r:
            if k not in keys:
                keys.append(k)
    with open(os.path.join(OUT, "sil_summary.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in SUMMARY:
            w.writerow({k: (f"{v:.5g}" if isinstance(v, float) else v) for k, v in r.items()})


if __name__ == "__main__":
    print(f"eta (LTspice v1.5, converter only) = {ETA:.4f}; time scale run d = {TIME_SCALE:.0f}x")
    run_a()
    run_b()
    run_c()
    run_d()
    run_e()
    write_summary()
    for r in SUMMARY:
        print({k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()})
