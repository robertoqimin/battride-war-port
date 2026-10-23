/*
 * ps3recomp game project -- game-specific hooks and overrides.
 *
 * main.cpp is the runner and is game-agnostic. This file is where a port puts
 * everything that is not: the PRX loading hook it must answer, overrides for
 * firmware functions the HLE library gets wrong for this title, and patches
 * over recompiled code.
 *
 * It starts out as the empty version of all of that, which is what a game with
 * no lifted PRX and no overrides needs.
 */

#include <cstdio>
#include <cstdlib>
#include <cstring>

#include "ps3emu/ps3types.h"
#include "ps3emu/error_codes.h"

/* ---------------------------------------------------------------------------
 * PRX loading
 *
 * main.cpp calls this once, after the lifted function table is registered and
 * vm_base is live, before the game runs. A title that lifts a real system PRX
 * -- libsre, which is cellSpurs and cellSync -- loads its image into guest RAM
 * here and registers its exports. Most ports never need to: the HLE library
 * answers those modules instead.
 * -----------------------------------------------------------------------*/

extern "C" void ps3_load_prx_modules(void)
{
}

/* ---------------------------------------------------------------------------
 * Example: Override a specific NID
 *
 * The module system resolves function imports by NID.  To replace a default
 * HLE stub with custom logic, register your function at init time.
 * -----------------------------------------------------------------------*/

/*
 * Example: override cellGcmSetFlipMode (NID 0xA53D12AE) to force vsync.
 *
 *   static void my_cellGcmSetFlipMode(u32 mode)
 *   {
 *       printf("[hook] cellGcmSetFlipMode: forcing VSYNC (was %u)\n", mode);
 *       // Force vsync regardless of what the game requested
 *       cellGcmSetFlipMode(CELL_GCM_DISPLAY_VSYNC);
 *   }
 *
 * Then in your init code:
 *
 *   ps3::modules::override_nid(0xA53D12AE,
 *       reinterpret_cast<void*>(my_cellGcmSetFlipMode));
 */

/* ---------------------------------------------------------------------------
 * Example: Hook into module loading
 *
 * You can intercept cellSysmoduleLoadModule to perform custom actions
 * when a particular module is loaded.
 * -----------------------------------------------------------------------*/

/*
 *   static s32 my_loadmodule_hook(u16 id)
 *   {
 *       printf("[hook] Module 0x%04X loaded\n", id);
 *
 *       if (id == CELL_SYSMODULE_AUDIO) {
 *           // Perform custom audio backend initialization
 *           init_my_audio_backend();
 *       }
 *
 *       // Call the original implementation
 *       return cellSysmoduleLoadModule(id);
 *   }
 */

/* ---------------------------------------------------------------------------
 * Game-specific patches
 *
 * Sometimes you need to patch recompiled code at specific addresses.
 * Use the patch system to modify behavior without editing generated code.
 * -----------------------------------------------------------------------*/

/*
 *   // Skip an integrity check at guest address 0x00812FA0
 *   ps3::patches::nop_range(0x00812FA0, 0x00812FB0);
 *
 *   // Replace a function call with a direct return
 *   ps3::patches::force_return(0x009A1000, 0);  // return 0
 */

/* BLJS10220 import adapters; all pointer arguments remain guest EAs. */
#include "ppu_recomp.h"
#include <cstdint>
#include <atomic>
extern "C" {
void ps3_hle_register_ctx(uint32_t, const char*, void (*)(ppu_context*));
int32_t cellKbGetData(uint32_t, void*);
int32_t cellFontFTInit(const void*, void*);
uint64_t ppu_guest_call(uint32_t, uint64_t, uint64_t, uint64_t, uint64_t, uint64_t, uint64_t, uint64_t, uint64_t);
}
static void port_kb_read(ppu_context* c)
{
    c->gpr[3] = (uint64_t)(int64_t)cellKbGetData((uint32_t)c->gpr[3],
        (void*)(uintptr_t)(uint32_t)c->gpr[4]);
}
static void port_font_init(ppu_context* c)
{
    /* Revision is r3; config and library-out are r4/r5. Uses the runtime's
     * fallback font library (not a full FreeType rasterizer). */
    c->gpr[3] = (uint64_t)(int64_t)cellFontFTInit(
        (void*)(uintptr_t)(uint32_t)c->gpr[4],
        (void*)(uintptr_t)(uint32_t)c->gpr[5]);
}
/* The initialize API registers four guest callback OPDs. Attach/detach APIs
 * invoke the corresponding OPD through the runtime's nested guest dispatcher. */
