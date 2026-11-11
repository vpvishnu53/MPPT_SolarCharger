# What was added on 2026-11-11

*One-page record of this session (Claude Code, main PC). Commits `794fc1a` and the v1.6 commit that follows it. Everything here is **simulated**; nothing was flashed or measured, and there is still no bench data.*

Before this session the repo held the project docs, LTspice files up to v1.4, and the datasheets. There was no firmware, no Python, and no simulation beyond the static 50 kHz duty sweep.

---

## 1. Decisions recorded

The user set the **simulation baseline**, recorded as *DECIDED (simulation baseline)* in `PROJECT_STATE.md` §1.6:

| fsw | Dead time | D_min / D_max | PV input | CC limit | Absorption / float | P&O step / period |
|---|---|---|---|---|---|---|
| 100 kHz | 200 ns | 0.60 / 0.85 | series Schottky | 0.6 A | 14.4 V / 13.6 V | 1 count (1/420) / 20 ms |

Every value was checked against the PDFs in `datasheets/`; none contradicts them. Two caveats:
- The Schottky part is a simulation placeholder with no datasheet.
- The 0.6 A limit is derived from the 1.3 Ah sibling battery's datasheet.

Other thresholds and gains (tail current, re-bulk voltage, margins, K_I, K_V, fault limits) are **PROPOSED** only.

---

## 2. New and changed files

### LTspice (`SimFiles/`)

| File | What it is |
|---|---|
| `mppt_sim_1.5.asc` / `.log` | Copy of 1.4 with 100 kHz, 200 ns dead time, MBRS340 Schottky at the PV input (Cin moved to the converter side), battery stepped 12 V / 14.4 V, duty 0.60–0.85, more measurements (panel power, converter-only efficiency, I(L) min/max), named gate nodes |
| `mppt_sim_1.6.asc` / `.log` | Copy of 1.5 with M1/M2 = the real **IRF3205 vendor model** |
| `models/IRF3205.spi` | Infineon/IR IRF3205 SPICE subcircuit, supplied by the user |
| `SIM_FILE_HISTORY.md` | v1.5 and v1.6 entries added |
| `mppt_sim_1.4.asc` | **Not edited** (rule: never edit an old version) |

### Firmware (`firmware/`)

| File | What it is |
|---|---|
| `mppt_po.h` / `.c` | Perturb & Observe tracker using the §3.3 interface. Explicit sign convention: increasing D lowers the PV voltage. Hitting a clamp reverses direction |
| `charger_fsm.h` / `.c` | Charge state machine IDLE → BULK_MPPT → CC_LIMIT → CV_ABSORB → FLOAT, plus FAULT. `fsm_step()` is a pure transition function; `charger_update()` runs the transition, then the state action (P&O, or integral CC/CV/float regulation), and returns the duty (0 = PWM off) |
| `README.md` | Status updated |

Both build with **0 warnings** on the host gcc and on `arm-none-eabi-gcc -mcpu=cortex-m4 -mthumb -mfpu=fpv4-sp-d16 -mfloat-abi=hard`. The ARM build uses hardware-FPU instructions with no soft-float calls. Code size: about 1.3 kB. Constraints: float32, no HAL, no heap.

### Simulation tooling (`sim/`, new folder)

| File | What it is |
|---|---|
| `plotstyle.py` | Shared plot style for every figure |
| `ltspice/ltspice_raw.py` | Reads LTspice binary `.raw` files (stepped runs) and `.meas` tables from `.log` |
| `ltspice/export_ltspice.py` | Writes the sweep CSVs, the v1.4/1.5/1.6 comparison plot and the waveform PNGs |
| `ltspice/tt_sensitivity.sh` | Re-runs the 12 V MPP point with three IRF3205 body-diode TT values (temporary copies; nothing in `SimFiles/` changes) |
| `ltspice/results/` | `ltspice_v1.4/1.5/1.6_sweep.csv`, `ltspice_compare_versions.png`, waveform PNGs for v1.5 and v1.6 at D = 0.70 / 0.85, 12 V / 14.4 V |
| `sil/build.sh` | Builds the unchanged firmware C files into `sil/build/libcharger.dll` |
| `sil/sil_shim.c` | Reports struct sizes so Python can check its ctypes layouts |
| `sil/charger_lib.py` | ctypes bindings for the firmware functions |
| `sil/plant.py` | Averaged plant: same single-diode PV model as LTspice, MBRS340 diode, averaged buck with η from LTspice, C + R battery, duty quantised to whole timer counts |
| `sil/run_sil.py` | Runs a–e, saves the plots and `sil_summary.csv` |
| `sil/results/` | `sil_a` … `sil_e` PNGs, `sil_summary.csv`, `run_log.txt` |
| `sil/.venv/` | Local Python environment with numpy, matplotlib and pypdf (**git-ignored**; recreate with `python -m venv sim/sil/.venv` then `pip install numpy matplotlib`) |

### Documentation

