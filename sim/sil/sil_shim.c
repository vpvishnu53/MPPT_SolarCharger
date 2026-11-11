/* sil_shim.c - SIL-only helpers (not firmware). Lets Python check that its ctypes struct
 * layouts match the compiler's, so a header change can't silently corrupt the SIL run. */
#include "charger_fsm.h"

unsigned sil_sizeof_po_state(void)    { return (unsigned)sizeof(po_state_t); }
unsigned sil_sizeof_charger(void)     { return (unsigned)sizeof(charger_t); }
unsigned sil_sizeof_charger_cfg(void) { return (unsigned)sizeof(charger_cfg_t); }
