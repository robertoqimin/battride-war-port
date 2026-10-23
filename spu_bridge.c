/* BLJS10220 exact-image registrations. Static rejection is in spu/inventory.json. */
#include "spu_workload.h"
#include "spu_interp.h"
#include <stdio.h>
/* The stripped executable segment includes words the static translator
 * rejects. Interpret live instructions rather than silently skipping them. */
extern void spu_spurs_taskset_syscall(spu_context*);
static void battride_audio_task(spu_context* ctx)
{
    uint32_t pc=0x3050u;
    for (;;) {
        spu_interp_run_until(ctx, pc, SPURS_TASKSET_PM_SYSCALL_LS);
        if (ctx->pc != SPURS_TASKSET_PM_SYSCALL_LS) return;
        /* The async task adapter planted this synthetic task-API sentinel.
         * Service it using the same HLE as lifted SPURS tasks. */
        spu_spurs_taskset_syscall(ctx);
        pc=ctx->gpr[0]._u32[0] & SPU_LS_MASK;
    }
}
void port_register_spu(void)
{
    spu_workload_register_img(0xC1759183E2FF7448ULL, battride_audio_task,
                             506692475, "battride_audio_task.interpreted");
    spu_workload_register_img(0xDA70F59822356AD0ULL, battride_audio_task,
                             506692475, "battride_audio_task.text.interpreted");
    fprintf(stderr, "[port] SPU audio image registered with interpreter fallback\n");
}
