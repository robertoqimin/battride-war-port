#!/usr/bin/env bash
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
sdk="${PS3RECOMP_DIR:-$root/../ps3recomp}"
test_dir="$(mktemp -d -t battride-input-test-XXXXXX)"
trap 'rm -rf -- "$test_dir"' EXIT
"${CC:-clang}" -std=gnu17 -O1 -UNDEBUG -I"$sdk/include" $(pkg-config --cflags sdl2) \
  -DPORT_CELLPAD_SOURCE="\"$sdk/libs/input/cellPad.c\"" "$root/tests/test_input_bridge.c" \
  $(pkg-config --libs sdl2) -pthread -lm -o "$test_dir/test"
PORT_CONTROLLER_DB="$root/third_party/SDL_GameControllerDB/gamecontrollerdb.txt" SDL_JOYSTICK_HIDAPI=0 "$test_dir/test"
