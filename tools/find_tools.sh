#!/bin/sh
# Locate the external tools this project needs, on any of our Windows machines (Git Bash).
# Source it:   . tools/find_tools.sh
# Sets (empty if not found):
#   PYBASE   - a 64-bit Python 3 interpreter (used only to create the venv)
#   VENV_PY  - the project venv's python (sim/sil/.venv), if the venv exists
#   CC64     - a 64-bit host gcc (must match 64-bit Python to build the SIL DLL)
#   LTSPICE  - LTspice executable (batch mode: "$LTSPICE" -b file.asc)
#   ARMGCC   - arm-none-eabi-gcc
# Any of these can be forced by exporting it before sourcing this file, e.g.
#   export LTSPICE="/c/Program Files/ADI/LTspice/LTspice.exe"

_ft_root="$(cd "$(dirname "${FT_SELF:-$0}")" 2>/dev/null && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(git -C "${_ft_root:-.}" rev-parse --show-toplevel 2>/dev/null || pwd)}"

_ft_unix() {  # Windows path -> Git Bash path (no-op if already unix-style or cygpath missing)
  if [ -n "$1" ] && command -v cygpath >/dev/null 2>&1; then cygpath -u "$1"; else printf '%s\n' "$1"; fi
}
_ft_first() { for _c in "$@"; do [ -n "$_c" ] && [ -x "$_c" ] && { printf '%s\n' "$_c"; return 0; }; done; return 1; }

_LAD="$(_ft_unix "${LOCALAPPDATA:-}")"
_UPR="$(_ft_unix "${USERPROFILE:-}")"

# ---- 64-bit Python 3 --------------------------------------------------------------------------
if [ -z "${PYBASE:-}" ]; then
  for _c in "py -3" python python3; do
    # shellcheck disable=SC2086
    if $_c -c "import struct,sys; sys.exit(0 if struct.calcsize('P')==8 and sys.version_info>=(3,10) else 1)" >/dev/null 2>&1; then
      PYBASE="$_c"; break
    fi
  done
fi
VENV_PY=""
[ -x "$PROJECT_ROOT/sim/sil/.venv/Scripts/python.exe" ] && VENV_PY="$PROJECT_ROOT/sim/sil/.venv/Scripts/python.exe"
[ -z "$VENV_PY" ] && [ -x "$PROJECT_ROOT/sim/sil/.venv/bin/python" ] && VENV_PY="$PROJECT_ROOT/sim/sil/.venv/bin/python"

# ---- 64-bit host gcc ---------------------------------------------------------------------------
if [ -z "${CC64:-}" ]; then
  for _c in /c/msys64/ucrt64/bin/gcc.exe /c/msys64/mingw64/bin/gcc.exe /c/msys64/clang64/bin/gcc.exe \
            "$(command -v gcc 2>/dev/null)" "$(command -v x86_64-w64-mingw32-gcc 2>/dev/null)"; do
    if [ -n "$_c" ] && [ -x "$_c" ] && "$_c" -dumpmachine 2>/dev/null | grep -q x86_64; then CC64="$_c"; break; fi
  done
fi

# ---- LTspice ----------------------------------------------------------------------------------
if [ -z "${LTSPICE:-}" ]; then
  LTSPICE="$(_ft_first \
    "$_LAD/Programs/ADI/LTspice/LTspice.exe" \
    "$_UPR/AppData/Local/Programs/ADI/LTspice/LTspice.exe" \
    "/c/Program Files/ADI/LTspice/LTspice.exe" \
    "/c/Program Files/LTC/LTspiceXVII/XVIIx64.exe" \
    "/c/Program Files/LTC/LTspiceIV/scad3.exe")" || LTSPICE=""
fi

# ---- arm-none-eabi-gcc ------------------------------------------------------------------------
if [ -z "${ARMGCC:-}" ]; then
  ARMGCC="$(command -v arm-none-eabi-gcc 2>/dev/null)" || ARMGCC=""
  if [ -z "$ARMGCC" ]; then
    for _c in /c/ST/STM32CubeIDE*/STM32CubeIDE/plugins/*gnu-tools-for-stm32*/tools/bin/arm-none-eabi-gcc.exe \
              "/c/Program Files (x86)/GNU Arm Embedded Toolchain"/*/bin/arm-none-eabi-gcc.exe \
              "/c/Program Files/Arm GNU Toolchain arm-none-eabi"/*/bin/arm-none-eabi-gcc.exe \
              /c/ST/STM32CubeCLT*/GNU-tools-for-STM32/bin/arm-none-eabi-gcc.exe; do
      [ -x "$_c" ] && ARMGCC="$_c"   # glob order is alphabetical: the last match is the newest version
    done
  fi
fi

export PROJECT_ROOT PYBASE VENV_PY CC64 LTSPICE ARMGCC
