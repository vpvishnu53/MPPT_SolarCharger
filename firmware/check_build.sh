#!/bin/sh
# Compile-check the firmware logic for the target (CLAUDE.md rule: must compile with these flags
# before it is handed over). Objects go to firmware/build/ (git-ignored). Fails on any warning.
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$HERE/.." && pwd)"
. "$PROJECT_ROOT/tools/find_tools.sh"
[ -n "$ARMGCC" ] || { echo "arm-none-eabi-gcc not found (export ARMGCC=<path>)"; exit 1; }
mkdir -p "$HERE/build"
for f in mppt_po charger_fsm; do
  "$ARMGCC" -mcpu=cortex-m4 -mthumb -mfpu=fpv4-sp-d16 -mfloat-abi=hard -std=c99 -O2 \
    -ffunction-sections -fdata-sections \
    -Wall -Wextra -Wpedantic -Wdouble-promotion -Wconversion -Wshadow -Werror \
    -c "$HERE/$f.c" -o "$HERE/build/$f.o"
done
"$(dirname "$ARMGCC")/arm-none-eabi-size" "$HERE"/build/*.o | sed 's#[^[:space:]]*/build/#build/#'
echo "firmware: compiled for Cortex-M4F with 0 warnings ($("$ARMGCC" -dumpversion))"
