/*
 * charger_fsm.c - charge state machine. See charger_fsm.h for states, transitions and conventions.
 *
 * Why vpv must be measured on the PANEL side of the input Schottky:
 *   with complementary PWM the synchronous buck also runs backwards (boost from the battery
 *   into the input capacitor). At night the Schottky stops current reaching the panel, but the
 *   converter-side input node is then pumped up to about Vbat/D, which is ABOVE Vbat. A divider
 *   on that node would never see the panel collapse. On the panel side the voltage really falls.
 *   The Ibat < i_reverse check is a second, independent way to catch the same condition.
 */
#include "charger_fsm.h"

static charger_cfg_t s_cfg;   /* single instance; set by charger_init() */

static float clampf(float x, float lo, float hi)
{
    if (x < lo) return lo;
    if (x > hi) return hi;
    return x;
}

static float minf(float a, float b) { return (a < b) ? a : b; }

void charger_default_cfg(charger_cfg_t *cfg)
{
    cfg->d_min            = 0.60f;
    cfg->d_max            = 0.85f;
    cfg->po_step          = PO_STEP_COUNTS(1);
    cfg->v_abs            = 14.4f;
    cfg->v_float          = 13.6f;
    cfg->i_cc             = 0.6f;
    cfg->i_tail           = 0.11f;
    cfg->v_rebulk         = 12.8f;
    cfg->cc_exit_frac     = 0.85f;
    cfg->cv_exit_dv       = 0.30f;
    cfg->pv_start_margin  = 1.0f;
    cfg->pv_stop_margin   = 0.3f;
    cfg->i_reverse        = -0.20f;
    cfg->v_bat_min        = 10.5f;
    cfg->v_bat_ov         = 15.0f;
    cfg->i_oc             = 1.5f;
    cfg->v_pv_max         = 26.0f;
    cfg->v_bat_sensor_min = 1.0f;
    cfg->k_i              = 0.08f;
    cfg->k_v              = 0.10f;
    cfg->dstep_max        = PO_STEP_COUNTS(8);
    cfg->restart_holdoff  = 50u;
}

void charger_init(charger_t *c, const charger_cfg_t *cfg)
{
    s_cfg = *cfg;
    c->state    = CS_IDLE;
    c->duty     = cfg->d_min;
    c->pwm_on   = 0u;
    c->fault    = (uint8_t)FLT_NONE;
    c->idle_cnt = 0u;
    po_init(&c->po, cfg->d_min, cfg->po_step, cfg->d_min, cfg->d_max);
}

fault_code_t fsm_check_fault(const meas_t *m)
{
    /* NaN compares false with everything, so a NaN reading fails these range checks too. */
    if (!(m->vbat >= s_cfg.v_bat_sensor_min) || !(m->vpv >= -1.0f) || !(m->vpv <= s_cfg.v_pv_max)
        || !(m->ibat == m->ibat)) {
        return FLT_SENSOR;
    }
    if (m->vbat > s_cfg.v_bat_ov) return FLT_BAT_OV;
    if (m->ibat > s_cfg.i_oc)     return FLT_OC;
    return FLT_NONE;
}

