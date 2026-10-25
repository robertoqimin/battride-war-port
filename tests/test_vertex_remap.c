/* rsx_vertex_remap_build (rsx_vertex_bridge.c, with its direct-table fast
 * path) against the SDK's hash-table version: same unique count, same
 * compacted reference order, same occurrence map, over compact, sparse,
 * mixed-base and repeated reference lists. */
#include "rsx_vertex_compact.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int reference_remap(rsx_vertex_remap*, rsx_vertex_ref*, u32, u32*);

static unsigned s_seed = 12345;
static u32 rnd(void) { s_seed = s_seed * 1103515245u + 12345u; return s_seed >> 8; }

int main(void)
{
    rsx_vertex_remap a, b;
    memset(&a, 0, sizeof a);
    memset(&b, 0, sizeof b);
    static rsx_vertex_ref ra[20000], rb[20000];
    unsigned cases = 0;
    for (int round = 0; round < 3000; round++) {
        const u32 n = 2 + rnd() % 6000;
        const u32 kind = round % 4;
        const u32 lo = rnd() % 100000;
        const u32 span = kind == 0 ? 1 + n / 3 : kind == 1 ? 1 + rnd() % 70000 : kind == 2 ? 1 + n : 3;
        for (u32 i = 0; i < n; i++) {
            ra[i].vertex_id = lo + rnd() % span;
            ra[i].base_index = (kind == 2 && (rnd() & 7) == 0) ? 7 : 0;   /* mixed bases fall back */
        }
        memcpy(rb, ra, n * sizeof *ra);
        u32 ua = 0, ub = 0;
        if (!rsx_vertex_remap_build(&a, ra, n, &ua) || !reference_remap(&b, rb, n, &ub)) {
            fprintf(stderr, "remap failed in round %d\n", round);
            return 1;
        }
        if (ua != ub || memcmp(ra, rb, ua * sizeof *ra) ||
            memcmp(a.occurrence_to_unique, b.occurrence_to_unique, n * sizeof(u32))) {
            fprintf(stderr, "mismatch in round %d (n=%u kind=%u): unique %u vs %u\n", round, n, kind, ua, ub);
            return 1;
        }
        cases++;
    }
    printf("test_vertex_remap: %u cases ok\n", cases);
    return 0;
}
