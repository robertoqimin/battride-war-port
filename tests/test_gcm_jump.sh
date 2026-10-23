#!/usr/bin/env bash
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
sdk="${PS3RECOMP_DIR:-$root/../ps3recomp}"
test_dir="$(mktemp -d -t battride-gcm-test-XXXXXX)"
trap 'rm -rf -- "$test_dir"' EXIT
"${CC:-clang}" -std=gnu17 -O1 -UNDEBUG -ffunction-sections -fdata-sections \
  -I"$sdk/include" -I"$sdk/libs/video" "$root/tests/test_gcm_jump.c" \
  -Wl,--gc-sections -pthread -lm -o "$test_dir/test"
"$test_dir/test"
"$test_dir/test" legacy
