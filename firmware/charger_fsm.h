/*
 * charger_fsm.h - SLA charge state machine with P&O as the bulk stage (float32, no HAL, no heap).
 *
 * States and transitions (PROJECT_STATE.md section 3.5, plus the IDLE exits added here):
 *   any       -> FAULT     : overvoltage / overcurrent / sensor reading invalid (latched)
 *   IDLE      -> BULK_MPPT : Vpv > Vbat + start margin, Vbat >= V_BAT_MIN,
 *                            held for restart_holdoff periods (enforced in charger_update)
 *   running   -> IDLE      : Vpv < Vbat + stop margin (panel collapse / night)
 *                            or Ibat < i_reverse (current flowing back out of the battery)
 *   BULK_MPPT -> CV_ABSORB : Vbat >= V_ABS        (checked before the CC test)
 *   BULK_MPPT -> CC_LIMIT  : Ibat >= I_CC
 *   CC_LIMIT  -> CV_ABSORB : Vbat >= V_ABS
 *   CC_LIMIT  -> BULK_MPPT : Ibat < cc_exit_frac * I_CC (panel can no longer supply I_CC)
 *   CV_ABSORB -> FLOAT     : Ibat < I_TAIL (taper complete)
 *   CV_ABSORB -> BULK_MPPT : Vbat < V_ABS - cv_exit_dv (panel can no longer hold V_ABS)
 *   FLOAT     -> BULK_MPPT : Vbat < V_REBULK
 *
 * Measurement convention (meas_t):
 *   vpv  : PV voltage measured on the PANEL side of the input Schottky (see charger_fsm.c note)
 *   vbat : battery terminal voltage
 *   ibat : charger output current from the INA219, positive = charging the battery
 *
 * Duty control per state (duty sign convention as in mppt_po.h: raising D lowers Vpv and,
 * on the high-voltage side of the MPP, raises the charge current):
 *   BULK_MPPT : P&O on Vbat*Ibat
 *   CC_LIMIT  : integral control, D += K_I*(I_CC - Ibat)
 *   CV_ABSORB : D += min(K_V*(V_ABS - Vbat),   K_I*(I_CC - Ibat))
 *   FLOAT     : D += min(K_V*(V_FLOAT - Vbat), K_I*(I_CC - Ibat))
 *   IDLE/FAULT: PWM off
 * The min() keeps the current limit active during CV/float as well.
 */
#ifndef CHARGER_FSM_H
#define CHARGER_FSM_H

#include <stdint.h>
#include "mppt_po.h"

typedef enum { CS_IDLE, CS_BULK_MPPT, CS_CC_LIMIT, CS_CV_ABSORB, CS_FLOAT, CS_FAULT } charge_state_t;

typedef enum { FLT_NONE = 0, FLT_SENSOR, FLT_BAT_OV, FLT_OC } fault_code_t;

typedef struct { float vpv, vbat, ibat; } meas_t;

typedef struct {
    /* DECIDED (simulation baseline, 2026-11-11) */
    float d_min, d_max;        /* 0.60, 0.85 */
    float po_step;             /* 1/420 (1 TIM1 count) */
    float v_abs, v_float;      /* 14.4 V, 13.6 V */
    float i_cc;                /* 0.6 A */
    /* PROPOSED (not agreed; values chosen for the simulation) */
    float i_tail;              /* 0.11 A = 0.05 C of 2.2 Ah */
    float v_rebulk;            /* 12.8 V */
    float cc_exit_frac;        /* 0.85 */
    float cv_exit_dv;          /* 0.30 V */
    float pv_start_margin;     /* 1.0 V */
    float pv_stop_margin;      /* 0.3 V */
    float i_reverse;           /* -0.20 A */
    float v_bat_min;           /* 10.5 V: do not start on a deeply discharged / missing battery */
    float v_bat_ov;            /* 15.0 V fault */
    float i_oc;                /* 1.5 A fault (hardware BKIN comparator is the primary OC path) */
    float v_pv_max;            /* 26.0 V: above the divider full scale = sensor invalid */
    float v_bat_sensor_min;    /* 1.0 V: below this the battery sense is open/invalid */
    float k_i;                 /* 0.08 duty/A per update. Plant dIbat/dD <= ~9 A/unit duty
                                  (LTspice v1.5, 12 V) -> loop gain <= 0.7 */
    float k_v;                 /* 0.10 duty/V per update. Worst case is float near Voc:
                                  dVbat/dD ~ Rb * 37 A/unit ~ 2.9 V/unit -> loop gain ~0.3.
                                  0.5 was tried first: SIL showed near-oscillation in FLOAT */
    float dstep_max;           /* 8/420: max duty change per update in CC/CV/FLOAT */
    uint16_t restart_holdoff;  /* 50 updates = 1 s at 20 ms */
} charger_cfg_t;

typedef struct {
    charge_state_t state;
    po_state_t     po;
    float          duty;       /* last commanded duty (held while PWM is off) */
    uint8_t        pwm_on;     /* 0: MOE off, both FETs off */
    uint8_t        fault;      /* fault_code_t that latched FAULT */
    uint16_t       idle_cnt;   /* consecutive IDLE periods with the start condition true */
} charger_t;

/* Fill cfg with the simulation-baseline values listed above. */
void charger_default_cfg(charger_cfg_t *cfg);

/* Copies cfg into the module (single charger instance) and resets c to IDLE, PWM off. */
void charger_init(charger_t *c, const charger_cfg_t *cfg);

/* Pure transition function (no side effects). Uses the cfg given to charger_init(). */
charge_state_t fsm_step(charge_state_t cur, const meas_t *m);

/* Fault classification used by fsm_step (FLT_NONE if the measurements are acceptable). */
fault_code_t fsm_check_fault(const meas_t *m);

/* Run once per control period (20 ms): transition + state action.
 * Returns the duty to apply, or 0.0f when the PWM must be off (c->pwm_on == 0). */
float charger_update(charger_t *c, const meas_t *m);

#endif /* CHARGER_FSM_H */
