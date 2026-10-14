# PROJECT_STATE.md: STM32 Synchronous-Buck MPPT Solar Charge Controller

> **Read this first (honesty note for the next session).**
> This is a 3rd-year engineering capstone. As of 2026-10-08 the work completed is **architecture, component selection, and LTspice simulation**. **No firmware has been compiled or flashed, and no hardware has been confirmed built.** The only "code" is one TIM1 register-init snippet drafted in chat (corrected below, untested). Everything labeled **PROPOSED** below is a suggestion that has *not* been agreed or verified. Everything labeled **DECIDED** was stated by the user or locked in the design. Do not treat proposed items as settled.

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
| Switching frequency | **100 kHz (hardware plan)** | **LTspice was run at 50 kHz; frequency sweep never executed** (see §4) |

Cboot derivation (consistent with the stated 292 nF): `Cboot >= 2*Qg/dV = 2 * 146 nC / 1 V = 292 nF`. A practical choice is larger (e.g. 1 uF X7R), which is not yet decided.

### 1.2 Toolchain & environment

- **DECIDED:** Bare-metal C, CMSIS-style register access, no RTOS, no HAL-dependence stated as a goal.
- **NOT DECIDED (needs a user choice):** compiler, build system, IDE, debugger flow.
  - **PROPOSED:** `arm-none-eabi-gcc` + Makefile (or STM32CubeIDE with only CMSIS device headers `stm32f401xe.h` used), flashing via the Nucleo's on-board ST-LINK.
  - **PROPOSED compile flags:** `-mcpu=cortex-m4 -mthumb -mfpu=fpv4-sp-d16 -mfloat-abi=hard -O2 -ffunction-sections -fdata-sections`
  - **Required at startup for the FPU:** `SCB->CPACR |= (0xFUL << 20);` (enable CP10/CP11) before any float math, or you get a HardFault.
- **Numeric format: DECIDED = float32 on the hardware FPU.** There is **no fixed-point specification** in this project; do not invent one unless the user asks.
- **Simulation:** LTspice (24.0.12 on one machine, 26.0.2 on another; same project copied between them). Current file: `SimFiles/mppt_sim_1.4.asc` (byte-identical to `mppt_sim_1.3.asc`).

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
                            DTG=0x28 (40) -> 476 ns   (1 tick = 11.9 ns)
```

**Dead-time concern (new, unresolved):** 476 ns at 100 kHz is 4.8 % of the 10 us period *per edge*, about 9.5 % total. At D = 0.9 the low-side on-time `= 0.1*10us - 2*476ns ~ 48 ns`, which is effectively zero, so **bootstrap refresh and synchronous operation break down near D_max.** Options: reduce dead time to ~150-300 ns (verify IRF3205 turn-off delay + IR2110 propagation on a scope), cap D_max near 0.85, and/or run at 50 kHz. The LTspice run used 100 ns dead time at 50 kHz, not these values.

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

PROPOSED parameters (not agreed):
- `D_MIN = 0.60` (above the 0.57 floor with margin), `D_MAX = 0.85`
- `STEP = 1 count (0.238 %)` to minimize steady-state oscillation (the stated novelty); optionally adaptive (larger when |dP| is large)
- P&O period ~ 10-50 ms (must exceed the settling time of the input/output caps and the INA219 conversion time; INA219 at 12-bit/8x averaging is ~4.3 ms)
- Optional dead-band on |dP| to suppress dither at the MPP
- **Open design question:** with battery-side current only (INA219 on the charge path), P&O tracks *output* power `Vbat*Ibat`, which is valid if converter efficiency is roughly constant. Tracking PV-side power would need a second current sensor.

### 2.4 LTspice model and results (VERIFIED by running; this is the strongest completed work)

**File:** `mppt_sim_1.4.asc` (power stage + single-diode PV model + battery load).

| Element | Value |
|---|---|
| PV photocurrent `I1` | 0.8 A (DC current source, ground -> `PVint`) |
| PV diode `D1` | `.model DPV D(Is=1n N=40)`, `PVint` -> ground. Voc = N*Vt*ln(Iph/Is+1) ~ 40*0.02585*20.5 ~ 21.2 V |
| `Rsh1` | 1500 ohm (PVint -> gnd) |
| `Rs1` | 0.35 ohm (PVint -> PVout) |
| `Cin` | 10 uF (PVout -> gnd) |
| MOSFETs | `M1` (high) / `M2` (low): **IRFZ44N** placeholder (ships in LTspice `standard.mos`); IRF3205 model not yet imported |
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
| P&O | **Not written** |
| CC/CV state machine | **Not written** |
| Telemetry (UART) | **Not written** |
| Hardware break / protection | **Concept only** |

There are **no existing function prototypes or public structs** in the project. The headers in 3.3 are **PROPOSED** interfaces so the next session has a shared starting point.

### 3.2 TIM1 init (drafted; corrected from the chat version, UNTESTED)

The original chat snippet had a typo (`TIM1_CR1_CMS`; the correct mask is `TIM_CR1_CMS`) and omitted GPIO setup. Corrected:

```c
#include "stm32f401xe.h"

