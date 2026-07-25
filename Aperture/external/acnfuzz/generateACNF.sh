#!/usr/bin/bash
directory=$(dirname "$0")

if [ $# -eq 1 ]; then
  seed=$1
elif [ $# -eq 0 ]; then
  seed=$(od -vAn -N8 -tu8 < /dev/urandom | tr -d '[:space:]')
else
  echo "Invalid arguments. Usage: ./generateACNF.sh [seed]"
  exit 1
fi

# acnfuzz expects a non-negative seed that fits in signed 32-bit.
max_seed=2147483647
if ! [[ "$seed" =~ ^[0-9]+$ ]]; then
  echo "Seed must be numeric."
  exit 1
fi
seed=$(python3 - <<'PY' "$seed" "$max_seed"
import sys
s = int(sys.argv[1])
mx = int(sys.argv[2])
print(s % (mx + 1))
PY
)

echo "c seed $seed"

if [ -x "$directory/acnfuzz" ]; then
  "$directory/acnfuzz" "$seed"
else
  echo "Could not find executable acnfuzz in $directory or $directory/acnfuzz"
  exit 1
fi
