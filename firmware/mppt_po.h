/*
 * mppt_po.h - Perturb & Observe maximum-power-point tracker (float32, no HAL, no heap).
 *
 * SIGN CONVENTION (read this first)
 *   duty D = high-side on-time / switching period.
 *   The battery clamps the converter output, so Vpv ~= Vbat / D (ideal CCM buck).
 *   => INCREASING D LOWERS the PV operating voltage (moves LEFT on the P-V curve).
 *   => DECREASING D RAISES the PV operating voltage (moves right, toward Voc).
 *   dir = +1 means "next step increases D", dir = -1 means "next step decreases D".
 *
 * Algorithm (PROJECT_STATE.md section 2.3):
 *   P(k) = v * i
 *   if P(k) > P(k-1): keep direction, else: reverse direction
 *   D(k+1) = clamp(D(k) + dir * step, d_min, d_max)
 *   Hitting a clamp also reverses the direction so the tracker walks back into range.
 *
 * The caller chooses which power is tracked. In this design the only current sensor is the
 * INA219 on the charge path, so po_update() is fed Vbat and Ibat (output power). That tracks
 * the PV MPP as long as converter efficiency is roughly constant near the MPP (it is within
 * ~0.1 % in the LTspice v1.5 sweep).
 */
#ifndef MPPT_PO_H
#define MPPT_PO_H

#include <stdint.h>

#define PO_PWM_COUNTS   420.0f                    /* TIM1 ARR+1 at 100 kHz center-aligned */
#define PO_STEP_COUNTS(n) ((float)(n) / PO_PWM_COUNTS)
#define PO_P_INVALID    (-1.0e30f)                /* "no previous sample" marker */

typedef struct {
    float  v_prev, p_prev;    /* previous sample (p_prev = PO_P_INVALID after init) */
    float  duty;              /* last commanded duty */
    float  step;              /* duty step per update, e.g. 1/420 */
    float  d_min, d_max;      /* clamp range */
    int8_t dir;               /* +1 increase D (lower Vpv), -1 decrease D (raise Vpv) */
} po_state_t;

/* d0 is clamped into [dmin, dmax]. Initial direction is +1 (increase D, i.e. load the panel
 * more), because the tracker is normally started from the high-voltage side of the MPP. */
void  po_init(po_state_t *s, float d0, float step, float dmin, float dmax);

/* One P&O iteration. v, i: the voltage and current whose product is maximised.
 * Returns the new duty (also stored in s->duty). Call once per P&O period (20 ms). */
float po_update(po_state_t *s, float v, float i);

#endif /* MPPT_PO_H */
