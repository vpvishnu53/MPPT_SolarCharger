"""Re-run the SIL and LTspice v1.8 in a temporary folder and compare with the committed results.

Called by `sh setup.sh --test` (which sets LTSPICE). Nothing in the repo is written.
SIL: compared exactly (same code, same seed) -> differences mean a different numpy/compiler behaviour.
LTspice: compared with a tolerance, because LTspice versions differ slightly (this repo's results were
made with LTspice 26.0.2).
"""
import csv
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "sim", "ltspice"))
from ltspice_raw import parse_meas_log  # noqa: E402

failures = 0


def read_csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def num(x):
    try:
        return float(x)
    except ValueError:
        return None


# ---------------------------------------------------------------- SIL
tmp = tempfile.mkdtemp(prefix="mppt_selftest_")
env = dict(os.environ, SIL_OUT=os.path.join(tmp, "sil"))
r = subprocess.run([sys.executable, os.path.join(ROOT, "sim", "sil", "run_sil.py")], env=env,
                   capture_output=True, text=True)
if r.returncode != 0:
    print("  SIL: FAILED to run\n" + r.stderr[-2000:])
    failures += 1
else:
    new = read_csv(os.path.join(tmp, "sil", "sil_summary.csv"))
    ref = read_csv(os.path.join(ROOT, "sim", "sil", "results", "sil_summary.csv"))
    worst = 0.0
    for a, b in zip(new, ref):
        for k in b:
            x, y = num(a.get(k, "")), num(b[k])
            if x is not None and y is not None and abs(y) > 1e-12:
                worst = max(worst, abs(x - y) / abs(y))
            elif (a.get(k, "") or "") != (b[k] or "") and not (x is not None and y is not None):
                worst = max(worst, 1.0)
    same_rows = len(new) == len(ref)
    ok = same_rows and worst < 1e-3
    failures += 0 if ok else 1
    print(f"  SIL runs a-e: {len(new)} summary rows, largest relative difference {worst:.2e} -> "
          f"{'MATCHES this repo' if ok else 'DIFFERS (see ' + tmp + ')'}")

# ---------------------------------------------------------------- LTspice v1.8
lt = os.environ.get("LTSPICE", "")
if not lt:
    print("  LTspice: skipped (not found)")
else:
    d = os.path.join(tmp, "lt")
    os.makedirs(d)
    shutil.copy(os.path.join(ROOT, "SimFiles", "mppt_sim_1.8.asc"), d)
    shutil.copytree(os.path.join(ROOT, "SimFiles", "models"), os.path.join(d, "models"))
    if lt.startswith("/") and len(lt) > 2 and lt[2] == "/":         # /c/... -> C:/... for subprocess
        lt = lt[1].upper() + ":" + lt[2:]
    subprocess.run([lt, "-b", "mppt_sim_1.8.asc"], cwd=d, capture_output=True)
    log = os.path.join(d, "mppt_sim_1.8.log")
    try:
        params, meas = parse_meas_log(log)
        head = open(log, encoding="latin-1").readline().strip()
    except (OSError, AttributeError):
        params, meas, head = [], {}, "no log"
    ref = read_csv(os.path.join(ROOT, "sim", "ltspice", "results", "ltspice_v1.8_sweep.csv"))
    if len(params) != len(ref) or "pin" not in meas:
        print(f"  LTspice v1.8: FAILED ({head}); see {d}")
        failures += 1
    else:
        worst = max(abs(meas["pin"][i] - float(r_["ppv"])) / max(abs(float(r_["ppv"])), 1.0) for i, r_ in enumerate(ref))
        worst_e = max(abs(meas["effconv"][i] - float(r_["eff_conv_pct"])) for i, r_ in enumerate(ref)
                      if float(r_["ppv"]) > 1.0)
        ok = worst < 0.01 and worst_e < 0.5
        failures += 0 if ok else 1
        print(f"  LTspice v1.8 ({head}): 18 steps, panel power within {100*worst:.3f} %, converter efficiency within "
              f"{worst_e:.3f} points -> {'MATCHES this repo' if ok else 'DIFFERS (see ' + d + ')'}")

if failures == 0:
    shutil.rmtree(tmp, ignore_errors=True)
sys.exit(1 if failures else 0)
