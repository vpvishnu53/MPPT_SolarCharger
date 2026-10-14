# LTspice file history (checked 2026-10-09)

Folder: `C:\Users\Admin\Desktop\Projects\MPPT_SolarCharger\SimFiles\`

| File | Status | Difference vs 1.4 |
|---|---|---|
| `mppt_sim_1.4.asc` | **Current** | — (results in `mppt_sim_1.4_results.log`, match PROJECT_STATE §2.4) |
| `mppt_sim_1.3.asc` | Identical to 1.4 | none (byte-identical) |
| `mppt_sim_1.2.asc` | Superseded | Rs1 drawn the other way (`R90` at x=-48); Iavg/Pin measured as `-I(Rs1)` to compensate sign |
| `mppt_sim_1.2_ai_review_1.asc` | Superseded | Same as 1.2 but `u` instead of `µ` for unit prefixes |
| `mppt_sim_1.1.asc` | Superseded | Rs1 orientation as 1.2; Pin used `-V(pvout)*I(Rs1)` |

Note: PROJECT_STATE §5 lists `mppt_sim_1_3.asc`, `buck_converter.asc` and `buck_converter_pv_sweep_resload4.asc`. These are **not** in the project folder (the 1.3 file uses a dot: `mppt_sim_1.3.asc`). The two `buck_converter*` files are either on another machine or gone.

The 1.4 log path shows LTspice ran it from `C:\Users\Admin\Documents\LTspice\OpenLab1.2\`, so a second working copy exists there.
