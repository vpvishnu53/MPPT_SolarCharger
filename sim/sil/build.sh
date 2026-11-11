#!/bin/sh
# Build the firmware control logic (unchanged sources from firmware/) as a host shared library
# for the Python SIL harness. Needs a 64-bit gcc matching the 64-bit Python
# (on this PC: MSYS2 UCRT64 gcc; C:\MinGW\bin\gcc is 32-bit and cannot be used).
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
FW="$HERE/../../firmware"
mkdir -p "$HERE/build"
CC="${CC:-/c/msys64/ucrt64/bin/gcc}"
"$CC" -std=c99 -O2 -Wall -Wextra -Wpedantic -Wdouble-promotion -Wconversion -Wshadow \
  -shared -static-libgcc -I"$FW" \
  "$FW/mppt_po.c" "$FW/charger_fsm.c" "$HERE/sil_shim.c" \
  -o "$HERE/build/libcharger.dll"
echo "built $HERE/build/libcharger.dll"