#define TIM1_ARR_VAL   419u      /* (ARR+1)=420 -> 100 kHz center-aligned @ 84 MHz */
#define TIM1_CCR_MAX   420u
#define DEADTIME_DTG   0x28u     /* 40 ticks * 11.9 ns = 476 ns; SEE dead-time concern in 2.2 */

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

### 3.3 PROPOSED module interfaces (not yet written)

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

### 3.5 CC/CV state machine (PROPOSED; user only specified "CC/CV bounding MPPT")

```
IDLE        -> BULK_MPPT  : Vpv > Vbat + margin (panel can charge) and Vbat in valid range
BULK_MPPT   -> CC_LIMIT   : Ibat >= I_MAX (P&O would exceed battery charge limit)
BULK_MPPT/CC_LIMIT -> CV_ABSORB : Vbat >= V_ABS (14.4 V)
CV_ABSORB   -> FLOAT      : Ibat < I_TAIL (taper complete)
FLOAT       -> BULK_MPPT  : Vbat < V_REBULK
any         -> FAULT      : overcurrent / overvoltage / sensor invalid
```

In CC and CV states, the controller regulates duty to hold current or voltage and the P&O is suspended.

---

## 4. Known Bugs, Blockers, & Pending Tasks

### 4.1 Hardware / design issues identified (not yet resolved)

1. **Reverse current from the battery into the panel (high priority).** The panel input has no blocking element. When PV voltage falls (night, shade, or D too low), the battery can drive current through L and **M1's body diode** into the PV side, and a complementary-PWM synchronous buck passes negative inductor current. Fix: series Schottky (or ideal-diode controller) at the PV input, plus firmware that stops PWM when `Vpv*D < Vbat` or PV current ~ 0. The LTspice reverse-flow results at D<=0.55 are the same effect.
2. **Dead time vs. D_max at 100 kHz** (see §2.2): low-side on-time collapses near D=0.9, so bootstrap refresh can fail. Decide dead time, D_max, and fsw together; the 50 kHz sim does not cover this.
3. **Simulation/hardware frequency mismatch:** hardware plan 100 kHz, sim 50 kHz. The originally planned fsw sweep (20/50/100/150/200 kHz) was **never run**.
4. **Charge-current vs. battery rating:** at 12 V, the panel can deliver ~13 W / 12 V ~ **1.1 A, about 0.5 C for a 2.2 Ah SLA**. Typical SLA limits are about 0.25-0.3 C (~0.55-0.66 A); **verify the battery datasheet.** The CC limit will likely be active much of the time in full sun, so MPPT is not the dominant mode. This affects the demo narrative.
5. **Float voltage:** the spec lists "absorption/float 14.4 V." Float for SLA is normally lower (~13.5-13.8 V, temperature-dependent); **verify datasheet.** The simulation uses a fixed 12 V battery only; the 14.4 V case is unsimulated.
6. **INA219 is I2C, not ADC/DMA** (see §1.5). The INA219 module also has **no ALERT pin**, so my earlier suggestion of "an overcurrent comparator on the INA219" needs correction: use a separate shunt + comparator (e.g. LM393-class) into BKIN.
7. **IR2110 logic levels:** verify VIH/VIL against 3.3 V MCU outputs at the chosen logic supply (VDD), and plan a gate-drive supply (>=10-12 V) that exists even with a missing/dead battery.
8. **Inductor saturation/current rating** and **IRF3205 high Qg** at 100 kHz (~15 mA average gate current at 146 nC) not yet checked against the IR2110 and supply.
9. **Sensor noise:** divider source impedance vs. ADC sample time, and switching ripple on ADC samples (see §3.4).

### 4.2 Simulation gaps (not done)

