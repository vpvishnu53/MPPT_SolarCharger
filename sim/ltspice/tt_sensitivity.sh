#!/bin/sh
# Sensitivity of v1.6 efficiency to the IRF3205 body-diode transit time TT (reverse-recovery charge).
# The vendor model ships TT = 100 us; the datasheet Qrr (143 nC at IF = 62 A) implies ~2.3 ns.
# Runs one point (D = 0.68, Vb = 12 V, the 12 V MPP) per TT value in a temporary folder;
# nothing in SimFiles/ is modified. Needs SimFiles/mppt_sim_1.6.net (created by running the .asc once).
set -e
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SIMF="$ROOT/SimFiles"
LT="${LTSPICE:-/c/Users/Admin/AppData/Local/Programs/ADI/LTspice/LTspice.exe}"
TMP="$(mktemp -d)"
cd "$TMP"
for tt in 1e-4 2.3e-9 0; do
  sed "s/TT=0.0001/TT=$tt/" "$SIMF/models/IRF3205.spi" > "m_$tt.spi"
  sed -e "s#^.include models/IRF3205.spi#.include m_$tt.spi#" \
      -e 's/^.step param Duty list.*/.param Duty=0.68/' \
      -e 's/^.step param Vb list.*/.param Vb=12/' \
      -e 's/^.save.*/.save V(PVpanel) I(Rs1) V(PVout) I(D2) V(vout) I(R1) I(L)/' \
      "$SIMF/mppt_sim_1.6.net" > "tt_$tt.net"
  "$LT" -b "tt_$tt.net"
  echo "TT = $tt"
  grep -E "^(pin|pconv|pout|eff|effconv):" "tt_$tt.log"
done
echo "(temporary files in $TMP)"
