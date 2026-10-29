# Windows port plan

The port builds and runs on Linux only. This is what stands between it and
Windows, and the stages to get there. Changes to the SDK go upstream to
ps3recomp, since the build pins an SDK revision.

## What already helps

- The ps3recomp SDK targets Windows: `win32_compat`, WASAPI audio, XInput,
  the D3D12 backend, `app.rc`, and the `dbghelp`/`user32`/`gdi32`/`winmm`
  imports.
- `main.cpp` and `loader_bridge.cpp` already have `_WIN32` paths for the guest
  arena (`VirtualAlloc`) and the guest-pointer trap (vectored exception
  handler).
- `vulkan_bridge.c` creates its window and surface through SDL, so it does not
  depend on X11 or Wayland.
- The generator scripts are Python and mostly host-independent.

## Blockers

| # | Blocker | Where |
|---|---|---|
| 1 | `PS3RECOMP_RSX_VULKAN` is a `FATAL_ERROR` on Windows | `ps3recomp/CMakeLists.txt` |
| 2 | The SDK links SDL2 only off Windows; `input_bridge.c` and `vulkan_bridge.c` need it | `ps3recomp/CMakeLists.txt` |
| 3 | On Windows the SDK selects WASAPI and XInput; the port wraps the SDL2 backends (`pad_poll_sdl2`, `audio_bridge.c` pacing, which is added on Linux only) | `input_bridge.c`, `audio_bridge.c` |
| 4 | Vulkan loader loaded with `dlopen("libvulkan.so.1")` | `vulkan_bridge.c` |
| 5 | Thread pinning reads `/proc/self/task` and calls `sched_setaffinity` | `thread_affinity.c` |
| 6 | The SAIL video decoder runs FFmpeg through `posix_spawn`, `pipe2`, `poll`, `waitpid` | `sail_decoder.hpp` |
| 7 | The sampling profiler uses `SIGPROF` and `syscall(gettid)` | `stubs.cpp` |
| 8 | Lifted translation units exceed the default COFF section limit; MinGW needs `-Wa,-mbig-obj` (only MSVC's `/bigobj` is set) | `CMakeLists.txt` |
| 9 | `cl.exe` cannot build the code (`__int128`, `__atomic_*`); `spu_dispatch_mt.c` needs clang for `musttail`; PGO needs GCC | SDK and port |
| 10 | `store_wrap.c`, `PORT_PPU_FAST_MEMORY` and `PORT_PPU_NATIVE` are disabled on `WIN32` | `CMakeLists.txt` |
| 11 | Launcher and importer assume Linux: `/proc/cpuinfo`, GTK4, RPCS3 AppImage, `XDG_*`, `patchelf`, `start_new_session`, signals | `packaging/*.py` |
| 12 | PGO profiles are trained on Linux; the `#ifdef`s change the code, so Windows needs its own | `scripts/pgo_train.py` |

## Toolchain

MSYS2 UCRT64, with clang for C (`musttail`) and g++ for C++ (PGO), the same
split as the `linux-vulkan` preset. winpthreads supplies `pthread`,
`clock_gettime` and `nanosleep`, so most bridges compile unchanged, and
MinGW's linkers support `--wrap` and weak/alias symbols, which MSVC does not.

For quick iteration, cross-compile on Fedora (`mingw64-gcc`, `mingw64-SDL2`)
and run under Wine (Vulkan through winevulkan) before testing on real Windows.

## Stages

### 0. Setup

- Pick the Windows 10/11 test machine (ideally dual boot on the Ryzen 5 4600H
  with the GTX 1650, to compare against Linux numbers).
- Install MSYS2 UCRT64: gcc, clang, cmake, ninja, SDL2, vulkan-headers,
  glslang, python.
- Set up the Fedora MinGW cross build and Wine with Vulkan.
- Open `windows` branches in this repository and in ps3recomp.

### 1. Configure and link

- SDK: allow the Vulkan backend on Windows, link SDL2 on Windows, force
  `PS3RECOMP_AUDIO_USE_SDL2` and the SDL2 pad backend.
- Port: a `windows-vulkan` preset; `-Wa,-mbig-obj` on the lifted and SPU
  sources; `thread_affinity.c` and the `stubs.cpp` profiler Linux-only (stubs
  on Windows for now).
- `vulkan_bridge.c`: `LoadLibrary("vulkan-1.dll")` instead of `dlopen`.
- Add `audio_bridge.c` on Windows too, with `timeBeginPeriod(1)` or a
  high-resolution waitable timer for its 1 ms sleep.
- Link libstdc++ and winpthread statically, or ship their DLLs.
- Milestone: the `.exe` links.

### 2. First boot

- Check `alloc_guest_vm` and `vm_commit` over `VirtualAlloc`, and the guest
  trap through the vectored exception handler.
- Check VFS paths in `fs_bridge.cpp`: backslashes, drive letters, case
  insensitivity, `PS3_VFS_ROOT`.
- Rewrite `sail_decoder.hpp` over `CreateProcess`, anonymous pipes, a reader
  thread or `PeekNamedPipe`, and `TerminateProcess`.
- Milestone: reaches the title menu under Wine, then on native Windows.

### 3. Playable

- Tutorial, the STG02 fight, audio without dropouts (`PORT_AUDIO_STATS`),
  movies, saves, keyboard and mouse, controllers (gamecontrollerdb), FSR and
  display modes.
- Fix what differs from Linux.
- Milestone: the opening mission completes on Windows.

### 4. Performance

- Re-enable on Windows: `store_wrap.c` (`--wrap` in MinGW ld/lld),
  `port_ppu_memory.h` and `ppu_native.cpp` (weak/alias on COFF). Find out
  first why they are excluded on `WIN32`.
- Thread pinning with `SetThreadAffinityMask` / `SetThreadIdealProcessor`.
- Port `bench_combat.py`, retrain PGO on Windows, compare with Linux.

### 5. Launcher and importer

- A Windows entry in `rpcs3.json`: the official `.7z` build runs portable, so
  `dev_flash` and the decrypted EBOOT land in different places.
- Windows `7z.exe` and `ffmpeg.exe`.
- CPU check via `IsProcessorFeaturePresent` instead of `/proc/cpuinfo`.
- Data in `%LOCALAPPDATA%\battride-war-port`, settings in `%APPDATA%`.
- Process control with `CREATE_NEW_PROCESS_GROUP` instead of signals; drop
  the `patchelf` step.
- Port `graphics_probe.c`.
- UI: GTK4 from MSYS2 (keeps the code) or another toolkit — to decide.
- Bundle a minimal toolchain so the game is built on the player's computer;
  the runner is never shipped.

### 6. Packaging and licences

- Portable zip or installer (Inno Setup).
- Sources tarball for every bundled binary (MinGW runtime, winpthreads, SDL2,
  FFmpeg, 7-Zip); update `THIRD_PARTY_NOTICES.md` and `PUBLIC_FILES.txt`.
- User-facing Windows instructions, including SmartScreen (no code signing)
  and Defender, which slows the build and may flag the freshly built `.exe`.

### 7. Test matrix and beta

- Windows 10 and 11; NVIDIA, AMD and Intel GPUs; dual-GPU laptops
  (`PS3RECOMP_VK_DEVICE`); build time on the player's computer.
- GitHub Actions (windows-latest + MSYS2) for the SDK and its tests only: the
  lifted code comes from the game and is not public.
- Milestone: Windows beta release.

## Main risks

- The SAIL decoder rewrite (stage 2).
- Performance while the memory fast paths are off (stage 4).
- Size of the bundled toolchain and build time with Defender active (stage 5).
