#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <random>
extern "C" {
void ref_madd(void*, const void*, const void*, const void*, uint32_t);
void port_madd(void*, const void*, const void*, const void*, uint32_t);
void ref_nmsub(void*, const void*, const void*, const void*, uint32_t);
void port_nmsub(void*, const void*, const void*, const void*, uint32_t);
void ref_add(void*, const void*, const void*, uint32_t);
void port_add(void*, const void*, const void*, uint32_t);
void ref_sub(void*, const void*, const void*, uint32_t);
void port_sub(void*, const void*, const void*, uint32_t);
}
static int diff(const char* op, const uint8_t* a, const uint8_t* b, const uint8_t* c,
                const uint8_t* r1, const uint8_t* r2, uint32_t vscr) {
    if (!memcmp(r1, r2, 16)) return 0;
    for (int i = 0; i < 4; i++) { uint32_t x, y, z = 0, p, q; memcpy(&x, a+4*i, 4); memcpy(&y, b+4*i, 4);
        if (c) memcpy(&z, c+4*i, 4); memcpy(&p, r1+4*i, 4); memcpy(&q, r2+4*i, 4);
        if (p != q) std::printf("%s lane %d vscr=%x a=%08x b=%08x c=%08x ref=%08x port=%08x\n", op, i, vscr,
            __builtin_bswap32(x), __builtin_bswap32(y), __builtin_bswap32(z), __builtin_bswap32(p), __builtin_bswap32(q)); }
    return 1;
}
static const uint32_t edge[] = {0, 0x80000000u, 0x00000001u, 0x807FFFFFu, 0x00800000u, 0x3F800000u,
    0xBF800000u, 0x7F800000u, 0xFF800000u, 0x7FC00000u, 0x7F800001u, 0xFFFFFFFFu, 0x7F7FFFFFu, 0x40490FDBu};
int main() {
    std::mt19937 rng(1234);
    auto word = [&](void) -> uint32_t {
        switch (rng() % 4) { case 0: return edge[rng() % (sizeof edge / 4)];
                             case 1: return rng() & 0x80FFFFFFu;          /* tiny/denormal-ish */
                             default: return rng(); } };
    unsigned long checked = 0;
    for (int it = 0; it < 2000000; it++) {
        uint8_t a[16], b[16], c[16], r1[16], r2[16];
        for (int i = 0; i < 4; i++) { uint32_t x = word(), y = word(), z = word();
            memcpy(a + 4 * i, &x, 4); memcpy(b + 4 * i, &y, 4); memcpy(c + 4 * i, &z, 4); }
        const uint32_t vscr = (it & 1) ? 0x00010000u : 0u;
        ref_madd(r1, a, b, c, vscr); port_madd(r2, a, b, c, vscr); if (diff("madd", a, b, c, r1, r2, vscr)) return 1;
        ref_nmsub(r1, a, b, c, vscr); port_nmsub(r2, a, b, c, vscr); if (diff("nmsub", a, b, c, r1, r2, vscr)) return 1;
        ref_add(r1, a, b, vscr); port_add(r2, a, b, vscr); if (diff("add", a, b, nullptr, r1, r2, vscr)) return 1;
        ref_sub(r1, a, b, vscr); port_sub(r2, a, b, vscr); if (diff("sub", a, b, nullptr, r1, r2, vscr)) return 1;
        checked += 4;
    }
    std::printf("PASS: vmaddfp/vnmsubfp/vaddfp/vsubfp SIMD == scalar on %lu vectors (both NJ modes)\n", checked);
}
