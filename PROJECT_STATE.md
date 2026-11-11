# PROJECT_STATE.md: STM32 Synchronous-Buck MPPT Solar Charge Controller

> **Read this first (honesty note for the next session).**
> This is a 3rd-year engineering capstone. As of 2026-11-11 the work completed is **architecture, component selection, LTspice simulation (v1.5 at 100 kHz), the P&O + charge-FSM firmware logic (compiled for the Cortex-M4F, not flashed), and a software-in-the-loop simulation of that logic**. **Nothing has been flashed, and no hardware has been confirmed built. There is no bench data.** All results are *simulated*, not validated. Full write-up: `docs/simulation_results.md`. Everything labeled **PROPOSED** below is a suggestion that has *not* been agreed or verified. Everything labeled **DECIDED** was stated by the user or locked in the design. Do not treat proposed items as settled.

---

## 0. Project Summary

| Item | Value |
|---|---|
| Goal | Cheap, safe, student-demo-grade MPPT charge controller |
| Application | Ultra-low-power (12 W) off-grid IoT / telemetry node |
| Topology | Synchronous buck (low-side Schottky replaced by an active MOSFET) |
| MPPT | Perturb & Observe (P&O), bare-metal, tuned to minimize steady-state oscillation loss at low power |
| Charging | CC/CV state machine for SLA battery, with MPPT as the bulk stage |
| Differentiator vs literature | Bare-metal Cortex-M4 (FPU + advanced timer) instead of RTOS/DSP-heavy designs and legacy ARM7 designs |
| Defense materials | Slides with IEEE citations and system block diagrams already produced (in an earlier session, not reproduced here) |

### Plan (5 steps, firmware/hardware)
1. Hardware assembly & static testing (breakdown written; bootstrap Cboot sizing done; **not confirmed executed**)
2. Bare-metal TIM1 complementary PWM + dead-time (register sequence drafted, see §3)
3. DMA-linked ADC sampling + telemetry (not started)
4. P&O loop + CC/CV state machine (not started)
5. Closed-loop bench validation vs. LTspice baseline, then demo (not started)

Phase A (LTspice) was done *before* Step 2. It is essentially complete for static characterization (see §2.4).

---

## 1. System & Target Architecture

### 1.1 Hardware (DECIDED)

| Block | Part / Spec | Notes |
|---|---|---|
| MCU board | STM32 Nucleo-F401RE (STM32F401RET6, Cortex-M4F) | Hardware FPU (single precision), advanced timer TIM1, max SYSCLK 84 MHz |
| PV panel | 12 V / 12 W polycrystalline | Voc ≈ 21 V, Vmp = 17.1 V (datasheet Isc/Imp **not yet checked**; a 12 W / 17.1 V panel implies Imp ≈ 0.70 A, Isc likely ≈ 0.75-0.85 A) |
| Battery | 12 V 2.2 Ah sealed lead-acid (SLA) | Target absorption 14.4 V (see §4 for float-voltage and charge-current concerns) |
| Switches | 2 x IRF3205 N-MOSFET (high-side + low-side) | 55 V, low Rds(on), high Qg (~146 nC max per datasheet; **verify**) |
| Gate driver | IR2110 high/low-side driver | Bootstrap: Cboot >= 292 nF ceramic, fast-recovery Dboot |
| Inductor | 100 uH toroid | Current rating must exceed peak (~1.5 A+); not yet verified |
| Bulk caps | 470 uF electrolytic, input and output | |
| Voltage sensing | Resistor dividers, 25 V max -> 3.3 V | Ratios not finalized (see 1.4) |
| Current sensing | INA219 module (I2C) | Charge-current monitor |
| Switching frequency | **100 kHz (hardware plan)** | LTspice v1.4 ran at 50 kHz; **v1.5 runs at 100 kHz** (2026-11-11). A wider fsw sweep was never run (see §4) |

Cboot derivation (consistent with the stated 292 nF): `Cboot >= 2*Qg/dV = 2 * 146 nC / 1 V = 292 nF`. A practical choice is larger (e.g. 1 uF X7R), which is not yet decided.

### 1.2 Toolchain & environment

- **DECIDED:** Bare-metal C, CMSIS-style register access, no RTOS, no HAL-dependence stated as a goal.
- **NOT DECIDED (needs a user choice):** compiler, build system, IDE, debugger flow.
  - **PROPOSED:** `arm-none-eabi-gcc` + Makefile (or STM32CubeIDE with only CMSIS device headers `stm32f401xe.h` used), flashing via the Nucleo's on-board ST-LINK.
  - **PROPOSED compile flags:** `-mcpu=cortex-m4 -mthumb -mfpu=fpv4-sp-d16 -mfloat-abi=hard -O2 -ffunction-sections -fdata-sections`
  - **Required at startup for the FPU:** `SCB->CPACR |= (0xFUL << 20);` (enable CP10/CP11) before any float math, or you get a HardFault.
- **Numeric format: DECIDED = float32 on the hardware FPU.** There is **no fixed-point specification** in this project; do not invent one unless the user asks.
- **Simulation:** LTspice (24.0.12 on one machine, 26.0.2 on another; same project copied between them). Current file: `SimFiles/mppt_sim_1.8.asc` (2026-11-11: the decided baseline with 300 ns dead time and IR2110 typical timing, duty x Vb sweep; 1.4-1.7 kept unedited). Batch run on the main PC: `C:\Users\Admin\AppData\Local\Programs\ADI\LTspice\LTspice.exe -b <file>.asc`.
- **Tools on the main PC (checked 2026-11-11):** Python 3.12 with a local venv `sim/sil/.venv` (numpy, matplotlib) for the SIL and plots; host gcc = MSYS2 UCRT64 gcc 16.2 (64-bit, matches Python; `C:\MinGW` gcc is 32-bit and cannot build a DLL Python can load); arm-none-eabi-gcc 14.3 inside the STM32CubeIDE 2.1.1 bundle (not on PATH).

### 1.3 Clock tree (PROPOSED, standard for F401 at 84 MHz; verify vs RM0368)

```
Source        : HSI 16 MHz (or HSE 8 MHz from ST-LINK MCO on Nucleo)
PLL (HSI)     : PLLM=16, PLLN=336, PLLP=4  -> SYSCLK = 16/16*336/4 = 84 MHz
PLL (HSE 8M)  : PLLM=8,  PLLN=336, PLLP=4  -> 84 MHz
Flash latency : 2 wait states @ 84 MHz (3.3 V), enable prefetch + I/D cache
AHB  (HCLK)   : /1 = 84 MHz
APB1 (PCLK1)  : /2 = 42 MHz (max 42)  -> timer clocks on APB1 = 84 MHz
APB2 (PCLK2)  : /1 = 84 MHz (max 84)  -> TIM1 clock = 84 MHz
ADC clock     : PCLK2 / 4 = 21 MHz (max 36 MHz)
```

### 1.4 Pin allocation (PROPOSED. Nothing below was agreed; verify against the F401 datasheet AF table and Nucleo UM1724 before wiring)

