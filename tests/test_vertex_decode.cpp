#include <cstdint>
#include <cstdio>
#include <cstring>
#include <random>
#include <sys/mman.h>
#include <unistd.h>
#include "rsx_dispatch.h"
extern "C" int reference_decode(uint32_t, uint32_t, const uint8_t*, float*);
extern "C" int rsx_vertex_decode_element(uint32_t, uint32_t, const uint8_t*, float*);
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
}
