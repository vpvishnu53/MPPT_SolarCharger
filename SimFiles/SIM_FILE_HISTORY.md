# LTspice file history (checked 2026-10-09)

Folder: `C:\Users\Admin\Desktop\Projects\MPPT_SolarCharger\SimFiles\`

| File | Status | Difference vs 1.4 |
|---|---|---|
| `mppt_sim_1.7.asc` | **Current** (2026-11-11) | v1.6 + IR2110 timing and gate network (dead-time study); see the v1.7 section below |
| `mppt_sim_1.6.asc` | Previous (2026-11-11), kept unedited | v1.5 with the IRF3205 vendor model; see the v1.6 section below |
| `mppt_sim_1.5.asc` | Previous (2026-11-11), kept unedited | See the v1.5 section below |
| `mppt_sim_1.4.asc` | Previous baseline (kept, not edited) | — (results in `mppt_sim_1.4.log`, match PROJECT_STATE §2.4) |
| `mppt_sim_1.3.asc` | Identical to 1.4 | none (byte-identical) |
| `mppt_sim_1.2.asc` | Superseded | Rs1 drawn the other way (`R90` at x=-48); Iavg/Pin measured as `-I(Rs1)` to compensate sign |
| `mppt_sim_1.2_ai_review_1.asc` | Superseded | Same as 1.2 but `u` instead of `µ` for unit prefixes |
| `mppt_sim_1.1.asc` | Superseded | Rs1 orientation as 1.2; Pin used `-V(pvout)*I(Rs1)` |

Note: PROJECT_STATE §5 lists `mppt_sim_1_3.asc`, `buck_converter.asc` and `buck_converter_pv_sweep_resload4.asc`. These are **not** in the project folder (the 1.3 file uses a dot: `mppt_sim_1.3.asc`). The two `buck_converter*` files are either on another machine or gone.

The 1.4 log path shows LTspice ran it from `C:\Users\Admin\Documents\LTspice\OpenLab1.2\`, so a second working copy exists there.

## v1.5 (2026-11-11, copied from 1.4; 1.4 left untouched)

Changes vs 1.4:

| Item | 1.4 | 1.5 |
|---|---|---|
| `Tsw` / fsw | 20u / 50 kHz | **10u / 100 kHz** (hardware plan) |
| `Dead` | 100n | **200n** |
| PV input | Rs1 straight to Cin and M1 drain | **D2 = MBRS340 Schottky** (40 V / 3 A, LTspice `standard.dio`) in series, node `PVpanel` -> `PVout`; Cin moved to the converter side of D2. Part is a simulation placeholder; no datasheet in `datasheets/` (unverified) |
| Battery | `V1 = 12` | `V1 = {Vb}`, `.step param Vb list 12 14.4` |
| Duty sweep | 0.2 ... 0.9 (12 points) | 0.60 0.64 0.66 0.68 0.70 0.72 0.76 0.80 0.85 (P&O clamp range only) |
| MOSFETs | IRFZ44N | IRFZ44N (the IRF3205 model arrived later the same day: see v1.6) |
| `.tran` | 0 10m 0 1u | 0 10m 0 50n (finer max step for the 200 ns dead time) |
| Measures | Vavg, Iavg, Pin, Pout, Eff | Pin now at the **panel terminals** `V(PVpanel)*I(Rs1)` (so Eff includes the diode); added `Pconv` (after D2), `EffConv`, `ILmin`, `ILmax` |
| Node names | — | added `PVpanel`, `G1H`, `G2L` for waveform export; `.save` limits the `.raw` to 10 traces |

Run: `LTspice.exe -b mppt_sim_1.5.asc` (LTspice 26.0.2, 18 steps, ~25 s). First attempt used `.tran 0 10m 8m 50n`
(Tstart = 8 ms to shrink the `.raw`); **every `.meas` then FAILed**. Fixed by setting Tstart back to 0.

Results: `sim/ltspice/results/ltspice_v1.5_sweep.csv`, plots in the same folder (exported by
`sim/ltspice/export_v15.py`, since renamed `export_ltspice.py`, which parses the `.raw` directly). Summary in `docs/simulation_results.md`.

## v1.6 (2026-11-11, copied from 1.5; 1.5 left untouched)

Only change: M1 and M2 use the Infineon/IR **IRF3205 vendor subcircuit** (`SimFiles/models/IRF3205.spi`, supplied by the user
from their Downloads folder; Symmetry MODPEX level-1 model dated Apr 2001, nodes 1 = D, 2 = G, 3 = S). In the schematic:
`SYMATTR Value irf3205`, `SYMATTR Prefix X`, plus `.include models/IRF3205.spi`. Run time 53 s (vs 25 s for v1.5).
The model header restricts commercial use/resale; it is kept in this private student repo for simulation only.

Results (`sim/ltspice/results/ltspice_v1.6_sweep.csv`): 12 V MPP still D = 0.68 (13.35 W, Vpv 17.93 V); 14.4 V MPP D = 0.80.
Converter efficiency 96.85 % vs 98.74 % in v1.5. A body-diode TT sensitivity run (`sim/ltspice/tt_sensitivity.sh`,
temporary copies only) shows the 1.9-point drop is reverse recovery from the model's TT = 100 us; with TT = 2.3 ns
(datasheet Qrr/IF) the converter is 98.90 %. Details in `docs/simulation_results.md` §2.4.

## v1.7 (2026-11-11, copied from 1.6; 1.6 left untouched)

Purpose: dead-time / shoot-through check with a realistic gate driver. Not a duty sweep.

| Item | 1.6 | 1.7 |
|---|---|---|
| Gate sources | ideal 0-10 V PULSE, 10 ns edges | 0-`Vdrv` (12 V, PROPOSED IR2110 VCC) PULSE with IR2110 delays `Ton`/`Toff` and `Rser={Rdrv}` (driver output R) |
| MOSFETs | `irf3205` | `irf3205_g` = new project subcircuit `models/gate_net_irf3205.sub`: vendor `irf3205` (unmodified) + `Rgon` and an optional `Rgoff` + 1N5819 turn-off path |
| Steps | Duty x Vb (18) | `Rg` 0/4.7/10/22 x `Corner` 0/1 (IR2110 typical / pessimistic) x `Cfg` 0..3 (12 V MPP D=0.68 or 14.4 V D=0.66; symmetric or split network) = 32 |
| Saved extra | - | internal gate nodes `V(m1:x1:7)`, `V(m2:x1:7)` |

Notes from building it:
- `.meas` cannot use subcircuit pin currents (`Ix(m2:1)` -> "Current not found", and that error stopped every measurement); `.save Ix(...)` was also ignored. Shoot-through is therefore detected from the internal gate voltages.
- `.meas ... WHEN` margins were unusable because the Miller kick creates extra threshold crossings; the margins are computed in Python instead (`sim/ltspice/analyze_v17.py`, "last fall of the outgoing gate to first rise of the incoming gate").
- A first attempt with `Rser={Rdrv+Rg}` (symmetric only) was replaced by the subcircuit so the split network could be tested.

Results: `sim/ltspice/results/ltspice_v1.7_deadtime.csv`, `ltspice_v1.7_deadtime_summary.png`, `ltspice_v1.7_edgeB_waveforms.png`.
Follow-up sweep of dead time x gate-source capacitor (temporary copies, `sim/ltspice/deadtime_sweep.sh`):
`ltspice_v1.7_deadtime_sweep.csv`. Summary in `docs/simulation_results.md` §2.5.