static std::atomic<uint32_t> port_printf_callbacks[4];
static void port_spu_printf_init(ppu_context* c)
{
    for (unsigned i=0;i<4;i++) port_printf_callbacks[i].store((uint32_t)c->gpr[3+i]);
    std::fprintf(stderr, "[port] SPU printf callbacks registered\n");
    c->gpr[3] = 0;
}
static void port_spu_printf_finalize(ppu_context* c)
{
    for (auto& cb:port_printf_callbacks) cb.store(0);
    c->gpr[3] = 0;
}
template<unsigned Slot> static void port_spu_printf_callback(ppu_context* c)
{
    uint32_t opd=port_printf_callbacks[Slot].load();
    c->gpr[3] = opd ? ppu_guest_call(opd,c->gpr[3],0,0,0,0,0,0,0)
                       : (uint64_t)(int64_t)(int32_t)0x8001000Fu;
}
extern "C" int32_t cellSysutilQueueGuestCallbackArgs(uint32_t, const uint64_t[8]);
static std::atomic<uint32_t> port_search_callback{0}, port_search_userdata{0};
static void port_search_init(ppu_context* c)
{
    int32_t error=0;
    uint32_t cb=(uint32_t)c->gpr[5], expected=0;
    if (c->gpr[3]!=0) error=(int32_t)0x8002C804u;
    else if (!cb) error=(int32_t)0x8002C801u;
    else if (!port_search_callback.compare_exchange_strong(expected,cb)) error=(int32_t)0x8002C805u;
    else {
        port_search_userdata.store((uint32_t)c->gpr[6]);
        uint64_t args[8]={1,0,0,c->gpr[6],0,0,0,0};
        error=cellSysutilQueueGuestCallbackArgs(cb,args);
        if (error) port_search_callback.store(0);
    }
    c->gpr[3]=(uint64_t)(int64_t)error;
}
static void port_search_finalize(ppu_context* c)
{
    uint32_t cb=port_search_callback.load();
    int32_t error=(int32_t)0x8002C806u;
    if (cb) {
        uint64_t args[8]={2,0,0,port_search_userdata.load(),0,0,0,0};
        error=cellSysutilQueueGuestCallbackArgs(cb,args);
        if (!error) port_search_callback.store(0);
    }
    c->gpr[3]=(uint64_t)(int64_t)error;
}
/* This port has no mounted user-media catalog. List searches therefore
 * complete with a real zero-entry result, asynchronously through sysutil. */
