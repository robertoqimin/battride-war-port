#include <cstdint>
#include <cstdio>
#include <cstring>
#include <random>
#include <sys/mman.h>
#include <unistd.h>
#include "rsx_dispatch.h"
#include "rsx_vertex_compact.h"
extern "C" int reference_decode(uint32_t, uint32_t, const uint8_t*, float*);
extern "C" int rsx_vertex_fetch_many(const rsx_vertex_fetch_plan*, const rsx_vertex_ref*, uint32_t, uint8_t*);
int main() {
    std::mt19937 random(195);
    uint8_t bytes[32];
    unsigned checked = 0;
    for (unsigned iteration = 0; iteration < 100000; ++iteration) {
        for (auto& b : bytes) b = static_cast<uint8_t>(random());
        for (uint32_t type = 0; type < 9; ++type)
            for (uint32_t size = 0; size <= 5; ++size) {
                float a[4] = {}, b[4] = {};
                const int x = reference_decode(type, size, bytes + 1, a);
                const int y = rsx_vertex_decode_element(type, size, bytes + 1, b);
                if (x != y || std::memcmp(a, b, sizeof a)) {
                    std::fprintf(stderr, "decode mismatch type=%u size=%u iteration=%u\n", type, size, iteration);
                    return 1;
                }
                ++checked;
            }
    }
    // Place packed attributes immediately before a protected page. A SIMD
    // implementation must not load 16 bytes from a four-byte u8 attribute.
    const size_t page = (size_t)sysconf(_SC_PAGESIZE);
    auto* memory = static_cast<uint8_t*>(mmap(nullptr, page * 2, PROT_READ | PROT_WRITE,
                                              MAP_PRIVATE | MAP_ANONYMOUS, -1, 0));
    if (memory == MAP_FAILED || mprotect(memory + page, page, PROT_NONE)) return 2;
    for (uint32_t type : {RSX_VTX_TYPE_FLOAT, RSX_VTX_TYPE_UNORM8, RSX_VTX_TYPE_UINT8}) {
        const size_t bytes = type == RSX_VTX_TYPE_FLOAT ? 16 : 4;
        uint8_t* source = memory + page - bytes;
        std::memset(source, 0xA5, bytes);
        float a[4], b[4];
        if (reference_decode(type, 4, source, a) != rsx_vertex_decode_element(type, 4, source, b)
                || std::memcmp(a, b, sizeof a)) return 1;
    }
    munmap(memory, page * 2);
    std::printf("PASS: %u vertex decodes match SDK bit for bit (unaligned sources)\n", checked);

    // The batch fetch decodes the common formats inline; every type and size
    // must come out as rsx_vertex_fetch_one (which calls the decoder) writes it.
    constexpr uint32_t kVerts = 64, kStride = 16;
    static uint8_t data[kVerts * kStride + 1];
    unsigned batched = 0;
    for (unsigned iteration = 0; iteration < 2000; ++iteration) {
        for (auto& b : data) b = static_cast<uint8_t>(random());
        for (uint32_t type = 1; type <= 7; ++type)
            for (uint32_t size = 1; size <= 4; ++size) {
                rsx_vertex_fetch_plan plan;
                std::memset(&plan, 0, sizeof plan);
                rsx_vertex_layout_plan_init(&plan.layout, 1u);
                rsx_vertex_fetch_attr& attr = plan.attr[0];
                attr.desc.type = type;
                attr.desc.size = size;
                attr.desc.stride = kStride;
                attr.elem_size = type == RSX_VTX_TYPE_CMP32 ? 4u
                    : type == RSX_VTX_TYPE_FLOAT ? 4u * size
                    : (type == RSX_VTX_TYPE_UNORM8 || type == RSX_VTX_TYPE_UINT8) ? size : 2u * size;
                attr.stride = kStride;
                attr.stable_base = data + 1;          // unaligned
                attr.stable_first = 0;
                attr.stable_last = kVerts - 1;
                rsx_vertex_ref refs[kVerts];
                for (uint32_t i = 0; i < kVerts; ++i) refs[i] = { static_cast<uint32_t>(random() % kVerts), 0 };
                float many[kVerts][4], one[4];
                if (!rsx_vertex_fetch_many(&plan, refs, kVerts, reinterpret_cast<uint8_t*>(many))) return 3;
                for (uint32_t i = 0; i < kVerts; ++i) {
                    if (!rsx_vertex_fetch_one(&plan, &refs[i], reinterpret_cast<uint8_t*>(one)) ||
                        std::memcmp(one, many[i], sizeof one)) {
                        std::fprintf(stderr, "batch mismatch type=%u size=%u vertex=%u\n", type, size, i);
                        return 1;
                    }
                    ++batched;
                }
            }
    }
    std::printf("PASS: %u batch-fetched vertices match one-at-a-time fetch\n", batched);
}