charge_state_t fsm_step(charge_state_t cur, const meas_t *m)
{
    if (cur == CS_FAULT) return CS_FAULT;                 /* latched until charger_init() */
    if (fsm_check_fault(m) != FLT_NONE) return CS_FAULT;

    if (cur == CS_IDLE) {
        if ((m->vpv > m->vbat + s_cfg.pv_start_margin) && (m->vbat >= s_cfg.v_bat_min)) {
            return CS_BULK_MPPT;
        }
        return CS_IDLE;
    }

    /* Running states: panel collapse or reverse current -> stop switching. */
    if ((m->vpv < m->vbat + s_cfg.pv_stop_margin) || (m->ibat < s_cfg.i_reverse)) {
        return CS_IDLE;
    }

    switch (cur) {
    case CS_BULK_MPPT:
        if (m->vbat >= s_cfg.v_abs) return CS_CV_ABSORB;
        if (m->ibat >= s_cfg.i_cc)  return CS_CC_LIMIT;
        return CS_BULK_MPPT;
    case CS_CC_LIMIT:
        if (m->vbat >= s_cfg.v_abs) return CS_CV_ABSORB;
        if (m->ibat < s_cfg.cc_exit_frac * s_cfg.i_cc) return CS_BULK_MPPT;
        return CS_CC_LIMIT;
    case CS_CV_ABSORB:
        if (m->ibat < s_cfg.i_tail) return CS_FLOAT;
        if (m->vbat < s_cfg.v_abs - s_cfg.cv_exit_dv) return CS_BULK_MPPT;
        return CS_CV_ABSORB;
    case CS_FLOAT:
        if (m->vbat < s_cfg.v_rebulk) return CS_BULK_MPPT;
        return CS_FLOAT;
    default:
        return CS_FAULT;                                   /* unknown state: fail safe */
    }
}

float charger_update(charger_t *c, const meas_t *m)
{
    const charge_state_t prev = c->state;
    charge_state_t next = fsm_step(prev, m);

    /* Restart hold-off: the start condition must hold for restart_holdoff consecutive periods.
     * Without it the charger chatters at dusk/dawn: the unloaded panel shows a high Voc, the
     * converter starts, loads the panel, Vpv collapses, the converter stops, and so on. */
    if (prev == CS_IDLE) {
        if (next == CS_BULK_MPPT) {
            if (c->idle_cnt < s_cfg.restart_holdoff) {
                c->idle_cnt++;
                next = CS_IDLE;
            }
        } else {
            c->idle_cnt = 0u;
        }
    }

    /* Entry actions */
    if (next != prev) {
        switch (next) {
        case CS_IDLE:
            c->pwm_on = 0u;
            c->idle_cnt = 0u;
            break;
        case CS_FAULT:
            c->pwm_on = 0u;
            c->fault = (uint8_t)fsm_check_fault(m);
            break;
        case CS_BULK_MPPT:
            if (prev == CS_IDLE) {
                /* Start where the converter draws ~no current: Vbat/D = Vpv(open circuit).
                 * P&O then raises D (dir = +1) toward the MPP. */
                const float d0 = (m->vpv > 0.1f) ? (m->vbat / m->vpv) : s_cfg.d_min;
                po_init(&c->po, d0, s_cfg.po_step, s_cfg.d_min, s_cfg.d_max);
                c->duty = c->po.duty;
                c->pwm_on = 1u;
                c->state = next;
                return c->duty;           /* apply the start duty first, track from the next period */
            }
            po_init(&c->po, c->duty, s_cfg.po_step, s_cfg.d_min, s_cfg.d_max);
            break;
        default:
            break;                        /* CC/CV/FLOAT continue from the present duty */
        }
    }
    c->state = next;

    /* State actions */
    float dd = 0.0f;
    switch (next) {
    case CS_BULK_MPPT:
        c->duty = po_update(&c->po, m->vbat, m->ibat);
        return c->duty;
    case CS_CC_LIMIT:
        dd = s_cfg.k_i * (s_cfg.i_cc - m->ibat);
        break;
    case CS_CV_ABSORB:
        dd = minf(s_cfg.k_v * (s_cfg.v_abs - m->vbat), s_cfg.k_i * (s_cfg.i_cc - m->ibat));
        break;
    case CS_FLOAT:
        dd = minf(s_cfg.k_v * (s_cfg.v_float - m->vbat), s_cfg.k_i * (s_cfg.i_cc - m->ibat));
        break;
    case CS_IDLE:
    case CS_FAULT:
    default:
        return 0.0f;
    }
    dd = clampf(dd, -s_cfg.dstep_max, s_cfg.dstep_max);
    c->duty = clampf(c->duty + dd, s_cfg.d_min, s_cfg.d_max);
    return c->duty;
}