extern "C" void* sys_heap_malloc(uint32_t, uint32_t);
extern "C" int32_t sys_heap_free(uint32_t, void*);
void vm_write32(uint64_t, uint32_t);
static std::atomic<uint32_t> port_search_result{0};
static void port_search_list(ppu_context* c)
{
    int32_t error=(int32_t)0x8002C801u;
    uint32_t out=(uint32_t)c->gpr[5], cb=port_search_callback.load();
    if (!cb) error=(int32_t)0x8002C806u;
    else if (c->gpr[3]>=1 && c->gpr[3]<=9 && (c->gpr[4]==1 || c->gpr[4]==2) && out) {
        if (port_search_result.load()) error=(int32_t)0x8002C802u;
        else {
            uint32_t result=(uint32_t)(uintptr_t)sys_heap_malloc(0,8);
            if (!result) error=(int32_t)0x8002C803u;
            else {
                vm_write32(out,1); vm_write32(result,1); vm_write32(result+4,0);
                uint64_t args[8]={3,0,result,port_search_userdata.load(),0,0,0,0};
                error=cellSysutilQueueGuestCallbackArgs(cb,args);
                if (!error) port_search_result.store(result);
                else sys_heap_free(0,(void*)(uintptr_t)result);
            }
        }
    }
    c->gpr[3]=(uint64_t)(int64_t)error;
}
static void port_search_end(ppu_context* c)
{
    uint32_t result=port_search_result.load();
    int32_t error=(int32_t)0x8002C80Du;
    if (c->gpr[3]==1 && result) {
        sys_heap_free(0,(void*)(uintptr_t)result);
        port_search_result.store(0); error=0;
    }
    c->gpr[3]=(uint64_t)(int64_t)error;
}
static std::atomic<uint32_t> port_music_callback{0}, port_music_userdata{0};
static void port_music_init(ppu_context* c)
{
    int32_t error=(int32_t)0x8002C102u;
    if (c->gpr[3]==0 && c->gpr[4]>=16 && c->gpr[4]<=255 && c->gpr[5]) {
        uint64_t args[8]={1,0,c->gpr[6],0,0,0,0,0};
        error=cellSysutilQueueGuestCallbackArgs((uint32_t)c->gpr[5],args);
        if (!error) {
            port_music_callback.store((uint32_t)c->gpr[5]);
            port_music_userdata.store((uint32_t)c->gpr[6]);
        }
    }
    c->gpr[3]=(uint64_t)(int64_t)error;
}
uint32_t vm_read32(uint64_t);
extern "C" void ppu_dump_guest_stack(ppu_context*, const char*);
extern "C" int32_t cellGameContentErrorDialog(int32_t,int32_t,const char*);
static void port_content_error_trace(ppu_context* c)
{
    std::fprintf(stderr,"[port-data-error] lr=0x%08X r3=%08X r4=%08X r5=%08X\n",
        (uint32_t)c->lr,(uint32_t)c->gpr[3],(uint32_t)c->gpr[4],(uint32_t)c->gpr[5]);
    uint32_t slot=vm_read32(c->gpr[2]-0x3C2C), manager=vm_read32(slot);
    std::fprintf(stderr,"[install-state] toc=%08X slot=%08X manager=%08X flags=%08X\n",
        (uint32_t)c->gpr[2],slot,manager,vm_read32(manager+0x48));
    ppu_dump_guest_stack(c,"content-error");
    c->gpr[3]=(uint64_t)(int64_t)cellGameContentErrorDialog((int32_t)c->gpr[3],
        (int32_t)c->gpr[4],(const char*)(uintptr_t)(uint32_t)c->gpr[5]);
}
/* ListAutoSave differs from FixedSave2 by its error-dialog parameter and
 * ninth PPC64 argument; both use the same fixed-directory callback contract. */
extern "C" int32_t cellSaveDataFixedSave2(uint32_t,void*,void*,void*,void*,void*,uint32_t,void*);
uint64_t vm_read64(uint64_t);
static std::atomic<bool> port_save_overlay{false};
static void port_save_overlay_set(ppu_context* c)
{
    port_save_overlay.store(c->gpr[3]!=0);
}
static void port_save_list_auto(ppu_context* c)
{
    if(c->gpr[4]>2) {c->gpr[3]=(uint64_t)(int64_t)(int32_t)0x8002B404u;return;}
    uint32_t userdata=(uint32_t)vm_read64((uint32_t)c->gpr[1]+112u);
    int32_t result=cellSaveDataFixedSave2((uint32_t)c->gpr[3],
        (void*)(uintptr_t)(uint32_t)c->gpr[5],(void*)(uintptr_t)(uint32_t)c->gpr[6],
        (void*)(uintptr_t)(uint32_t)c->gpr[7],(void*)(uintptr_t)(uint32_t)c->gpr[8],
        (void*)(uintptr_t)(uint32_t)c->gpr[9],(uint32_t)c->gpr[10],(void*)(uintptr_t)userdata);
    std::fprintf(stderr,"[port-save] ListAutoSave -> 0x%08X userdata=0x%08X\n",(uint32_t)result,userdata);
    c->gpr[3]=(uint64_t)(int64_t)result;
}
extern "C" void port_register_sail(void);
extern "C" void port_register_hle(void)
{
    port_register_sail();
    ps3_hle_register_ctx(0xE7FA820Bu,"cellSaveDataEnableOverlay",port_save_overlay_set);
    ps3_hle_register_ctx(0x4DD03A4Eu,"cellSaveDataListAutoSave",port_save_list_auto);
    ps3_hle_register_ctx(0xB0A1F8C6u,"cellGameContentErrorDialog",port_content_error_trace);
    ps3_hle_register_ctx(0xFF0A21B7u, "cellKbRead", port_kb_read);
    ps3_hle_register_ctx(0x7A0A83C4u, "cellFontInitLibraryFreeTypeWithRevision", port_font_init);
    ps3_hle_register_ctx(0x45FE2FCEu, "_sys_spu_printf_initialize", port_spu_printf_init);
    ps3_hle_register_ctx(0xDD3B27ACu, "_sys_spu_printf_finalize", port_spu_printf_finalize);
    ps3_hle_register_ctx(0xDD0C1E09u, "_sys_spu_printf_attach_group", port_spu_printf_callback<0>);
    ps3_hle_register_ctx(0x5FDFB2FEu, "_sys_spu_printf_detach_group", port_spu_printf_callback<1>);
    ps3_hle_register_ctx(0x1AE10B92u, "_sys_spu_printf_attach_thread", port_spu_printf_callback<2>);
    ps3_hle_register_ctx(0xB3BBCF2Au, "_sys_spu_printf_detach_thread", port_spu_printf_callback<3>);
    ps3_hle_register_ctx(0x0A4C8295u, "cellSearchStartListSearch", port_search_list);
    ps3_hle_register_ctx(0x774033D6u, "cellSearchEnd", port_search_end);
    ps3_hle_register_ctx(0xBE50B11Eu, "cellMusicInitialize2", port_music_init);
    ps3_hle_register_ctx(0xC81CCF8Au, "cellSearchInitialize", port_search_init);
    ps3_hle_register_ctx(0xBFAB7616u, "cellSearchFinalize", port_search_finalize);
    std::fprintf(stderr, "[port] keyboard/font/SPU printf/search lifecycle adapters installed\n");
}

