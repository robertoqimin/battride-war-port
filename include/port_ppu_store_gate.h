#pragma once
/* The bound the fast store paths (include/port_ppu_memory.h, store_wrap.c)
 * check against: an aligned store at ea goes straight to guest memory only if
 * 0x10000 <= ea < port_ppu_store_end, so with the end a multiple of 8 it also
 * ends at or below it. 0x10000 sends every store to the full accessor: while
 * diagnostics are on (!inline_ok) or a null sweep is being contained. Otherwise
 * the end is the backed arena (ppu_vm_size, 0 = all of it) capped below the
 * 0xE0000000 raw SPU windows. loader_bridge.cpp recomputes
 * port_ppu_store_end whenever one of these inputs changes, so a store pays one
 * load and one compare for all of them. */
#include <stdint.h>

static inline uint32_t port_ppu_store_end_for(int inline_ok, uint32_t null_sweep, uint32_t vm_size)
{
    if (!inline_ok || null_sweep) return 0x10000u;
    const uint32_t end = (vm_size && vm_size < 0xE0000000u) ? vm_size : 0xE0000000u;
    return end < 0x10000u ? 0x10000u : end & ~7u;
}
