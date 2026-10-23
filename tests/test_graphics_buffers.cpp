#include "ppu_recomp.h"
#undef vm_read32
#include <sys/mman.h>
#include <unordered_map>
extern "C" {uint8_t* vm_base;int vm_inline_ok=1;uint32_t ppu_hle_inject_base=0x20000000;uint32_t ppu_vm_size=0;}
#include <cassert>
#include <cstdlib>
#include <cstdio>
static std::unordered_map<uint32_t,uint32_t> mem;
static int allocations, frees, maps, fail_allocate, fail_map;
extern "C" uint32_t vm_read32(uint64_t a) {return mem[(uint32_t)a];}
extern "C" void vm_write32(uint64_t a,uint32_t v) {mem[(uint32_t)a]=v;uint32_t be=__builtin_bswap32(v);memcpy(vm_base+(uint32_t)a,&be,4);}
extern "C" int64_t sys_memory_allocate(ppu_context* c) {
 allocations++;assert(c->gpr[3]==0x4000000 && c->gpr[4]==0x400);
 if(fail_allocate)return -1;vm_write32(c->gpr[5],0x18000000);return 0;
}
extern "C" int64_t sys_memory_free(ppu_context* c) {assert(c->gpr[3]==0x18000000);frees++;return 0;}
extern "C" int32_t cellGcmMapMainMemory(uint32_t a,uint32_t n,uint32_t* out) {
 maps++;assert(a==0x18000000 && n==0x4000000);if(fail_map)return -1;
 vm_write32((uintptr_t)out,0x1c00000);return 0;
}
extern "C" void port_expand_graphics_buffers(ppu_context*,uint32_t);
static void reset() {
 mem.clear();allocations=frees=maps=fail_allocate=fail_map=0;
 vm_write32(0x13000100,0x10100000);vm_write32(0x13000104,0x10100020);
 for(unsigned i=0;i<2;i++){uint32_t c=0x10100000+32*i,b=0x15300000+0x400000*i;
 vm_write32(c,b);vm_write32(c+4,b+0x3fffc0);vm_write32(c+8,b);vm_write32(c+12,0x6d5a40);}
 vm_write32(0xf100030,0x12345678);
}
int main() {
 vm_base=(uint8_t*)mmap(nullptr,0x100000000ull,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS|MAP_NORESERVE,-1,0);assert(vm_base!=MAP_FAILED);
 ppu_context c{};c.gpr[1]=0xf100000;c.gpr[3]=0x12345;
 reset();unsetenv("PORT_GCM_EXPAND_BUFFERS");port_expand_graphics_buffers(&c,0x13000000);assert(!allocations);
 setenv("PORT_GCM_EXPAND_BUFFERS","0",1);port_expand_graphics_buffers(&c,0x13000000);assert(!allocations);
 setenv("PORT_GCM_EXPAND_BUFFERS","1",1);
 reset();vm_write32(0x10100008,0x15300004);port_expand_graphics_buffers(&c,0x13000000);assert(!allocations);
 reset();fail_allocate=1;port_expand_graphics_buffers(&c,0x13000000);assert(allocations==1&&!maps&&vm_read32(0x10100000)==0x15300000);
 reset();fail_map=1;port_expand_graphics_buffers(&c,0x13000000);assert(frees==1&&vm_read32(0x10100000)==0x15300000);
 reset();port_expand_graphics_buffers(&c,0x13000000);assert(allocations==1&&maps==1&&!frees);
 for(unsigned i=0;i<2;i++){uint32_t a=0x10100000+32*i,b=0x18000000+0x2000000*i;
 assert(vm_read32(a)==b&&vm_read32(a+4)==b+0x1ffffc0&&vm_read32(a+8)==b&&vm_read32(a+12)==0x6d5a40);}
 assert(vm_read32(0x15300000)==0x21c00000 && vm_read32(0x15700000)==0x23c00000);
 assert(c.gpr[3]==0x12345&&vm_read32(0xf100030)==0x12345678);
 port_expand_graphics_buffers(&c,0x13000000);assert(allocations==1);
 puts("PASS: opt-in, empty-context guard, allocation/map failures, disjoint buffers, callback/register/scratch preservation");
}
