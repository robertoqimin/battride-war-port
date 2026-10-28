#pragma once
/* Force-included into the generated chunk that defines each function
 * ppu_native.cpp replaces. The lifted definition becomes weak, so the
 * linker sends every call -- from other chunks and from its own -- to the
 * native one, and stays reachable under port_lifted_<name> for
 * PORT_PPU_NATIVE=check. Generated files and ppu_recomp.h are unchanged. */
#include "ppu_recomp.h"

void func_004B5120(ppu_context* ctx) __attribute__((weak));
void port_lifted_func_004B5120(ppu_context* ctx)
    __attribute__((alias("_Z13func_004B5120P11ppu_context")));