| Function | Pin | AF / Mode | Connects to |
|---|---|---|---|
| TIM1_CH1 | PA8 | AF1 | IR2110 HIN (high-side input) |
| TIM1_CH1N | PA7 | AF1 | IR2110 LIN (low-side input). Alt: PB13 |
| TIM1_BKIN | PA6 | AF1 | Overcurrent comparator output (hardware break). Alt: PB12 |
| ADC1_IN0 | PA0 | Analog | PV voltage divider |
| ADC1_IN1 | PA1 | Analog | Battery voltage divider |
| I2C1_SCL / SDA | PB8 / PB9 | AF4, open-drain | INA219 (external 4.7 kohm pull-ups) |
| USART2 TX/RX | PA2 / PA3 | AF7 | ST-LINK virtual COM port, telemetry |
| User LED | PA5 | GPIO | Status |

Divider example (not final): 68 kohm / 10 kohm gives ratio 7.8, so 25.7 V full scale -> 3.3 V, and Voc 21 V -> 2.69 V. The source impedance (~8.7 kohm) is high for the ADC, so add ~100 nF at the pin and use a long sample time (e.g. 144+ cycles). Use 1% or better resistors.

### 1.5 Interface correction to the original summary

The original session summary said the ADC DMA stream carries "analog voltage and **INA219** current readings." **That is not possible as written.** The INA219 is an **I2C** device and cannot be sampled by the ADC/DMA. Correct architecture: ADC+DMA for the two voltage dividers; **I2C (polled, interrupt, or I2C DMA) for the INA219**. Alternatively, use an analog shunt amplifier into an ADC channel.

### 1.6 Simulation baseline (DECIDED (simulation baseline), set by the user 2026-11-11)

These values are used in LTspice v1.5, the firmware defaults (`charger_default_cfg()`) and the SIL runs. No datasheet in `datasheets/` contradicts them (cross-check table in `docs/simulation_results.md` §1.1).

| Parameter | Value | Note |
|---|---|---|
| fsw | 100 kHz | TIM1 ARR = 419, center-aligned, 420 counts |
| Dead time | **300 ns** (changed from 200 ns by the user on 2026-11-11 after LTspice v1.7) | TIM1 DTG = 25 (0x19) = 297.6 ns at 84 MHz. Reason: v1.7 shows ~22 ns shoot-through per cycle at 200 ns once the IR2110 output resistance is modelled; 300 ns cuts it to 9 ns, and 300 ns + 2.2 nF gate-source cap to 0 at typical timing (the cap is still PROPOSED). Low-side on-time at D_max 0.85 = 0.9 us. LTspice v1.5/v1.6 and the SIL were run at 200 ns; v1.7 (dead-time study) and v1.8 (duty sweep) use 300 ns |
| D_min / D_max | 0.60 / 0.85 | CCR1 252 / 357 |
| PV-input blocking diode | Schottky in series at the PV input | Sim uses MBRS340 (LTspice library) as a placeholder; real part not chosen, no datasheet |
| CC limit | 0.6 A | |
| Absorption / float | 14.4 V / 13.6 V | |
| P&O step / period | 1 count (1/420) / 20 ms | |

Other charger thresholds and gains used in the simulation (tail current 0.11 A, re-bulk 12.8 V, margins, hold-off, K_I 0.08, K_V 0.10, fault limits) are **PROPOSED**; they are listed in `firmware/charger_fsm.h` and `docs/simulation_results.md` §1.2.

---

## 2. Core Logic & Mathematical Models

### 2.1 Power-stage math (DECIDED values; checks are back-of-envelope, mine)

- Ideal buck relation (CCM): `Vout = D * Vin`, so with the battery clamping Vout, `Vin = Vbat / D`. At 12 V: D=0.70 -> Vin=17.1 V (matches Vmp); D=0.57 -> 21 V (Voc).
- **Duty floor:** `D_min ~ Vbat/Voc ~ 12/21 ~ 0.57`. Below it, the buck cannot reach the battery voltage from the panel and (with synchronous switches) current reverses. The P&O search range **must** be clamped above this.
- Inductor ripple: `dI_pp = Vout*(1-D)/(L*fsw)`. At Vout=12 V, D=0.70, L=100 uH: **0.72 A pp @ 50 kHz, 0.36 A pp @ 100 kHz.** Average output current at the MPP is ~1.1 A, so there is margin at full sun.
- **Important:** with *complementary* PWM and no diode emulation, a synchronous buck is **forced-CCM**. It does not enter DCM at light load; the inductor current goes negative instead. See the reverse-current blocker in §4.

### 2.2 TIM1 timing math (DECIDED approach, numbers verified by hand)

```
TIM1 clock                = 84 MHz
Center-aligned mode       : period = 2 * (ARR+1) ticks
Target fsw                = 100 kHz  -> (ARR+1) = 84e6 / (2*100e3) = 420  -> ARR = 419
Duty                      : D = CCR1 / 420      (CCR1 = round(D*420))
Duty resolution           : 1 count = 0.238 % duty (~12-bit-ish, ~8.7 bits)
Dead time                 : DTG[7:0] (range 1, DTG[7]=0): t_dead = DTG / 84e6
                            DTG=0x28 (40) -> 476 ns   (1 tick = 11.9 ns)   [original draft]
                            DTG=0x19 (25) -> 297.6 ns                      [DECIDED 300 ns, 2026-11-11]
```

**Dead-time concern (resolved 2026-11-11: dead time 300 ns and D_max 0.85 DECIDED; 200 ns was the first choice and was changed after LTspice v1.7 showed shoot-through with the IR2110 modelled. Low-side on-time at D = 0.85 is 0.9 us):** 476 ns at 100 kHz is 4.8 % of the 10 us period *per edge*, about 9.5 % total. At D = 0.9 the low-side on-time `= 0.1*10us - 2*476ns ~ 48 ns`, which is effectively zero, so **bootstrap refresh and synchronous operation break down near D_max.** Options: reduce dead time to ~150-300 ns (verify IRF3205 turn-off delay + IR2110 propagation on a scope), cap D_max near 0.85, and/or run at 50 kHz. The LTspice run used 100 ns dead time at 50 kHz, not these values.

### 2.3 P&O control law (DECIDED concept; thresholds are PROPOSED)

```
P(k)  = V(k) * I(k)            (float32, FPU)
dP    = P(k) - P(k-1)
dD    = +/- STEP               (one or two CCR counts = 0.24-0.48 % duty)

if dP > 0 : keep previous direction of D change
else      : reverse direction
D(k+1) = clamp(D(k) + dir*STEP, D_MIN, D_MAX)
```

Because Vin = Vbat/D, *increasing D lowers the PV operating voltage* (moves left on the P-V curve). The sign convention must be defined explicitly in code.

Parameters (D_MIN, D_MAX, STEP and period became **DECIDED (simulation baseline)** on 2026-11-11, see §1.6):
- `D_MIN = 0.60` (above the 0.57 floor with margin), `D_MAX = 0.85`
- `STEP = 1 count (0.238 %)` to minimize steady-state oscillation (the stated novelty); optionally adaptive (larger when |dP| is large). SIL finding: with realistic measurement noise the 1-count tracker random-walks about +/-4 counts around the MPP (noise, not step size, limits accuracy); still >= 99.89 % tracking in the model
- P&O period 20 ms (must exceed the settling time of the input/output caps and the INA219 conversion time; INA219 at 12-bit/8x averaging is ~4.3 ms)
- Optional dead-band on |dP| to suppress dither at the MPP (PROPOSED, not implemented)
- **Resolved for now (implemented 2026-11-11):** P&O is fed output power Vbat*Ibat (INA219 only). In LTspice v1.5 converter efficiency varies only 0.06 % across D = 0.64-0.72, so output-power tracking finds the panel MPP in the model. **Original open question:** with battery-side current only (INA219 on the charge path), P&O tracks *output* power `Vbat*Ibat`, which is valid if converter efficiency is roughly constant. Tracking PV-side power would need a second current sensor.

