#!/bin/sh
# v1.7 follow-up sweep: dead time (200/300/400 ns) x IR2110 corner x external gate-source capacitor
# (Cgx = 0 / 2.2 nF / 4.7 nF on both FETs), symmetric gate network with Rg = 0, 12 V MPP (D = 0.68).
# Works on temporary copies (nothing in SimFiles/ is modified). Needs SimFiles/mppt_sim_1.7.net
# (created by running the .asc once). Prints the same metrics as analyze_v17.py.
set -e
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SIMF="$ROOT/SimFiles"
LT="${LTSPICE:-/c/Users/Admin/AppData/Local/Programs/ADI/LTspice/LTspice.exe}"
PY="${PYTHON:-$ROOT/sim/sil/.venv/Scripts/python}"
TMP="$(mktemp -d)"
mkdir -p "$TMP/models"
cp "$SIMF/models/IRF3205.spi" "$TMP/models/"
sed 's/^X1   D  gi  S  irf3205/X1   D  gi  S  irf3205\nCgx  gi S {Cgx}/' \
    "$SIMF/models/gate_net_irf3205.sub" > "$TMP/models/gate_net_irf3205.sub"
sed -e 's/^.param Tsw=10u Dead=200n Vdrv=12/.param Tsw=10u Vdrv=12 Rg=0 Cfg=0/' \
    -e 's/^.step param Rg list.*/.step param Dead list 200n 300n 400n/' \
    -e 's/^.step param Cfg list.*/.step param Cgx list 1p 2.2n 4.7n/' \
    "$SIMF/mppt_sim_1.7.net" > "$TMP/dt.net"
cd "$TMP"
"$LT" -b dt.net
"$PY" - "$TMP" "$ROOT/sim/ltspice" <<'EOF'
import os, sys
sys.path.insert(0, sys.argv[2])
import numpy as np
import analyze_v17 as a
d = sys.argv[1]
names, steps = a.read_raw(os.path.join(d, "dt.raw"))
params, meas = a.parse_meas_log(os.path.join(d, "dt.log"))
print("dead_ns,corner,cgx_nF,margin_A_ns,margin_B_ns,overlap_ns,kick_L_V,eff_conv_pct,eff_total_pct")
for i, (s, p) in enumerate(zip(steps, params)):
    dead, corner = float(p["dead"]), int(float(p["corner"]))
    ton = 94e-9 if corner else 120e-9
    t = s["time"]; vh = s["V(m1:x1:7)"] - s["V(sw)"]; vl = s["V(m2:x1:7)"]
    per = (t >= a.P0) & (t < a.P0 + a.TSW)
    both = (vh[per] > a.VTH) & (vl[per] > a.VTH)
    ov = float(np.sum(np.diff(t[per])[both[:-1]])) * 1e9
    tA = a.P0 + 0.68 * a.TSW
    mA = a.edge_margin(t, vh, vl, tA, tA + 1.2e-6)
    tB = a.P0 + a.TSW - dead
    mB = a.edge_margin(t, vl, vh, tB - 0.3e-6, tB + 1.2e-6)
    kl = (t >= a.P0 + a.TSW + ton) & (t <= a.P0 + a.TSW + ton + 0.5e-6)
    print(f"{dead*1e9:.0f},{'pessimistic' if corner else 'typical'},{float(p['cgx'])*1e9:.1f},"
          f"{mA:.1f},{mB:.1f},{ov:.1f},{vl[kl].max():.2f},{meas['effconv'][i]:.2f},{meas['eff'][i]:.2f}")
EOF
echo "(temporary files in $TMP)"
