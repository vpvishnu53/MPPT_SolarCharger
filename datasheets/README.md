# Datasheets checklist

Put the vendor PDFs here. Each one settles open items in PROJECT_STATE.md.

| Part | Get it from | What it settles |
|---|---|---|
| [x] IRF3205 (`IRF3205.pdf`, Infineon, downloaded 2026-10-14) | Infineon | Qg (Cboot sizing, gate-drive current at 100 kHz), Rds(on), turn-on/off delays (dead time); also the SPICE `.lib` for a real model |
| [ ] IR2110 (download failed 2026-10-14) | Infineon | VIH/VIL vs 3.3 V logic, propagation delay (dead time), UVLO (bootstrap droop), VDD/VCC supply ranges |
| [x] INA219 (`INA219.pdf`, TI, downloaded 2026-10-14) | TI | Conversion time vs P&O period, calibration register, shunt range on your module |
| [ ] (not attempted: battery model not given) SLA battery 12 V 2.2 Ah | your battery's maker (exact model on the label) | Max charge current (0.25-0.3 C?), absorption and **float** voltage, temperature compensation |
| [ ] PV panel 12 W | panel label / seller | Isc, Imp, Voc, Vmp at STC |
| [ ] 100 ÂµH inductor | seller / part number | Saturation current and DC resistance |
| [ ] (download failed 2026-10-14) STM32F401xD/xE datasheet | ST (DS10086) | Alternate-function table (pin map in Â§1.4) |
| [ ] (download failed 2026-10-14) RM0368 reference manual | ST | TIM1, ADC, DMA, RCC registers |
| [ ] (download failed 2026-10-14) UM1724 Nucleo-64 user manual | ST | Which pins are free, solder bridges, ST-LINK MCO clock |

Name files plainly, e.g. `IRF3205.pdf`, `RM0368_STM32F401_reference_manual.pdf`.