### 2.4 LTspice model and results (VERIFIED by running; this is the strongest completed work)

**File:** `mppt_sim_1.4.asc` (power stage + single-diode PV model + battery load).

| Element | Value |
|---|---|
| PV photocurrent `I1` | 0.8 A (DC current source, ground -> `PVint`) |
| PV diode `D1` | `.model DPV D(Is=1n N=40)`, `PVint` -> ground. Voc = N*Vt*ln(Iph/Is+1) ~ 40*0.02585*20.5 ~ 21.2 V |
| `Rsh1` | 1500 ohm (PVint -> gnd) |
| `Rs1` | 0.35 ohm (PVint -> PVout) |
| `Cin` | 10 uF (PVout -> gnd) |
| MOSFETs | `M1` (high) / `M2` (low): **IRFZ44N** placeholder (ships in LTspice `standard.mos`) in 1.4/1.5; **IRF3205 vendor model from v1.6** |
| `L`, `C` | 100 uH, 470 uF |
| Battery model | `V1 = 12 V` in series with `R1 = 0.08 ohm` |
| High-side drive | `V3` floating PULSE source with its negative terminal tied to the SW node (stands in for the IR2110 bootstrap) |
| Low-side drive | `V2` PULSE referenced to ground |
| Parameters | `.param Tsw=20u Dead=100n` (**fixed 50 kHz**), `Duty` swept |
| V3 (M1 gate) | `PULSE(0 10 0 10n 10n {Duty*Tsw} {Tsw})` |
| V2 (M2 gate) | `PULSE(0 10 {Duty*Tsw+Dead} 10n 10n {(1-Duty)*Tsw-2*Dead} {Tsw})` (100 ns gap both edges at every duty; algebra verified at D=0.2 and 0.9) |
| Sweep | `.step param Duty list 0.2 0.4 0.45 0.5 0.55 0.6 0.65 0.7 0.75 0.8 0.85 0.9` (note: **no 0.3**) |
| Run / window | `.tran` to 10 ms, `.meas` averaged over 8-10 ms |
| Measures | `vavg=AVG V(PVout)`, `iavg=AVG I(Rs1)`, `pavg=vavg*iavg`, `pin=AVG V(pvout)*I(Rs1)`, `pout=AVG V(vout)*I(r1)`, `eff=pout/pin*100` |

**Results (LTspice 26.0.2, identical on repeated runs and in the earlier 24.0.12 run):**

| Duty | Vavg (V) | Iavg (A) | Pin (W) | Pout (W) | Eff (%) | Validity |
|---|---|---|---|---|---|---|
| 0.20 | 27.78 | -11.70 | -369.6 | -422.9 | 114.4 | invalid (reverse flow) |
| 0.40 | 25.19 | -5.62 | -146.7 | -150.3 | 102.5 | invalid |
| 0.45 | 24.09 | -3.50 | -85.9 | -87.2 | 101.5 | invalid |
| 0.50 | 22.84 | -1.56 | -35.8 | -36.1 | 100.8 | invalid |
| 0.55 | 21.49 | -0.197 | -4.24 | -4.23 | 99.6 | invalid |
| 0.60 | 20.00 | 0.490 | 9.80 | 9.79 | 99.9 | valid |
| 0.65 | 18.53 | 0.710 | 13.158 | 13.126 | 99.76 | valid |
| **0.70** | **17.22** | **0.766** | **13.195** | **13.157** | **99.71** | **valid, ~MPP** |
| 0.75 | 16.08 | 0.782 | 12.567 | 12.537 | 99.77 | valid |
| 0.80 | 15.07 | 0.787 | 11.859 | 11.829 | 99.75 | valid |
| 0.85 | 14.19 | 0.789 | 11.195 | 11.159 | 99.68 | valid |
| 0.90 | 13.39 | 0.790 | 10.585 | 10.558 | 99.74 | valid |

**Interpretation:**
- Vavg tracks `12/D` closely, confirming correct buck + battery behavior.
- The peak lies between D=0.65 and 0.70; estimated MPP duty **~0.68-0.70** at Vpv ~17-18 V, near the datasheet Vmp of 17.1 V.
- **Caveat on claims:** the model was calibrated to Voc only. Vmp landing near 17.1 V is a *model-consistency check*, **not** independent hardware validation. The simulated peak (13.2 W) also exceeds the 12 W rating because the model has no STC derating.
- D <= 0.55 gives negative power and >100 % efficiency. This is the **buck-cannot-reach-battery-voltage / reverse-flow region** (`Vin = 12/D` > Voc), an expected non-physical-for-a-panel artifact of ideal synchronous switches, not a bug. It defines the duty floor.
- Efficiency of ~99.7 % is **optimistic**: ideal gate drive, no switching-loss modeling of the real IRF3205, no driver, no ESR/core loss. Do not quote it as expected hardware efficiency.

#### v1.5 results (2026-11-11, LTspice 26.0.2, `SimFiles/mppt_sim_1.5.asc`)

Changes vs 1.4: 100 kHz, 200 ns dead time, series Schottky (MBRS340) at the PV input with Cin on the converter side, battery stepped 12 V and 14.4 V, duty 0.60 0.64 0.66 0.68 0.70 0.72 0.76 0.80 0.85. MOSFETs still IRFZ44N. Pin is now measured at the panel terminals (Eff includes the diode). Data: `sim/ltspice/results/ltspice_v1.5_sweep.csv`; plots and waveform PNGs in the same folder.

| | v1.4, 12 V | v1.5, 12 V | v1.5, 14.4 V |
|---|---|---|---|
| Best swept duty | 0.70 | **0.68** | **0.80** |
| Vpv there | 17.22 V | 18.08 V | 18.39 V |
| Ppv there | 13.195 W | 13.339 W | 13.253 W |
| Efficiency panel -> battery | 99.71 % | **96.97 %** | 97.18 % |
| Converter only (after diode) | - | 98.74 % | 98.92 % |
| I(L) ripple at D = 0.70 | (0.72 A hand calc.) | 0.36 A pp, min 0.89 A (CCM) | 0.43 A pp |

- The MPP is in the same place (panel ~17.9-18.1 V). The v1.4 "MPP duty 0.70" was a **grid artefact**: 0.65 and 0.70 both sit on the shoulders; the true model Pmax is 13.351 W at Vpv 17.92 V.
- The ~2.7 % efficiency drop is ~1.9 % Schottky loss (0.33 V at 0.76 A) and ~1 % from doubling fsw and dead time (body-diode conduction 4 % of the period). Still optimistic (ideal drive, IRFZ44N).
- At 14.4 V and D <= 0.66 the Schottky blocks: the panel sits at Voc (21.19 V) with ~0 current. The reverse flow seen in v1.4 at low duty no longer reaches the panel. I(L) goes negative (down to -0.28 A) there: forced-CCM circulation between battery and Cin, as predicted in §2.1.
- At D = 0.85 the low-side on-time is 1.1 us (bootstrap refresh window).
- The first batch attempt with `.tran 0 10m 8m 50n` (Tstart = 8 ms) made **every `.meas` FAIL** in LTspice 26.0.2; Tstart must stay 0.