/* This runtime can emit >18 MiB for the opening mission's frame. The title's
 * two 4 MiB command arenas otherwise run into its CPU render metadata. Give
 * empty contexts separate mapped storage; this is a capacity workaround, not
 * a fix for the excessive draw/state traffic. The launcher enables it. */
extern "C" int64_t sys_memory_allocate(ppu_context*);
extern "C" int64_t sys_memory_free(ppu_context*);
extern "C" int32_t cellGcmMapMainMemory(uint32_t,uint32_t,uint32_t*);
extern "C" void port_expand_graphics_buffers(ppu_context* original, uint32_t renderer)
{
    const char* enabled=std::getenv("PORT_GCM_EXPAND_BUFFERS");
    if (!enabled || !*enabled || *enabled=='0') return;
    const uint32_t a=vm_read32(renderer+0x100), b=vm_read32(renderer+0x104);
    if (!a || !b || vm_read32(a+8)!=vm_read32(a) || vm_read32(b+8)!=vm_read32(b) ||
        vm_read32(a+4)-vm_read32(a)!=0x3fffc0u ||
        vm_read32(b+4)-vm_read32(b)!=0x3fffc0u) return;
    const uint32_t size=0x2000000u, out=(uint32_t)original->gpr[1]+0x30;
    const uint32_t saved=vm_read32(out);
    ppu_context call=*original;call.gpr[3]=2*size;call.gpr[4]=0x400;call.gpr[5]=out;
    if (sys_memory_allocate(&call)!=0) {
        std::fprintf(stderr,"[port-buffers] cannot allocate 64 MiB for RSX commands; contexts unchanged\n");
        vm_write32(out,saved);return;
    }
    const uint32_t base=vm_read32(out);
    if (cellGcmMapMainMemory(base,2*size,(uint32_t*)(uintptr_t)out)!=0) {
        std::fprintf(stderr,"[port-buffers] cannot map RSX commands; allocation released\n");
        call.gpr[3]=base;sys_memory_free(&call);vm_write32(out,saved);return;
    }
    const uint32_t io=vm_read32(out);vm_write32(out,saved);
    for (unsigned i=0;i<2;i++) {
        uint32_t c=i?b:a, begin=base+i*size;
        uint32_t old=vm_read32(c);
        /* The initial FIFO jump was emitted before the contexts existed.
         * Preserve that entry point as a forwarding jump to the new stream. */
        vm_write32(old,0x20000000u | (io+i*size));
        vm_write32(c,begin);vm_write32(c+4,begin+size-64);vm_write32(c+8,begin);
    }
    std::fprintf(stderr,"[port-buffers] contexts %08X/%08X relocated to %08X, 32 MiB each, IO %08X\n",a,b,base,io);
}
