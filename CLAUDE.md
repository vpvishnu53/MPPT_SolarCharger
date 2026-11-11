# Instructions for Claude (desktop app or Claude Code)

## Git routine (do this every session)
- Repo: https://github.com/vpvishnu53/MPPT_SolarCharger (private; shared with a teammate).
- At the start of every session: run `git pull` before reading or changing anything.
- At the end of a session that changed files: update `PROJECT_STATE.md` (session log), then
  `git add -A`, `git commit -m "<short summary>"`, `git push`.
- If the pull shows conflicts, stop and ask the user before resolving them.
- Never edit an `.asc` file someone else may be editing; LTspice files can't be merged. Make a new version number instead.
- On a machine where `sim/sil/.venv` does not exist yet (new laptop, fresh clone): run `sh setup.sh --test` first and report what it found. Don't hard-code tool paths in scripts or docs; use `tools/find_tools.sh` (`$LTSPICE`, `$CC64`, `$ARMGCC`, `$VENV_PY`).

## Before doing anything
1. Read `PROJECT_STATE.md`. It is the single source of truth for this project.
2. Respect its labels: **DECIDED** items are settled; **PROPOSED** items are suggestions only. Don't present proposed values as agreed, and don't change a decided value without the user's approval.
3. Read section 4.4 (earlier mistakes) so they aren't repeated.

## Project facts that are easy to get wrong
- MCU: STM32F401RE (Nucleo-F401RE), Cortex-M4F, 84 MHz max. Bare-metal C with CMSIS device headers (`stm32f401xe.h`), no HAL, no RTOS.
- Math is float32 on the hardware FPU. Enable it (`SCB->CPACR |= 0xF << 20`) before any float math. There is no fixed-point spec; don't invent one.
- The INA219 is I2C. It is **not** read via ADC/DMA.
- A complementary-driven synchronous buck is forced-CCM: inductor current goes negative at light load instead of entering DCM.
- Simulations ran at 50 kHz with 100 ns dead time; the hardware plan is 100 kHz. Don't mix up the two.
- Simulated results are model results, not hardware validation. Say "designed and simulated", never "validated", until there is bench data in `bench/`.

## Working rules
- Check component values against the PDFs in `datasheets/` and cite the table or page. If the datasheet isn't there, say so and mark the value "unverified".
- Firmware goes in `firmware/`. It must compile with `arm-none-eabi-gcc -mcpu=cortex-m4 -mthumb -mfpu=fpv4-sp-d16 -mfloat-abi=hard` before it is handed to the user.
- New LTspice variants: copy the latest `SimFiles/mppt_sim_X.Y.asc` to the next version number; don't edit old versions. Log the change in `SimFiles/SIM_FILE_HISTORY.md`.
- Read bench data (scope PNGs, UART logs) directly from `bench/` rather than relying on the user's summary.
- At the end of a session that changed anything, update `PROJECT_STATE.md`: decisions, results, bug fixes, the next-steps list, and the session log at the bottom.
- This is a student capstone that the user must defend. Explain the reasoning behind design choices, not just the result.
