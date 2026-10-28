#!/usr/bin/env bash
# The port's SIMD VMX float ops (include/ppu_vmx.h) against the SDK's scalar
# originals, bit for bit, on random and edge-case words in both NJ modes.
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
sdk="${PS3RECOMP_DIR:-$root/../ps3recomp}"
dir="$(mktemp -d /tmp/battride-vmx-test.XXXXXX)"
trap 'rm -rf "$dir"' EXIT
gen() {  # gen <prefix> <header dir>
    cat > "$dir/$1.cpp" <<EOF
#include <cstdint>
#include <cstring>
#include <cmath>
#include "ppu_vmx.h"
extern "C" void $1_madd(void* d, const void* a, const void* b, const void* c, uint32_t v) { vmx_vmaddfp(d, a, b, c, v); }
extern "C" void $1_nmsub(void* d, const void* a, const void* b, const void* c, uint32_t v) { vmx_vnmsubfp(d, a, b, c, v); }
extern "C" void $1_add(void* d, const void* a, const void* b, uint32_t v) { vmx_vaddfp(d, a, b, v); }
extern "C" void $1_sub(void* d, const void* a, const void* b, uint32_t v) { vmx_vsubfp(d, a, b, v); }
extern "C" void $1_re(void* d, const void* b, uint32_t v) { vmx_vrefp(d, b, v); }
extern "C" void $1_rsqrte(void* d, const void* b, uint32_t v) { vmx_vrsqrtefp(d, b, v); }
extern "C" uint32_t $1_cmpeq(void* d, const void* a, const void* b) { return vmx_vcmpeqfp(d, a, b); }
extern "C" uint32_t $1_cmpge(void* d, const void* a, const void* b) { return vmx_vcmpgefp(d, a, b); }
extern "C" uint32_t $1_cmpgt(void* d, const void* a, const void* b) { return vmx_vcmpgtfp(d, a, b); }
EOF
}
gen ref; gen port
cxx="${CXX:-g++}"
# The reference is built without FMA so fmaf() is the libm call. With FMA,
# GCC folds the scalar vnmsubfp's -fmaf(x, z, -y) into fnmadd and loses the
# -0 that -(a*c - b) gives when a*c == b; the SIMD version keeps it.
"$cxx" -std=c++20 -O2 -march=x86-64 -ffp-contract=off -c -I"$sdk/runtime/ppu" "$dir/ref.cpp" -o "$dir/ref.o"
"$cxx" -std=c++20 -O2 -march=native -ffp-contract=off -c -I"$root/include" "$dir/port.cpp" -o "$dir/port.o"
"$cxx" -std=c++20 -O2 "$root/tests/test_vmx_simd.cpp" "$dir/ref.o" "$dir/port.o" -o "$dir/test"
"$dir/test"
