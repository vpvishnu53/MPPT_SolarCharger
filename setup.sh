#!/bin/sh
# One-time setup on a new machine (Windows + Git Bash). Safe to re-run.
#   sh setup.sh          find tools, create the Python venv, build the SIL DLL, compile-check the firmware
#   sh setup.sh --test   ... and then re-run the SIL and LTspice v1.8 in a temp folder and compare the
#                        numbers with the committed results (nothing in the repo is overwritten)
# Tool locations can be forced with environment variables: PYBASE, CC64, LTSPICE, ARMGCC (see tools/find_tools.sh).
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
PROJECT_ROOT="$ROOT"
. "$ROOT/tools/find_tools.sh"

say()  { printf '%s\n' "$*"; }
item() { if [ -n "$2" ]; then printf '  %-22s %s\n' "$1" "$2"; else printf '  %-22s %s\n' "$1" "NOT FOUND ($3)"; fi; }

say "== Tools"
item "Python 3 (64-bit)"  "$PYBASE"  "needed for SIL and plots: install Python 3.10+ 64-bit from python.org"
item "64-bit gcc (host)"  "$CC64"    "needed to build the SIL DLL: install MSYS2 and run 'pacman -S mingw-w64-ucrt-x86_64-gcc'"
item "LTspice"            "$LTSPICE" "needed for SimFiles/*.asc: install LTspice from analog.com, or export LTSPICE=<path>"
item "arm-none-eabi-gcc"  "$ARMGCC"  "needed for the firmware compile check: STM32CubeIDE includes it, or export ARMGCC=<path>"

say "== Python venv (sim/sil/.venv)"
if [ -z "$VENV_PY" ]; then
  [ -n "$PYBASE" ] || { say "  cannot create the venv without Python"; exit 1; }
  # shellcheck disable=SC2086
  $PYBASE -m venv "$ROOT/sim/sil/.venv"
  . "$ROOT/tools/find_tools.sh"
fi
"$VENV_PY" -m pip install -q --disable-pip-version-check -r "$ROOT/requirements.txt"
say "  ok: $("$VENV_PY" -c 'import numpy, matplotlib, pypdf; print("numpy", numpy.__version__, "| matplotlib", matplotlib.__version__, "| pypdf", pypdf.__version__)')"

say "== SIL DLL (sim/sil/build/libcharger.dll)"
if [ -n "$CC64" ]; then sh "$ROOT/sim/sil/build.sh" | sed 's/^/  /'; else say "  skipped (no 64-bit gcc)"; fi

say "== Firmware compile check (Cortex-M4F)"
if [ -n "$ARMGCC" ]; then sh "$ROOT/firmware/check_build.sh" | sed 's/^/  /'; else say "  skipped (no arm-none-eabi-gcc)"; fi

if [ "${1:-}" = "--test" ]; then
  say "== Self-test (temp folder; compares with committed results)"
  "$VENV_PY" "$ROOT/tools/selftest.py"
fi
say "== Done"