#### v1.6 results (2026-11-11): IRF3205 vendor model

v1.6 = v1.5 with M1/M2 = the Infineon/IR IRF3205 subcircuit (`SimFiles/models/IRF3205.spi`, supplied by the user). Data: `sim/ltspice/results/ltspice_v1.6_sweep.csv`.

| | v1.5 (IRFZ44N), 12 V | v1.6 (IRF3205), 12 V | v1.6, 14.4 V |
|---|---|---|---|
| Best swept duty | 0.68 | 0.68 | 0.80 |
| Vpv there | 18.08 V | 17.93 V | 18.24 V |
| Ppv there | 13.339 W | 13.350 W | 13.308 W |
| Efficiency panel -> battery | 96.97 % | **95.09 %** | 95.40 % |
| Converter only (after diode) | 98.74 % | **96.85 %** | 97.13 % |
| I(L) at D = 0.70 | 0.36 A pp, min 0.88 A | 0.35 A pp, min 0.87 A | 0.41 A pp, min 0.23 A |

- **MPP unchanged** (D = 0.68 at 12 V, 0.80 at 14.4 V), so the P&O design and clamps are unaffected.
- **Turn-off matches the datasheet** (V(SW) starts falling ~50 ns after the command, ~80 ns fall; datasheet td(off) 50 + tf 65 ns typ). It leaves only ~60-70 ns of the 200 ns dead time with an ideal driver; a real IR2110 + gate resistor will eat into that. Confirm on a scope.
- **Efficiency drop of 1.9 points is body-diode reverse recovery** from the model's TT = 100 us (sensitivity: TT = 2.3 ns, scaled from datasheet Qrr 143 nC at 62 A, gives 98.90 %). Real converter efficiency is expected between ~96.9 % and ~98.9 % in the model; **bench data must decide.**
- SIL re-check with eta = 0.9685 (v1.6) instead of 0.9874 (v1.5): tracking changes < 0.05 %, so SIL conclusions stand.

#### v1.7 results (2026-11-11): IR2110 timing + gate resistor, dead-time margin

