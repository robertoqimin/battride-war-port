#include "port_ppu_memory.h"
#undef vm_read8
#undef vm_read16
#undef vm_read32
#undef vm_read64
#undef vm_write8
#undef vm_write16
#undef vm_write32
#undef vm_write64
#include <cassert>
#include <cstdio>
#include <vector>
#include <random>
#include <cstring>
#include "spu_coherency.h"
#include "port_ppu_store_gate.h"
static std::vector<uint8_t> memory(1u << 20), expected(memory.size());
static unsigned char bits[(1u << 20) / 128 / 8] = {};
static int armed;
static unsigned slow_reads, slow_writes, wakes;
static bool use_sdk_coherency;
extern "C" const unsigned char* port_spu_coh_bitmap(void);
extern "C" const int* port_spu_coh_armed(void);
extern "C" void spu_ch_wake(spu_context*) { ++wakes; }
extern "C" {
uint8_t* vm_base = memory.data();
uint32_t ppu_vm_size = (uint32_t)memory.size(), ppu_hle_inject_base = 0x30000;
int vm_inline_ok = 1, port_ppu_store_inline_ok = 1;
uint32_t g_null_sweep_hi = 0, g_barrier_sync_watch = 0, port_ppu_store_end;
const unsigned char* port_ppu_coh_bits = bits;
const int* port_ppu_coh_on = &armed;
}
static void encode(uint8_t* to, uint64_t value, unsigned n) {
    for (unsigned i = 0; i < n; ++i) to[i] = (uint8_t)(value >> (8 * (n - i - 1)));
}
static uint64_t read_slow(uint64_t a, unsigned n) {
    ++slow_reads;
    const uint32_t ea = (uint32_t)a;
    if ((uint64_t)ea + n > memory.size()) return 0;
    uint64_t v = 0; for (unsigned i=0; i<n; ++i) v = v * 256 + memory[ea+i];
    return v;
}
static void write_slow(uint64_t a, uint64_t v, unsigned n) {
    ++slow_writes;
    const uint32_t ea = (uint32_t)a;
    if ((uint64_t)ea + n > memory.size()) return;
    if (use_sdk_coherency && spu_coh_is_reserved(ea)) {
        spu_lockline_lock(); encode(memory.data()+ea,v,n);
        spu_coh_notify_write(ea); spu_lockline_unlock();
    } else encode(memory.data()+ea,v,n);
}
extern "C" {
uint8_t vm_read8(uint64_t a) { return (uint8_t)read_slow(a,1); }
uint16_t vm_read16(uint64_t a) { return (uint16_t)read_slow(a,2); }
uint32_t vm_read32(uint64_t a) { return (uint32_t)read_slow(a,4); }
uint64_t vm_read64(uint64_t a) { return read_slow(a,8); }
void vm_write8(uint64_t a,uint8_t v) { write_slow(a,v,1); }
void vm_write16(uint64_t a,uint16_t v) { write_slow(a,v,2); }
void vm_write32(uint64_t a,uint32_t v) { write_slow(a,v,4); }
void vm_write64(uint64_t a,uint64_t v) { write_slow(a,v,8); }
// store_wrap.c's fallbacks, which the linker's --wrap points at the accessors.
void __real_vm_write8(uint64_t a,uint8_t v) { write_slow(a,v,1); }
void __real_vm_write16(uint64_t a,uint16_t v) { write_slow(a,v,2); }
void __real_vm_write32(uint64_t a,uint32_t v) { write_slow(a,v,4); }
void __real_vm_write64(uint64_t a,uint64_t v) { write_slow(a,v,8); }
void __wrap_vm_write8(uint64_t,uint8_t);
void __wrap_vm_write16(uint64_t,uint16_t);
void __wrap_vm_write32(uint64_t,uint32_t);
void __wrap_vm_write64(uint64_t,uint64_t);
}
static void gate() {
    port_ppu_store_end=port_ppu_store_end_for(port_ppu_store_inline_ok,g_null_sweep_hi,ppu_vm_size);
}
static bool via_wrap;   // store through store_wrap.c instead of the inline path
static void store(unsigned n,uint64_t a,uint64_t v) {
    if (via_wrap) {
        switch(n) {case 1:__wrap_vm_write8(a,(uint8_t)v);break;case 2:__wrap_vm_write16(a,(uint16_t)v);break;
                   case 4:__wrap_vm_write32(a,(uint32_t)v);break;case 8:__wrap_vm_write64(a,v);break;}
        return;
    }
    switch(n) {case 1:port_vm_write8(a,(uint8_t)v);break;case 2:port_vm_write16(a,(uint16_t)v);break;
               case 4:port_vm_write32(a,(uint32_t)v);break;case 8:port_vm_write64(a,v);break;}
}
static uint64_t load(unsigned n,uint64_t a) {
    switch(n) {case 1:return vm_read8_inl(a);case 2:return vm_read16_inl(a);
               case 4:return vm_read32_inl(a);default:return vm_read64_inl(a);}
}
int main() {
    std::mt19937_64 random(10220);
    const unsigned widths[] = {1,2,4,8};
    gate();
    for (unsigned i=0; i<300000; ++i) {
        via_wrap = random() & 1;
        const unsigned n = widths[random()%4];
        const uint32_t ea = 0x10000 + (uint32_t)(random() % (memory.size()-0x10008));
        const uint64_t address = ea + ((random()&1) ? (1ull<<32) : 0);
        const uint64_t v = random();
        encode(expected.data()+ea,v,n);store(n,address,v);
        uint64_t reference=0;for(unsigned k=0;k<n;k++)reference=reference*256+expected[ea+k];
        assert(load(n,address)==reference);
    }
    assert(memory==expected);
    // The gate: diagnostics or a null sweep send everything to the accessor,
    // the end follows ppu_vm_size and stays below the raw SPU windows.
    assert(port_ppu_store_end_for(1,0,0)==0xE0000000u && port_ppu_store_end_for(1,0,0xE0000000u)==0xE0000000u);
    assert(port_ppu_store_end_for(1,0,0xF0000000u)==0xE0000000u && port_ppu_store_end_for(1,0,0x100005u)==0x100000u);
    assert(port_ppu_store_end_for(0,0,0)==0x10000u && port_ppu_store_end_for(1,1,0)==0x10000u);
    assert(port_ppu_store_end_for(1,0,0x8000u)==0x10000u);
    for (int w=0; w<2; ++w) for (unsigned n : widths) {
        via_wrap=w;
        const uint32_t ea=0x20080;
        auto fallback = [&](uint64_t a) { unsigned before=slow_writes;store(n,a,123);assert(slow_writes==before+1); };
        port_ppu_store_inline_ok=0;gate();fallback(ea);port_ppu_store_inline_ok=1;gate();
        g_barrier_sync_watch=ea;fallback(ea);g_barrier_sync_watch=0;
        g_null_sweep_hi=1;gate();fallback(ea);g_null_sweep_hi=0;gate();
        armed=1;bits[(ea>>7)>>3]|=(unsigned char)(1u<<((ea>>7)&7));fallback(ea);
        bits[(ea>>7)>>3]=0;
        unsigned before=slow_writes;store(n,ea,456);assert(slow_writes==before);
        armed=0;
        fallback(0);fallback(0x1234);fallback(0xE0004000u);
        fallback((uint32_t)memory.size());
        before=slow_writes;store(n,memory.size()-n,7);assert(slow_writes==before);
        if(n>1) {fallback(ea+1);fallback(ea+128-n+1);fallback(memory.size()-n+1);}
        vm_inline_ok=0;before=slow_reads;load(n,ea);assert(slow_reads==before+1);vm_inline_ok=1;
        before=slow_reads;load(n,ppu_hle_inject_base+0x2008);assert(slow_reads==before+1);
        before=slow_reads;load(n,0x1234);assert(slow_reads==before+1);
        ppu_vm_size=0;gate();store(n,ea,789);assert(load(n,ea)==789u%(n==1?256ull:n==2?65536ull:0x100000000ull));
        ppu_vm_size=(uint32_t)memory.size();gate();
    }
    // Integrate the real SDK reservation table and notification implementation:
    // a PPU write must invalidate a live reservation and wake its SPU holder.
    use_sdk_coherency=true;
    port_ppu_coh_bits=port_spu_coh_bitmap();port_ppu_coh_on=port_spu_coh_armed();
    auto* context=new spu_context{};
    const uint32_t line=0x40000;
    for (int w=0; w<2; ++w) for (unsigned n : widths) {
        via_wrap=w;
        context->resv_ea=line;context->resv_valid=1;context->event_status=0;
        spu_lockline_lock();spu_coh_reserve(context,line);spu_lockline_unlock();
        const unsigned before=slow_writes, previous_wakes=wakes;
        store(n,line+16,0x1234);
        assert(slow_writes==before+1 && !context->resv_valid);
        assert((context->event_status & SPU_EVENT_LR) && wakes==previous_wakes+1);
        // A write to an unrelated line must neither fall back nor kill it.
        context->resv_valid=1;context->event_status=0;
        store(n,line+128,0x5678);
        assert(slow_writes==before+1 && context->resv_valid && !context->event_status);
    }
    spu_coh_unregister(context);delete context;
    std::puts("PASS: 300000 mixed-width memory round trips; byte equivalence; SDK reservation invalidation and wake; reserved/unreserved SPU lines; store gate (store_wrap.c); inline and store_wrap.c paths; diagnostics; null/MMIO/bounds; alignment; reference-word reads; 32-bit address truncation");
}
