#!/bin/sh
# Run an LTspice schematic in batch mode on any machine:  sh sim/ltspice/run_ltspice.sh SimFiles/mppt_sim_1.8.asc
# Uses the LTspice found by tools/find_tools.sh (or $LTSPICE). Output (.log/.raw/.net) lands next to the .asc.
set -e
[ -n "$1" ] || { echo "usage: sh sim/ltspice/run_ltspice.sh <file.asc>"; exit 2; }
PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
. "$PROJECT_ROOT/tools/find_tools.sh"
[ -n "$LTSPICE" ] || { echo "LTspice not found (export LTSPICE=<path to LTspice.exe>)"; exit 1; }
cd "$(dirname "$1")"
"$LTSPICE" -b "$(basename "$1")"
log="$(basename "$1" .asc).log"
echo "$(head -1 "$log" | tr -d '\r'): $(grep -c '^\.step' "$log") steps, $(grep -c FAIL "$log") failed measurements -> $(dirname "$1")/$log"
