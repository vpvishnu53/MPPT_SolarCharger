#!/bin/sh
# Build the firmware control logic (unchanged sources from firmware/) as a host shared library
# for the Python SIL harness. Needs a 64-bit gcc matching the 64-bit Python
# (found by tools/find_tools.sh, e.g. MSYS2 UCRT64 gcc; a 32-bit gcc such as C:\MinGW cannot be used).
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
FW="$HERE/../../firmware"
mkdir -p "$HERE/build"
PROJECT_ROOT="$(cd "$HERE/../.." && pwd)"
. "$PROJECT_ROOT/tools/find_tools.sh"
CC="$CC64"
[ -n "$CC" ] || { echo "no 64-bit gcc found (install MSYS2 UCRT64 gcc or export CC64=<path>)"; exit 1; }
"$CC" -std=c99 -O2 -Wall -Wextra -Wpedantic -Wdouble-promotion -Wconversion -Wshadow \
  -shared -static-libgcc -I"$FW" \
  "$FW/mppt_po.c" "$FW/charger_fsm.c" "$HERE/sil_shim.c" \
  -o "$HERE/build/libcharger.dll"
echo "built $HERE/build/libcharger.dll"
