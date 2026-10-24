# Performance measurement and tuning

Use the same SDK, CPU, save copy, mission, camera, input sequence, window size,
and capture settings for comparisons. Run one game process at a time. Compare
several alternating runs: the number and behavior of enemies are not deterministic.
Do not compare menus or video playback with combat.

## Frame intervals and CPU samples

```bash
PORT_FRAME_TIMES=/tmp/combat.csv PORT_PROFILE=/tmp/combat.samples ./run-vulkan.sh
python3 scripts/frame_report.py /tmp/combat.csv --start 180 --end 240
```

The CSV records monotonic **guest frame completion intervals**, after the frame
is handed to Vulkan. It does not measure scanout, GPU execution time, or input
latency. It is buffered and flushed every 60 frames; an abrupt stop can lose the
last partial buffer. Select only the combat window, excluding loads and menus.
The report gives average FPS, median/p95/p99 and maximum interval, and the count
of frames over the 30 FPS budget. Captures and CPU sampling add overhead; use
identical settings on both sides, then check a run without them.

`PORT_PROFILE_HZ` controls the existing CPU sampler (default 1000). Symbolize its
thread/address samples against `nm -n` output from the exact executable tested.
Samples in shared libraries need their loaded address mappings; do not attribute
them to the last executable symbol. CPU samples locate candidates; they do not
by themselves prove that an optimization improves frame pacing.

## Vulkan changes

- Identical VS/PS constant blocks retain their batch UBO slice.
- Pipeline binds are skipped when the pipeline is already bound. Command buffer
  resets invalidate this cache; video and fallback draws use the same binder.
- Identical resolved image views, samplers, UBO slices, and layout reuse the last
  immutable descriptor set within the same batch generation. Pool resets prevent
  stale reuse. Texture uploads do not change a view's identity.
- Adjacent draws with the same framebuffer/render pass can share a pass. Generic
  operations and submission close it before copies, uploads, clears, or snapshots.
  `PORT_VK_MERGE_PASSES=0` restores separate passes for comparison.

Texture content detection remains unchanged: no additional skipped hashes or
approximate dirty tracking were introduced. Such changes need evidence that
hashing is expensive and a reliable way to observe all guest writes.

## Profiled CPU paths

The initial 60-second crowded STG02 run measured about 24.4 FPS. Its CPU
samples put roughly 43% of process CPU in the busy PPU thread, 25% in the FIFO
thread, and 23% in the audio SPU thread. These are sampling shares, not frame
budgets. PPU memory helpers and `func_004B5120` were prominent; vertex decoding
was 16.5% of the FIFO thread's samples. Texture hashes together were about 2.7%
of that thread, so their detection policy was preserved.

`PORT_HOT_PPU_O3` selects O3 only for generated PPU chunk 029, which contains
that tree traversal function. Disable it for comparison with
`cmake --preset linux-vulkan -DPORT_HOT_PPU_O3=OFF`, then rebuild. Other PPU
chunks keep the existing preset optimization. No fast-math is enabled.

`rsx_vertex_bridge.c` has exact four-component SSE4.1 paths for float, UNORM8,
and UINT8 attributes; other formats and component counts retain SDK behavior.
`bash tests/test_vertex_decode.sh` compares 5.4 million decodes with the SDK.

## Guarded PPU memory paths

The manual crowd profile collected 16,806 samples over 30 seconds. On the busy
PPU thread (96.4% of one logical CPU in a five-second observation), read32,
write64, and write32 helpers represented 9.2%, 8.6%, and 8.0% of that thread's
samples. The tree traversal function accounted for 5.7%; its earlier 26.9%
figure came from a much shorter, different interval and is not representative
of every combat scene. Percentages are self samples, not inclusive call costs.

`include/port_ppu_memory.h` is force-included only in profiled generated chunks
015, 017, 021, 029 and 030. It does not modify generated files or the SDK:

- Existing inline reads are forced inline, keeping their original predicates
  and fallback for diagnostics, low addresses, raw SPU windows, reference-word
  polling and memory bounds.
- Aligned ordinary 1/2/4/8-byte writes use big-endian relaxed atomic stores when
  no store diagnostic or SPU reservation applies. Aligned accesses cannot cross
  a 128-byte reservation line.
- Reserved lines always delegate to the original accessor, retaining its lock,
  notification and wakeup behavior. Unaligned, low/null, raw SPU/MMIO, out-of-range
  and diagnostic accesses also delegate. Dynamic barrier watches and null-sweep
  diagnostics are checked on every fast-path candidate.

Use `PORT_PPU_MEMORY_SLOW=1 ./run-vulkan.sh` to disable the new inline **stores**
at startup. To restore both the original read and write compilation paths,
configure `-DPORT_PPU_FAST_MEMORY=OFF` and rebuild. The cache variable
`PORT_PPU_FAST_MEMORY_CHUNKS` controls the selected generated chunks. Windows
retains the existing accessors. These changes require a new manual performance
comparison; unit tests do not establish an FPS gain. Inlining moves CPU samples
from helper symbols into their guest callers, so a lower helper percentage
alone is not evidence of reduced CPU time.

```bash
bash tests/test_ppu_memory.sh
CXX=clang++ SANITIZE=1 bash tests/test_ppu_memory.sh
```

The regression checks 300,000 mixed-width memory round trips, byte equivalence,
unaligned and truncated addresses, bounds and diagnostic fallbacks, and the
actual SDK's reservation invalidation/wakeup implementation. ASan/UBSan are
available through Clang on the development system; its GCC ASan runtime is
currently unavailable. The fixture verifies routing to the existing slow
accessors; it does not emulate every MMIO device or every diagnostic.

## Optional GCC PGO

PGO is disabled by default. It applies to GCC C++ (translated PPU and harness),
not the clang C runtime. Use the same build directory and unchanged source/object
paths for training and use:

```bash
cmake --preset linux-vulkan -DPORT_PGO=generate
cmake --build --preset linux-vulkan
# Train on representative gameplay, then exit normally to write GCC .gcda files.
cmake --preset linux-vulkan -DPORT_PGO=use
cmake --build --preset linux-vulkan
# Repeat the same benchmark and compare with the ordinary build.
```

Do not use a forced kill as a training shutdown: GCC normally writes profiles on
normal process exit. This port does not yet have a validated clean exit on every
path, so PGO is experimental and is not enabled in the validated default build.
Configuration rejects use mode if no .gcda files exist. Investigate missing-profile
or mismatched-profile compiler diagnostics before claiming a trained build.
`PORT_PGO_DIR` chooses the private profile directory (default: build directory/pgo).
Restore the normal build with `-DPORT_PGO=off`. Native CPU builds may not run on
older CPUs; choose `PORT_MARCH` for the intended target when distributing binaries.
