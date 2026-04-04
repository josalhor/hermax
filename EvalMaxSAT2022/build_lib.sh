#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"

UNAME="$(uname -s)"

# Respect CI overrides, otherwise choose sane defaults
CXX="${CXX:-}"
if [[ -z "$CXX" ]]; then
  if [[ "$UNAME" == "Darwin" ]]; then
    CXX="clang++"
  else
    CXX="g++"
  fi
fi

OBJDIR="build_obj"
OUT="libipamirEvalMaxSAT2022.a"
rm -rf "$OBJDIR" "$OUT"
mkdir -p "$OBJDIR"

# IMPORTANT:
#  - Use -I only for dirs that must be found via <...> includes and are safe.
#  - Use -iquote for project headers so we do not shadow system headers like <math.h>.
INC_CADICAL_I=( -I "lib/cadical/src" )
INC_PROJECT_QUOTE=( -iquote "lib/EvalMaxSAT/src" -iquote "lib/MaLib/src" -iquote "." )

CXXFLAGS_COMMON=(
  -fPIC -DNDEBUG -O3 -std=c++17
  -Wall
)

echo "Compiling EvalMaxSAT2022 with $CXX on $UNAME ..."

###############################################################################
# 1) Compile CaDiCaL
###############################################################################
CADICAL_SRC_DIR="lib/cadical/src"
CADICAL_SRCS=()
while IFS= read -r -d '' f; do
  CADICAL_SRCS+=("$f")
done < <(find "$CADICAL_SRC_DIR" -maxdepth 1 -name '*.cpp' -print0)

for f in "${CADICAL_SRCS[@]}"; do
  o="$OBJDIR/cadical_$(basename "${f%.cpp}.o")"
  "$CXX" "${CXXFLAGS_COMMON[@]}" \
    "${INC_CADICAL_I[@]}" "${INC_PROJECT_QUOTE[@]}" \
    -c "$f" -o "$o"
done

###############################################################################
# 2) Compile EvalMaxSAT core
###############################################################################
for f in lib/EvalMaxSAT/src/*.cpp; do
  o="$OBJDIR/eval_$(basename "${f%.cpp}.o")"
  "$CXX" "${CXXFLAGS_COMMON[@]}" \
    "${INC_CADICAL_I[@]}" "${INC_PROJECT_QUOTE[@]}" \
    -c "$f" -o "$o"
done

###############################################################################
# 3) Compile MaLib
###############################################################################
MALIB_SRC="lib/MaLib/src/main.cpp"
"$CXX" "${CXXFLAGS_COMMON[@]}" \
  "${INC_CADICAL_I[@]}" "${INC_PROJECT_QUOTE[@]}" \
  -c "$MALIB_SRC" -o "$OBJDIR/malib_main.o"

###############################################################################
# 4) Compile glue
###############################################################################
GLUE_SRC="ipamirEvalMaxSAT2022glue.cc"
"$CXX" "${CXXFLAGS_COMMON[@]}" \
  "${INC_CADICAL_I[@]}" "${INC_PROJECT_QUOTE[@]}" \
  -c "$GLUE_SRC" -o "$OBJDIR/glue.o"

###############################################################################
# 5) Create archive (macOS: libtool -static to avoid GNU '/' members)
###############################################################################
echo "Creating $OUT ..."
if [[ "$UNAME" == "Darwin" ]]; then
  /usr/bin/libtool -static -o "$OUT" "$OBJDIR"/*.o
  /usr/bin/ranlib "$OUT"
else
  ar rcs "$OUT" "$OBJDIR"/*.o
  ranlib "$OUT" 2>/dev/null || true
fi

echo "Build complete: $OUT"