- Waveform checks never reported back: `I(L)` CCM/negative-current behavior, `V(SW)` shape, `I(Vin)` shoot-through spikes.
- IR2110 macromodel + bootstrap-droop run (check VB-VS never drops below ~9-10 V UVLO at minimum high-side duty... note the *worst* case is **high** duty, where low-side on-time is shortest).
- IRF3205 real model (`.lib` from vendor) for switching/conduction loss; Cboot sizing under realistic Qg.
- Battery at 14.4 V; irradiance-drop case (e.g. I1 0.8 -> 0.5 A) to show MPP shifting; finer duty steps near the peak (0.66-0.72); the missing 0.3 point (optional).
- Transient P&O behavior is not simulated (only static duty sweep).

### 4.3 Immediate next steps (ordered)

1. **Decide the open parameters:** fsw (50 vs 100 kHz), dead time, D_min/D_max, whether to add the PV-input blocking diode, and compiler/build system.
2. Write `clock_init()` (84 MHz) + FPU enable; verify with an MCO or a timer-toggled GPIO on a scope.
3. Bring up `pwm_init()` **with no power stage connected**: scope CH1/CH1N on the Nucleo pins, confirm complementary outputs, correct dead time (~476 ns or revised), 100 kHz, and CCR-to-duty linearity.
4. Hardware Step 1 (assembly + static test) on a current-limited bench supply (not the panel), with Cboot/Dboot, gate resistors, and a low-voltage first power-up.
5. ADC1+DMA with TIM1-triggered sampling, then INA219 over I2C; validate against a multimeter.
6. P&O loop with duty clamps, tested with a bench supply + series resistor emulating a PV curve (or the real panel outdoors).
7. CC/CV FSM, protections, telemetry; compare measured MPP duty (~0.68-0.70 predicted at 12 V battery) against measurement.
8. Update the LTspice model with the final fsw/dead time/IRF3205 and re-run, then prepare defense data.

### 4.4 Corrections to statements made earlier in the conversation (so they do not propagate)

- Chat TIM1 snippet used the wrong macro `TIM1_CR1_CMS`; fixed above.
- "Complementary PWM runs in DCM at light load": **incorrect** for a synchronous complementary-driven buck. It is forced-CCM with negative inductor current.
- "Stale netlist" explanation for identical LTspice logs: **incorrect**; see §2.4.
- The claim that the first log reflected a 3.5 A photocurrent: **incorrect**; its currents (~0.79 A max) show the 0.8 A model was already in use.
- Resume wording should reflect: *designed and simulated*; **not** "implemented/validated in hardware."

---

## 5. File Inventory

Main project folder: `C:\Users\Admin\Desktop\Projects\MPPT_SolarCharger\` (set 2026-10-14). Layout and conventions are in `README.md`; rules for Claude sessions are in `CLAUDE.md`.

| Path | Description |
|---|---|
| `PROJECT_STATE.md` | This document (single source of truth) |
| `README.md` | Folder map and naming conventions |
| `CLAUDE.md` | Instructions for Claude sessions (desktop app / Claude Code) |
| `.gitignore` | Excludes LTspice `.raw`/`.db` and firmware build output |
| `SimFiles/mppt_sim_1.4.asc` + `.log` | **Current** LTspice schematic and results; steps duty 0.2-0.9 at 50 kHz with PV model + 12 V/0.08 ohm battery |
| `SimFiles/archive/mppt_sim_1.1 / 1.2 / 1.2_ai_review_1 / 1.3` (`.asc`, `.log`, `.db`) | Superseded (1.3 is byte-identical to 1.4; the others have Rs1 drawn reversed with sign-flipped current measures, details in `SimFiles/SIM_FILE_HISTORY.md`). Moved 2026-10-14 |
| `SimFiles/*.raw` | All deleted 2026-10-14 (~500 MB, regenerable by re-running the `.asc`; git-ignored) |
| `SimFiles/SIM_FILE_HISTORY.md` | Version-by-version differences |
| `firmware/` | Empty; proposed module layout in `firmware/README.md` |
| `datasheets/` | Has `IRF3205.pdf` and `INA219.pdf` (not yet read to confirm any §1.1/§4.1 values, so those stay "verify"). Still missing: IR2110, STM32F401 DS10086, RM0368, UM1724 (downloads failed), SLA battery (model not supplied), panel, inductor. Checklist in `datasheets/README.md` |
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
| 2026-10-14 (later) | Claude Code, desktop app | Downloaded IRF3205 + INA219 datasheets (IR2110, DS10086, RM0368, UM1724 failed; battery model not given). Deleted `.raw` files, archived sims 1.1-1.3, compared OpenLab1.2 (nothing missing), `git init` + first commit. No design changes |