| File | Change |
|---|---|
| `docs/simulation_results.md` | **New.** The full write-up: parameters, v1.4 vs v1.5 vs v1.6, firmware, the five SIL runs with plots and explanations, limitations |
| `docs/session_2026-11-11_changelog.md` | **New.** This page |
| `PROJECT_STATE.md` | Updated sections: §1.2 tools, §1.6 baseline, §2.2–2.4 results, §3.1/3.3/3.5 firmware status, §4.1–4.4 issues, next steps and corrections, §5 inventory, §6 session log |
| `README.md`, `datasheets/README.md`, `.gitignore` | Status line, folder map, SPICE-model pointer; ignores `.venv/`, `__pycache__/`, `*.dll` |
| `CLAUDE.md` | The user's pending "Git routine" section, committed as-is |

---

## 3. Main results

**LTspice**
- **MPP:** D = 0.68 at 12 V, D ≈ 0.80 at 14.4 V. Both sit inside the 0.60–0.85 clamp range. The "0.70" from v1.4 was an artefact of its coarse 0.05 duty grid.
- **Schottky:** stops reverse current into the panel. At 14.4 V and D ≤ 0.66 the panel sits at Voc with no current. I(L) goes negative there (forced CCM), but that current only circulates between the battery and Cin.
- **Inductor ripple:** 0.36 A pp at D = 0.70, matching the hand calculation. The converter stays in CCM at the MPP.
- **Efficiency (panel → battery):**
  - 99.7 % in v1.4.
  - 97.0 % in v1.5. The drop is the Schottky (~1.9 %) plus the doubled frequency and dead time (~1 %).
  - 95.1 % in v1.6, with the IRF3205 model.
- **Why v1.6 is lower:** a sensitivity run shows the extra v1.6 loss is body-diode reverse recovery from the model's 100 µs transit time. With a datasheet-scaled 2.3 ns the converter-only efficiency is 98.9 %, so the realistic converter efficiency lies between about 96.9 % and 98.9 %.
- **Dead time:** the IRF3205 turn-off matches the datasheet (td(off) 50 ns + tf 65 ns) and leaves only about 60–70 ns of the 200 ns dead time spare with an ideal driver.

**SIL (firmware C code + averaged plant).** The plant matches LTspice within 0.2 % at the checked points, except D = 0.60, where it is 4 % low.

| Run | Result |
|---|---|
| a. irradiance step 0.8 → 0.5 → 0.8 A | 99.89–99.98 % steady-state tracking. Re-settles in 0.14–0.26 s. Vmp barely moves with irradiance |
| b. step 1 / 2 / 4 counts | All ≥ 99.88 %. Without noise, a 1-count step is best (99.99 %). With realistic sensor noise the 1-count tracker wanders ±4 counts, so noise, not step size, limits accuracy |
| c. full vs partial sun | Full sun: CC holds 0.600 A and the charger deliberately uses only 58 % of the available power. Partial sun: MPPT tracks at 99.95 % |
| d. charge cycle | CC → CV at 14.4 V → taper → float, then holds 13.60 V while supplying a 50 mA load. Time-scaled 440×; the taper is unrealistically short |
| e. night and fault | Shuts down at Iph = 5 mA, restarts once at dawn with no chatter. An injected overvoltage latches FAULT and the PWM stays off |

---

## 4. Problems found and fixed during the session

| Problem | How it was found | Fix |
|---|---|---|
| Every LTspice `.meas` FAILed in v1.5 | first batch run | Started the saved data at 0 ms instead of 8 ms (`.tran` Tstart = 0) |
| Float stage nearly oscillated (charge current swinging 0–0.24 A) | SIL run d plot | Voltage gain K_V 0.5 → 0.10. Near Voc one PWM count moves the current ~87 mA, so the old loop gain was ~1.5 |
| ~300 ms overcurrent (1.0 A) when full sun returns | SIL run c plot | Current gain K_I 0.04 → 0.08 and slew limit 4 → 8 counts; now ~150 ms |
| "Duty at true MPP" reference line ~2 counts off | SIL run a plot | The reference now includes the battery resistance (0.08 Ω × 1 A) |
| "Time to 99 %" metric read 0 s after irradiance steps | SIL summary | Replaced with "duty within ±max(2, step) counts of the MPP duty" |
| Label overlaps in plots | Looking at every PNG | Moved labels and legends; run b dither split into three panels |
| `C:\MinGW` gcc is 32-bit and can't build a DLL that 64-bit Python can load | tool check | Used the MSYS2 UCRT64 gcc |

---

## 5. Still open (needs the user)

1. Choose the real PV-input Schottky part.
2. Decide on a **v1.7** with the IRF3205 body-diode TT adjusted to the datasheet, or keep the vendor model and quote efficiency as a range.
3. Edge-aligned PWM (840 counts) vs center-aligned (420 counts). The 420-count resolution causes ±21–87 mA ripple in the current-limit and float stages.
4. Confirm or change the PROPOSED charger thresholds and gains, and decide whether to add an absorption timer.
5. Change the drafted TIM1 dead-time register from 0x28 to **0x11** (202 ns).
6. Hardware: clock, PWM, ADC, INA219, `main.c`, then bench tests. Only bench data can turn "simulated" into "validated".
