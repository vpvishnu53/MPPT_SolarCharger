# Firmware

Bare-metal C for the STM32F401RE, CMSIS register access, float32 on the FPU, no RTOS.
Toolchain and build system are **not decided yet** (see PROJECT_STATE.md §1.2).

Written so far (2026-11-11): `mppt_po.c/.h` (P&O) and `charger_fsm.c/.h` (charge state machine). They compile with `arm-none-eabi-gcc -mcpu=cortex-m4 -mthumb -mfpu=fpv4-sp-d16 -mfloat-abi=hard` (0 warnings) and are exercised by the SIL harness in `sim/sil/`. Not flashed. They will move into `src/` once the layout below is set up (update `sim/sil/build.sh` then).

Proposed layout once work starts (matches the interfaces in PROJECT_STATE.md §3.3):

```
firmware/
├── Makefile               (or a CubeIDE project using only CMSIS headers)
├── startup/               startup_stm32f401xe.s, linker script
├── cmsis/                 stm32f401xe.h, core_cm4.h, ...
├── src/
│   ├── main.c
│   ├── clock.c   / .h     84 MHz PLL, flash wait states, FPU enable
│   ├── pwm.c     / .h     TIM1 complementary PWM + dead time + break
│   ├── adc_dma.c / .h     ADC1 + DMA2, TIM1-triggered sampling
│   ├── ina219.c  / .h     I2C1 driver
│   ├── mppt_po.c / .h     Perturb & Observe
│   ├── charger_fsm.c / .h CC/CV state machine
│   └── telemetry.c / .h   USART2 to the ST-LINK virtual COM port
└── build/                 (ignored by git)
```

Make this folder (or the whole project folder) a git repo before the first source file goes in.