v1.7 = v1.6 + IR2110 delays (datasheet p.3: on 120/150 ns, off 94/125 ns typ/max), ~6 ohm driver output resistance (15 V / 2.5 A), VCC 12 V (PROPOSED), and a gate network per FET (`SimFiles/models/gate_net_irf3205.sub`: symmetric Rg, or split Rg-on / 1 ohm + diode-off). Margins measured on the internal gate (after the model's 3.97 ohm) against Vth 3.73 V by `sim/ltspice/analyze_v17.py`.

| Dead time | IR2110 corner | Gate-source cap (both FETs) | Overlap per cycle | Low-side Vgs kick | Converter eff. |
|---|---|---|---|---|---|
| 200 ns (decided) | typical | none | **22 ns** | 4.37 V | 94.7 % |
| 200 ns | pessimistic | none | **86 ns** | 5.41 V | 68.5 % |
| 300 ns | typical | none | 9 ns | 3.88 V | 95.8 % |
| 300 ns | typical | 2.2 nF | **0** | 3.60 V | 95.9 % |
| 300 ns | pessimistic | 2.2 nF | 19 ns | 4.10 V | 96.0 % |
| 400 ns | typical | 2.2 nF | **0** | 3.38 V | 94.8 % |
| 400 ns | pessimistic | 2.2 nF | **0** | 3.55 V | 95.6 % |

- **200 ns is not enough in the model with a real driver**: ~22 ns overlap per cycle even with Rg = 0 and typical timing (converter eff 94.7 % vs 96.9 % in v1.6). Symmetric Rg >= 10 ohm breaks the converter in the model.
- **Mechanism: Miller kick on the low-side gate** when M1 turns on (switch node rises ~17 V in tens of ns, couples through Cgd). Unchanged with the datasheet-scaled diode TT, so it is a capacitance effect.
- Longer dead time and a small gate-source capacitor both reduce it; the split gate network fixes edge A but not edge B.
- Caveats: level-1 model exaggerates near-threshold current; Cgd not checked against the datasheet Crss curve; ton min is assumed in the pessimistic corner; no PCB inductance. Direction is credible, numbers need the scope.

#### v1.8 results (2026-11-11): duty sweep at the decided 300 ns

v1.8 = v1.7 with dead time 300 ns, IR2110 typical timing, 12 V drive (PROPOSED), no external Rg, no gate-source capacitor; duty 0.60-0.85 x Vb 12 / 14.4 V. Data: `sim/ltspice/results/ltspice_v1.8_sweep.csv`, `ltspice_v1.8_overlap.csv`.

| | v1.6, 12 V (200 ns, ideal drive) | **v1.8, 12 V (300 ns, IR2110)** | v1.8, 14.4 V |
|---|---|---|---|
| Best swept duty | 0.68 | **0.68** | 0.80 |
| Ppv there | 13.350 W | **13.346 W** | 13.327 W |
| Efficiency panel -> battery | 95.09 % | **94.06 %** | 94.47 % |
| Converter only | 96.85 % | **95.81 %** | 96.19 % |
| Shoot-through overlap per cycle | (ideal drive) | **9.5 ns** | 8.5 ns |

- MPP unchanged (0.68 / 0.80), so P&O, clamps and SIL are unaffected.
- Edge A margin +175 to +250 ns everywhere. Edge B: residual 6-14 ns overlap per cycle at most powered points (Miller kick 3.8-4.0 V vs Vth 3.73 V); none at 12 V, D >= 0.76. v1.7 showed 2.2 nF gate-source cap removes it, so keep the PROPOSED pads.
- Efficiency at the 12 V MPP 94.1 % (converter 95.8 %); ~1 point below v1.6 from the residual overlap, longer body-diode conduction (amplified by the vendor diode storage) and real gate drive.

**Confusion to avoid:** an earlier thread blamed a "stale netlist" for identical logs. That was wrong. The first (24.0.12) log was already produced with the corrected 0.8 A model; repeated identical logs were simply the same circuit.

---

## 3. Current Codebase State & Modular Interfaces

### 3.1 Status

| Module | State |
|---|---|
| Clock init (84 MHz) | **Not written** (parameters in §1.3) |
| TIM1 complementary PWM + dead time | **Drafted in chat, uncompiled/untested** (below) |
| ADC1 + DMA2 | **Not written** |
| INA219 driver (I2C) | **Not written** |
| P&O | **Written** (`firmware/mppt_po.c/.h`, 2026-11-11). Compiles with 0 warnings on host gcc and arm-none-eabi-gcc (M4F hard-float). Exercised in SIL only; **not run on the MCU** |
| CC/CV state machine | **Written** (`firmware/charger_fsm.c/.h`): IDLE, BULK_MPPT, CC_LIMIT, CV_ABSORB, FLOAT, FAULT. Same compile/SIL status as P&O; **not run on the MCU** |
| SIL harness | `sim/sil/` (ctypes + averaged plant, runs a-e); results in `docs/simulation_results.md` §4 |
| Telemetry (UART) | **Not written** |
| Hardware break / protection | **Concept only** |

As of 2026-11-11 the `mppt_po.h` and `charger_fsm.h` parts of 3.3 are implemented with exactly these signatures. Additions: `charger_cfg_t`, `charger_t`, `fault_code_t`, `charger_default_cfg()`, `charger_init()`, `charger_update()` (transition + state action, returns the duty or 0 = PWM off) and `fsm_check_fault()`. `meas_t.vpv` must be measured on the **panel side** of the input Schottky (reason in `charger_fsm.c`); `meas_t.ibat` is the INA219 charge current, positive = charging. The other interfaces (pwm, adc_dma, ina219) are still PROPOSED and unwritten.

### 3.2 TIM1 init (drafted; corrected from the chat version, UNTESTED)

The original chat snippet had a typo (`TIM1_CR1_CMS`; the correct mask is `TIM_CR1_CMS`) and omitted GPIO setup. Corrected:

```c
#include "stm32f401xe.h"

#define TIM1_ARR_VAL   419u      /* (ARR+1)=420 -> 100 kHz center-aligned @ 84 MHz */
#define TIM1_CCR_MAX   420u
#define DEADTIME_DTG   0x19u     /* 25 ticks * 11.9 ns = 297.6 ns (DECIDED 300 ns, 2026-11-11; was 0x28 = 476 ns) */

void pwm_init(void)
{
    /* Clocks */
    RCC->AHB1ENR |= RCC_AHB1ENR_GPIOAEN;
    RCC->APB2ENR |= RCC_APB2ENR_TIM1EN;

    /* PA8 = TIM1_CH1, PA7 = TIM1_CH1N, AF1, high speed, no pull */
    GPIOA->MODER   &= ~((3u<<(8*2)) | (3u<<(7*2)));
    GPIOA->MODER   |=  ((2u<<(8*2)) | (2u<<(7*2)));
    GPIOA->OSPEEDR |=  ((3u<<(8*2)) | (3u<<(7*2)));
    GPIOA->AFR[1]  &= ~(0xFu << ((8-8)*4));
    GPIOA->AFR[1]  |=  (1u   << ((8-8)*4));      /* PA8 AF1 */
    GPIOA->AFR[0]  &= ~(0xFu << (7*4));
    GPIOA->AFR[0]  |=  (1u   << (7*4));          /* PA7 AF1 */

    TIM1->CR1  = 0;
    TIM1->CR1 |= TIM_CR1_CMS_0;                  /* center-aligned mode 1 */
    TIM1->PSC  = 0;
    TIM1->ARR  = TIM1_ARR_VAL;

    /* CH1: PWM mode 1, preload on */
    TIM1->CCMR1 &= ~(TIM_CCMR1_OC1M | TIM_CCMR1_CC1S);
    TIM1->CCMR1 |= TIM_CCMR1_OC1M_2 | TIM_CCMR1_OC1M_1 | TIM_CCMR1_OC1PE;
    TIM1->CCR1  = 0;                              /* start OFF, firmware raises it */

    /* Complementary outputs enabled, active-high both */
    TIM1->CCER |= TIM_CCER_CC1E | TIM_CCER_CC1NE;

    /* Dead time, off-state selection, main output enable */
    TIM1->BDTR = (DEADTIME_DTG & TIM_BDTR_DTG)
               | TIM_BDTR_OSSR | TIM_BDTR_OSSI;  /* drive defined idle levels */
    /* Optional hardware break (BKIN=PA6): TIM1->BDTR |= TIM_BDTR_BKE; set BKP per comparator polarity */
    TIM1->BDTR |= TIM_BDTR_MOE;                   /* set last, after everything else is configured */

    TIM1->EGR  |= TIM_EGR_UG;                     /* load preloads */
    TIM1->CR1  |= TIM_CR1_ARPE | TIM_CR1_CEN;
}

static inline void pwm_set_ccr(uint16_t ccr)
{
    if (ccr > 357u) ccr = 357u;   /* ~D_MAX 0.85; tune after dead-time decision */
    TIM1->CCR1 = ccr;
}
```

**Start-up safety:** before enabling MOE, the driver inputs must default to *both off* (pull-downs on HIN/LIN, or a gate-driver SD pin if available). Power-up with floating GPIOs can shoot through.

### 3.3 Module interfaces (mppt_po.h + charger_fsm.h implemented 2026-11-11; pwm, adc_dma, ina219 still PROPOSED)

```c
/* pwm.h */
void     pwm_init(void);
void     pwm_set_duty(float d);            /* clamps to [D_MIN,D_MAX], CCR1 = (uint16_t)(d*420.0f + 0.5f) */
float    pwm_get_duty(void);
void     pwm_disable(void);                /* MOE=0, both FETs off */

/* adc_dma.h : ADC1 regular group, 2 channels (PA0 vpv, PA1 vbat), DMA2 Stream0 Ch0, circular */
#define ADC_NCH 2u
extern volatile uint16_t adc_raw[ADC_NCH]; /* DMA target; written by hardware */
extern volatile uint8_t  adc_ready;        /* set in DMA TC ISR, cleared by consumer */
void     adc_dma_init(void);
float    adc_get_vpv(void);                /* raw*3.3/4095*DIV_RATIO_PV */
float    adc_get_vbat(void);

/* ina219.h : I2C1 (PB8/PB9), addr 0x40 default */
typedef struct { float i_a; float v_bus; uint8_t valid; } ina219_t;
int      ina219_init(uint16_t calib);      /* writes CONFIG + CALIBRATION */
int      ina219_read(ina219_t *out);       /* returns 0 on success */

/* mppt_po.h */
typedef struct {
    float v_prev, p_prev;
    float duty;
    float step;                            /* e.g. 1/420 */
    float d_min, d_max;
    int8_t dir;                            /* +1 / -1 */
} po_state_t;
void     po_init(po_state_t *s, float d0, float step, float dmin, float dmax);
float    po_update(po_state_t *s, float v, float i);  /* returns new duty */

/* charger_fsm.h */
typedef enum { CS_IDLE, CS_BULK_MPPT, CS_CC_LIMIT, CS_CV_ABSORB, CS_FLOAT, CS_FAULT } charge_state_t;
typedef struct { float vpv, vbat, ibat; } meas_t;
charge_state_t fsm_step(charge_state_t cur, const meas_t *m);
```

### 3.4 ISR / DMA / flag design

- **Not implemented.** PROPOSED: ADC1 triggered by **TIM1 CC2** (external trigger EXTSEL for TIM1_CC2) with CCR2 placed so sampling lands mid-high-side-on-time, away from switching edges. DMA2 Stream0 Channel0, circular, half-word, transfer-complete ISR sets `adc_ready`.
- **Design conflict to resolve:** the original plan said ADC in *continuous conversion* mode. That samples at arbitrary phase and will pick up switching ripple/noise. Timer-triggered sampling is preferred; user must decide.
- Control loop runs from a SysTick (or TIM-based) tick at the P&O period, not from the PWM ISR. All ISR-shared variables are `volatile`; `float` values shared with ISRs need atomic handling (copy under `__disable_irq()` or use a double buffer).
- Fault path: TIM1 BKIN (comparator) -> hardware clears MOE with no CPU involvement; optional `TIM1_BRK_TIM9_IRQHandler` to latch a fault flag and move the FSM to `CS_FAULT`.

### 3.5 CC/CV state machine (implemented 2026-11-11 as below plus IDLE exits; thresholds PROPOSED, see `firmware/charger_fsm.h`)

```
IDLE        -> BULK_MPPT  : Vpv > Vbat + margin (panel can charge) and Vbat in valid range
BULK_MPPT   -> CC_LIMIT   : Ibat >= I_MAX (P&O would exceed battery charge limit)
BULK_MPPT/CC_LIMIT -> CV_ABSORB : Vbat >= V_ABS (14.4 V)
CV_ABSORB   -> FLOAT      : Ibat < I_TAIL (taper complete)
FLOAT       -> BULK_MPPT  : Vbat < V_REBULK
any         -> FAULT      : overcurrent / overvoltage / sensor invalid
```

In CC and CV states, the controller regulates duty to hold current or voltage and the P&O is suspended.

Added in the implementation: `running -> IDLE` when Vpv < Vbat + 0.3 V (night / panel collapse) or Ibat < -0.2 A; `IDLE -> BULK` only after the start condition holds for 1 s (restart hold-off against dawn/dusk chatter); `CC -> BULK` when Ibat < 0.85*I_CC; `CV -> BULK` when Vbat < 14.1 V; FAULT is latched until `charger_init()`. No absorption timer yet.

---

## 4. Known Bugs, Blockers, & Pending Tasks

### 4.1 Hardware / design issues identified (not yet resolved)

1. **Reverse current from the battery into the panel (high priority).** *Update 2026-11-11: a series Schottky at the PV input is now DECIDED (simulation baseline) and is in LTspice v1.5, where it blocks the reverse flow; the firmware stops PWM on panel collapse or Ibat < -0.2 A (SIL run e). The real diode part is not chosen yet.* The panel input has no blocking element. When PV voltage falls (night, shade, or D too low), the battery can drive current through L and **M1's body diode** into the PV side, and a complementary-PWM synchronous buck passes negative inductor current. Fix: series Schottky (or ideal-diode controller) at the PV input, plus firmware that stops PWM when `Vpv*D < Vbat` or PV current ~ 0. The LTspice reverse-flow results at D<=0.55 are the same effect.
2. **Dead time vs. D_max at 100 kHz** (see §2.2; *2026-11-11: 300 ns / D_max 0.85 DECIDED (200 ns first, changed after v1.7), 0.9 us low-side on-time at D_max; bootstrap droop still unsimulated*): low-side on-time collapses near D=0.9, so bootstrap refresh can fail. Decide dead time, D_max, and fsw together; the 50 kHz sim does not cover this.
3. **Simulation/hardware frequency mismatch:** *resolved in v1.5 (100 kHz).* Originally: hardware plan 100 kHz, sim 50 kHz. The originally planned fsw sweep (20/50/100/150/200 kHz) was **never run**.
4. **Charge-current vs. battery rating:** at 12 V, the panel can deliver ~13 W / 12 V ~ **1.1 A, about 0.5 C for a 2.2 Ah SLA**. Typical SLA limits are about 0.25-0.3 C (~0.55-0.66 A); **verify the battery datasheet.** The CC limit will likely be active much of the time in full sun, so MPPT is not the dominant mode. This affects the demo narrative.
   - **Finding (2026-10-14, candidate battery Amptek AT12-2.2, sold by Sharvi; this is a candidate, not a DECIDED part choice):** no AT12-2.2 datasheet exists online. The Amptek AT-series sheet for the 1.3 Ah model (`datasheets/Amptek_AT12-1.3_series_datasheet.pdf`, page 1, "Cycle Use" row) gives initial charge current **< 0.36 A for 1.3 Ah = 0.28 C**. Scaled to 2.2 Ah that is **~0.61 A (derived, unverified)**. An Indian distributor listing (not a manufacturer document) gives < 0.88 A (0.4 C) for the 2.2 Ah. Use the conservative ~0.6 A until Amptek confirms. Either way the ~1.1 A panel current at 12 V is about 1.8x the conservative limit, so the CC limit will be active in full sun, as predicted above.
5. **Float voltage:** the spec lists "absorption/float 14.4 V." Float for SLA is normally lower (~13.5-13.8 V, temperature-dependent); **verify datasheet.** *(2026-11-11: 14.4 V battery case now simulated in v1.5, MPP duty ~0.80. Float set to 13.6 V, DECIDED simulation baseline.)*
   - **Finding (2026-10-14, same Amptek AT-series sheet, 1.3 Ah model; the Sharvi AT12-2.2 listing gives the same voltage ranges):** cycle-use (absorption) **14.4-15.0 V at 25 C, temp. coefficient -30 mV/C**; standby (float) **13.5-13.8 V at 25 C, temp. coefficient -20 mV/C**. This confirms the concern: **14.4 V is correct for absorption but must not be used as float**; float should be 13.5-13.8 V. The coefficients are for the whole 12 V battery per the sheet's wording (verify, as the extracted text is garbled). Charge only at 0-40 C per the sheet. Tail-current threshold for CV to FLOAT is not given by Amptek; still PROPOSED.
   - **Datasheet cross-check (2026-10-14; PDF page numbers, no DECIDED value changed):**
     - *IR2110 logic levels (item 7):* `IR2110.pdf` p.3 gives VIH min 9.5 V and VIL max 6.0 V **at VDD = 15 V**; the 3.3 V MCU cannot drive HIN/LIN if VDD is 15 V. The logic supply VDD may be 3-20 V above VSS (p.2, "VDD: VSS+3 to VSS+20"), so tie **VDD to 3.3 V** and VCC to the 10-20 V gate-drive supply (VCC 10-20 V, p.2). Thresholds scale with VDD; read Fig. 12/13 at VDD = 3.3 V before finalising (not yet read).
     - *IR2110 UVLO (§4.2):* VBS undervoltage 8.6 V typ rising / 8.2 V typ falling, max 9.4 V (p.3). The "~9-10 V" figure used earlier was conservative; bootstrap droop must stay above ~9.4 V worst case.
     - *Dead time (item 2):* IR2110 turn-on 120 ns typ / 150 max, turn-off 94 ns typ / 125 max, delay matching 10 ns max (p.3, CL = 1000 pF). IRF3205 td(off) 50 ns + tf 65 ns typ at Rg = 4.5 ohm (`IRF3205.pdf` p.2). Turn-off of one FET is ~115 ns typ, plus driver mismatch ~10 ns, so the **PROPOSED 150-300 ns** range is supported; 476 ns (DTG 0x28) is far longer than needed. Real value depends on your gate resistor; confirm on a scope.
     - *IRF3205 (item 8):* Qg 146 nC max, Qgs 35, Qgd 54, Rds(on) 8 mOhm max at VGS = 10 V (p.2). Confirms the Cboot derivation inputs in §1.1.
     - *Pins (§1.4), `STM32F401_DS10086.pdf` AF table pp.45-50:* PA8 = TIM1_CH1 AF1, PA7 = TIM1_CH1N AF1, PA6 = TIM1_BKIN AF1, PB12 = TIM1_BKIN AF1 (alt), PB8/PB9 = I2C1_SCL/SDA AF4: all **confirmed**. USART2 AF7 on PA2/PA3 not individually checked. `UM1724` p.24: LD2 user LED is PA5 on the F401RE: confirmed. Solder bridges for free pins/ST-LINK MCO: p.25, not yet reviewed.
6. **INA219 is I2C, not ADC/DMA** (see §1.5). The INA219 module also has **no ALERT pin**, so my earlier suggestion of "an overcurrent comparator on the INA219" needs correction: use a separate shunt + comparator (e.g. LM393-class) into BKIN.
7. **IR2110 logic levels:** verify VIH/VIL against 3.3 V MCU outputs at the chosen logic supply (VDD), and plan a gate-drive supply (>=10-12 V) that exists even with a missing/dead battery.
8. **Inductor saturation/current rating** and **IRF3205 high Qg** at 100 kHz (~15 mA average gate current at 146 nC) not yet checked against the IR2110 and supply.
9. **Sensor noise:** divider source impedance vs. ADC sample time, and switching ripple on ADC samples (see §3.4).

### 4.2 Simulation gaps

Done 2026-11-11: `I(L)`, `V(SW)` and gate waveforms at D = 0.70 / 0.85 (v1.5 PNGs); 14.4 V battery; finer duty steps 0.64-0.72; transient P&O / FSM behaviour (SIL, averaged plant); irradiance step (SIL run a). Still open:

- `I(Vin)` shoot-through spikes (not exported; with ideal 10 ns gate edges and 200 ns dead time none are expected in the model).
- IR2110 bootstrap droop / UVLO (v1.7 models the driver only as delays + output resistance) and PCB gate/source inductance.
- IR2110 macromodel + bootstrap-droop run (check VB-VS never drops below ~9-10 V UVLO at minimum high-side duty... note the *worst* case is **high** duty, where low-side on-time is shortest).
- IRF3205 real model (`.lib` from vendor) for switching/conduction loss; Cboot sizing under realistic Qg.
- Irradiance step at switching level in LTspice (done only in SIL); the missing 0.3 duty point (optional, now outside the clamp range).
- Realistic SLA battery model (the SIL battery is a scaled C + R; absorption taper timing is not realistic).

### 4.3 Immediate next steps (ordered, updated 2026-11-11)

1. ~~IRF3205 SPICE model~~ **done in v1.6** (2026-11-11). **DECIDED (user, 2026-11-11): keep the vendor model unmodified** (no TT-adjusted v1.7); quote efficiency as a range (converter ~96.9-98.9 %, panel->battery ~95-97 %) until bench data exists. Next sim candidate (PROPOSED): IR2110 delays + gate resistor to check the ~60-70 ns dead-time margin seen in v1.6.
2. ~~Decide dead time~~ **DECIDED 300 ns** (user, 2026-11-11, after v1.7). Still PROPOSED: PCB pads for a 2.2 nF gate-source capacitor on each FET and for a split gate network (Rg-on + diode/Rg-off); keep external Rg small unless split. At bring-up, scope the low-side Vgs during high-side turn-on (short ground spring) and adjust. Duty sweep at 300 ns done in v1.8 (residual 6-14 ns overlap without the capacitor).
3. **Decide (user):** real Schottky part for the PV input (40 V+, >= 2 A, low Vf); edge-aligned (840 counts) vs center-aligned (420 counts) PWM; the remaining PROPOSED charger thresholds (tail 0.11 A, re-bulk 12.8 V, absorption timer?); compiler/build system (arm-none-eabi-gcc 14.3 is available inside STM32CubeIDE 2.1.1 on the main PC).
4. Write `clock_init()` (84 MHz) + FPU enable; verify with an MCO or a timer-toggled GPIO on a scope. (The §3.2 TIM1 draft now uses `DEADTIME_DTG 0x19` = 297.6 ns.)
5. Bring up `pwm_init()` **with no power stage connected**: scope CH1/CH1N, confirm complementary outputs, ~300 ns dead time, 100 kHz, CCR-to-duty linearity, clamps 252-357.
6. Hardware Step 1 (assembly + static test) on a current-limited bench supply (not the panel), with Cboot/Dboot, gate resistors, the PV-side Schottky, and a low-voltage first power-up.
7. ADC1+DMA with TIM1-triggered sampling (Vpv divider on the **panel side** of the Schottky), then INA219 over I2C; validate against a multimeter. Measure the real noise and compare with the SIL assumption (6 mV, 1 mA).
8. Link `mppt_po.c` + `charger_fsm.c` (already written) into `main.c` at a 20 ms tick; first test with a bench supply + series resistor emulating a PV curve, then the panel outdoors. Re-tune K_I/K_V on the real battery.
9. Bench data into `bench/`, compare with LTspice v1.5 (MPP duty ~0.68 at 12 V, ~0.80 at 14.4 V) and SIL; only then use the word "validated".

### 4.4 Corrections to statements made earlier in the conversation (so they do not propagate)

- Chat TIM1 snippet used the wrong macro `TIM1_CR1_CMS`; fixed above.
- "Complementary PWM runs in DCM at light load": **incorrect** for a synchronous complementary-driven buck. It is forced-CCM with negative inductor current.
- "Stale netlist" explanation for identical LTspice logs: **incorrect**; see §2.4.
- The claim that the first log reflected a 3.5 A photocurrent: **incorrect**; its currents (~0.79 A max) show the 0.8 A model was already in use.
- Resume wording should reflect: *designed and simulated*; **not** "implemented/validated in hardware."
- (2026-11-11) "MPP duty ~0.70 at 12 V" from v1.4 was a coarse-grid artefact; the finer v1.5 sweep peaks at D = 0.68 (with the Schottky), model Pmax 13.35 W at Vpv ~17.9 V.
- (2026-11-11) A first CV/float gain K_V = 0.5 duty/V looked reasonable on paper but gave near-oscillation in FLOAT in SIL (loop gain ~1.5 near Voc, where 1 PWM count is worth ~87 mA). Use 0.10.
- (2026-11-11) In chat, Claude first said a longer dead time "cannot fix" the Miller kick because the kick happens after the dead time. **Wrong:** the kick adds to the residual low-side gate voltage, so a longer dead time (more discharge time) lowers the peak (4.37 V at 200 ns, 3.88 V at 300 ns, 3.72 V at 400 ns in v1.7).

---

## 5. File Inventory

Main project folder: `C:\Users\Admin\Desktop\Projects\MPPT_SolarCharger\` (set 2026-10-14). Layout and conventions are in `README.md`; rules for Claude sessions are in `CLAUDE.md`.

| Path | Description |
|---|---|
| `PROJECT_STATE.md` | This document (single source of truth) |
| `README.md` | Folder map and naming conventions |
| `CLAUDE.md` | Instructions for Claude sessions (desktop app / Claude Code) |
| `.gitignore` | Excludes LTspice `.raw`/`.db` and firmware build output |
| `SimFiles/mppt_sim_1.5.asc` + `.log` | LTspice v1.5 (2026-11-11): 100 kHz, 200 ns, PV Schottky, 12/14.4 V battery, duty 0.60-0.85, IRFZ44N |
| `SimFiles/mppt_sim_1.4.asc` + `.log` | Previous baseline (50 kHz, duty 0.2-0.9, 12 V); kept unedited |
| `SimFiles/mppt_sim_1.8.asc` + `.log` | **Current** LTspice schematic: decided baseline (300 ns, IR2110 typical, IRF3205, Schottky), duty x Vb sweep |
| `SimFiles/mppt_sim_1.7.asc` + `.log` | LTspice v1.7: v1.6 + IR2110 timing + gate network (dead-time study, 32 steps) |
| `SimFiles/models/gate_net_irf3205.sub` | Project subcircuit: vendor IRF3205 + external gate network (Rgon, optional diode/Rgoff turn-off path) |
| `SimFiles/mppt_sim_1.6.asc` + `.log` | LTspice v1.6: v1.5 + IRF3205 vendor model |
| `SimFiles/models/IRF3205.spi` | Infineon/IR IRF3205 SPICE subcircuit (supplied by the user 2026-11-11) |
| `sim/ltspice/` | `ltspice_raw.py` (.raw/.log parser), `export_ltspice.py` (CSVs, version comparison, waveform PNGs), `tt_sensitivity.sh` (body-diode TT check), `analyze_v17.py` (dead-time metrics), `deadtime_sweep.sh` (dead time x gate-source cap), `overlap_report.py` (shoot-through per step, v1.8+); `results/` holds the v1.4-v1.8 CSVs and PNGs |
| `docs/session_2026-11-11_changelog.md` | What this session added and why, in one place |
| `sim/sil/` | SIL harness: `build.sh` (builds `build/libcharger.dll` from `firmware/`), `charger_lib.py` (ctypes), `plant.py`, `run_sil.py`, `results/` (PNGs, `sil_summary.csv`). `.venv/` is a local Python venv with numpy/matplotlib (git-ignored) |
| `sim/plotstyle.py` | Shared plot style |
| `docs/simulation_results.md` | Simulation write-up (parameters, 1.4 vs 1.5, firmware, SIL runs a-e, limitations) |
| `SimFiles/archive/mppt_sim_1.1 / 1.2 / 1.2_ai_review_1 / 1.3` (`.asc`, `.log`, `.db`) | Superseded (1.3 is byte-identical to 1.4; the others have Rs1 drawn reversed with sign-flipped current measures, details in `SimFiles/SIM_FILE_HISTORY.md`). Moved 2026-10-14 |
| `SimFiles/*.raw` | All deleted 2026-10-14 (~500 MB, regenerable by re-running the `.asc`; git-ignored) |
| `SimFiles/SIM_FILE_HISTORY.md` | Version-by-version differences |
| `firmware/` | `mppt_po.c/.h`, `charger_fsm.c/.h` (2026-11-11, compiled, not flashed); proposed layout for the rest in `firmware/README.md` |
| `datasheets/` | `IRF3205.pdf`, `IR2110.pdf`, `INA219.pdf`, `STM32F401_DS10086.pdf`, `RM0368_STM32F401_reference_manual.pdf`, `UM1724_Nucleo64_user_manual.pdf`, `Amptek_AT12-1.3_series_datasheet.pdf` (battery, 1.3 Ah sibling of the candidate AT12-2.2). Cross-check results in §4.1 items 7-8. INA219 and RM0368 not yet read. Still missing: PV panel, inductor, a real AT12-2.2 sheet. Checklist in `datasheets/README.md` |
| `bench/NOTES.md` | Bench test log (no tests yet) |
| `docs/` | Defense materials (earlier slides not yet copied in) |

**Not in the project folder** (referenced by earlier sessions): `buck_converter.asc` (fixed 15 V source, single 80 % duty point) and `buck_converter_pv_sweep_resload4.asc` (I1=3.5 A, N=37, 3 ohm load). Both are superseded. A second LTspice working copy exists at `C:\Users\Admin\Documents\LTspice\OpenLab1.2\` (the 1.4 log was run from there). Compared 2026-10-14: every `.asc`/`.db`/`.log` there is byte-identical to the project copy; the only files not in the project are the `.raw` / `.op.raw` outputs (not needed). Nothing was copied.

---

## 6. Session Log

| Date | Where | What changed |
|---|---|---|
| ≤ 2026-10-08 | claude.ai free account | Architecture, component selection, LTspice sweep (1.1-1.4), TIM1 init draft, this document |
| 2026-10-09 | Pro account, desktop app | Project "Vishnu_MPPT" set up; verified 1.4 log matches §2.4; compared sim versions |
| 2026-10-14 | Pro account, desktop app | Made `MPPT_SolarCharger` the main folder; added README, CLAUDE.md, .gitignore, `firmware/`, `datasheets/`, `bench/`, `docs/`; corrected §5 inventory. No design changes |
| 2026-10-14 (datasheets) | Claude Code, desktop app | User supplied IR2110, DS10086, RM0368, UM1724 PDFs; added to `datasheets/`, README ticked. Cross-checked IR2110/IRF3205/pin-AF values (see §4.1 item 7 note). No DECIDED values changed |
| 2026-10-14 (battery) | Claude Code, desktop app | Battery datasheet search: candidate Amptek AT12-2.2 (Sharvi); only the AT12-1.3 series sheet found, saved to `datasheets/`; findings added to §4.1 items 4-5. No DECIDED values changed |
| 2026-10-14 (later) | Claude Code, desktop app | Downloaded IRF3205 + INA219 datasheets (IR2110, DS10086, RM0368, UM1724 failed; battery model not given). Deleted `.raw` files, archived sims 1.1-1.3, compared OpenLab1.2 (nothing missing), `git init` + first commit. No design changes |
| 2026-11-11 | Claude Code, desktop app (main PC) | User set the simulation baseline (§1.6, DECIDED). LTspice v1.5 (100 kHz, 200 ns, PV Schottky, 14.4 V case) run in batch and compared with 1.4; waveform PNGs exported by parsing the .raw. Wrote `firmware/mppt_po` + `charger_fsm` (0 warnings, host gcc + arm-none-eabi-gcc M4F). Built SIL in `sim/sil/` (runs a-e); retuned K_V 0.5 -> 0.10 and K_I 0.04 -> 0.08 after SIL. Write-up `docs/simulation_results.md`. IRF3205 SPICE model not obtained. Nothing flashed, no bench data |
| 2026-11-11 (later) | Claude Code, desktop app (main PC) | User supplied `irf3205.spi`. Added `SimFiles/models/IRF3205.spi` and LTspice v1.6 (v1.5 + IRF3205); MPP unchanged, converter eff 96.85 %; TT sensitivity shows the drop is body-diode reverse recovery (98.90 % with datasheet-scaled TT). Export script generalised (`export_ltspice.py`). Wrote `docs/session_2026-11-11_changelog.md`. No DECIDED values changed |
| 2026-11-11 (later) | Claude Code, desktop app (main PC) | User decided to keep the IRF3205 vendor model unmodified; recorded in §4.3. No other changes |
| 2026-11-11 (later) | Claude Code, desktop app (main PC) | LTspice v1.7: IR2110 timing + gate network (new `models/gate_net_irf3205.sub`), 32-step dead-time study + dead-time x Cgs sweep. Finding: 200 ns gives ~22 ns shoot-through per cycle in the model (Miller kick); 300 ns + 2.2 nF clears it at typical timing. Dead time NOT changed (DECIDED 200 ns stands until the user decides); 300 ns PROPOSED. Corrected an earlier chat claim (§4.4) |
| 2026-11-11 (later) | Claude Code, desktop app (main PC) | **User changed the dead time 200 ns -> 300 ns (DECIDED)** after LTspice v1.7. Updated §1.6, §2.2, the §3.2 TIM1 draft (DTG 0x19 = 297.6 ns), §4.1, §4.3, simulation_results.md and the changelog. No simulation re-run |
| 2026-11-11 (later) | Claude Code, desktop app (main PC) | LTspice v1.8: duty sweep at the decided 300 ns with IR2110 typical timing. MPP unchanged (0.68 / 0.80); 12 V MPP 94.1 % (converter 95.8 %); residual 6-14 ns shoot-through without the gate-source cap. Added `overlap_report.py`; export script handles v1.8. No DECIDED values changed |
