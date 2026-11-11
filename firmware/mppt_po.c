/* mppt_po.c - Perturb & Observe MPPT. See mppt_po.h for the sign convention. */
#include "mppt_po.h"

static float clampf(float x, float lo, float hi)
{
    if (x < lo) return lo;
    if (x > hi) return hi;
    return x;
}

void po_init(po_state_t *s, float d0, float step, float dmin, float dmax)
{
    s->d_min  = dmin;
    s->d_max  = dmax;
    s->step   = step;
    s->duty   = clampf(d0, dmin, dmax);
    s->dir    = +1;
    s->v_prev = 0.0f;
    s->p_prev = PO_P_INVALID;   /* first update has nothing to compare with: keeps dir */
}

float po_update(po_state_t *s, float v, float i)
{
    const float p = v * i;

    /* dP > 0: the last step helped, keep going. dP <= 0: it hurt (or did nothing), reverse. */
    if (!(p > s->p_prev)) {
        s->dir = (int8_t)(-s->dir);
    }

    float d = s->duty + (float)s->dir * s->step;
    if (d >= s->d_max) {
        d = s->d_max;
        s->dir = -1;            /* at the low-Vpv limit: next step must raise Vpv */
    } else if (d <= s->d_min) {
        d = s->d_min;
        s->dir = +1;            /* at the high-Vpv limit: next step must lower Vpv */
    }

    s->v_prev = v;
    s->p_prev = p;
    s->duty   = d;
    return d;
}
