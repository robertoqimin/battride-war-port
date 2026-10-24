# Battride War Port

An **experimental** port of Kamen Rider: Battride War (Japan), **BLJS10220**, using PS3Recomp 0.11.0 and Vulkan on Linux. This project is not affiliated with the game's rights holders.

This repository contains port code, configuration, tests, and instructions. **It does not include the game, ISO, EBOOT, firmware, keys, saves, a compiled game executable, or complete generated PPU/SPU sources.** Each user must prepare their own local data and generate the sources before building.

## Validated status as of October 22, 2026

- PAMF opening playback with `cellSail` callbacks; playback completion and reaching the title screen were validated in earlier stages.
- `cellFsReadWithOffset`, game data installation, and save adapters are implemented. In the tested environment, 21,107 installed files were compared with the disc files using SHA-256, with no differences.
- Vertex textures are implemented in the local Vulkan backend, allowing the character animation to render.
- The start of mission **STG02** was reached: scenery, character, enemies, HUD, movement, pause/resume, and attacks were observed. The counter reached **5 Combo**. A session lasting approximately 557 seconds was stopped intentionally; the original save remained unchanged.
- The opening mission used to produce about 19 MiB of commands per flip, overflowing the title's 4 MiB command buffers. The cause was the SDK's `sys_lwcond`, a 1 ms poll whose signals do nothing: the game's render thread waits once on a frame event and fell through, redrawing the whole frame dozens of times per flip (708 renders against 9 flips in a 15 s sample). The port now overrides `sys_lwcond` with real blocking (`stubs.cpp`). A mission frame then peaks near 0.5 MiB, and the mission ran with the original 4 MiB buffers. The earlier 2×32 MiB workaround is off by default and remains available with `PORT_GCM_EXPAND_BUFFERS=1`; `PORT_LWCOND_SDK=1` restores the SDK behaviour. `PORT_GCM_FRAME_STATS=<flips>` prints per-flip command volume, draw signatures and buffer usage.

- Performance in mission combat went from about 6 to about 30 frames per second, the game's original rate (GTX 1650, three 30-40 s measurements: 29.7, 30.3, 30.7): the preset now builds with `-O2` instead of `-O0`; the Vulkan backend records draws, clears and uploads into batched command buffers (two slots, so the GPU renders one frame while the next is recorded) instead of submitting and waiting per draw (`PS3RECOMP_VK_SYNC=1` restores that); guest stores skip the debug watch checks when none is armed; the frame clock wakes on guest fence waits and presents without waiting for the GPU. The window now presents in MAILBOX mode when the driver offers it: in FIFO (vsync) mode each present blocked the FIFO walker until a vblank, so frames slightly over 33 ms waited until 50 ms and play with walking and crowds ran at 20-24 fps. Over 150 s of mixed fighting and walking the rate is now 38 on average, 29.4 at the 10th percentile, and the in-game clock keeps real time (62 s in 62 s). `PS3RECOMP_VK_VSYNC=1` keeps FIFO. The intro still reaches the title both when skipped with START and when it plays to the end.

- Audio no longer breaks up. The game's audio SPU task ran interpreted and filled only about a third of the cellAudio blocks in time (4 blocks of sound, 8 of silence, repeating). `scripts/lift_audio_spu.py` now translates the task's code below its data tail and, when the firmware is present, the `flashMP3.pic` codec it loads (README_FIRMWARE.md); `spu_bridge.c` runs that code and interprets the rest. Measured on the title music and 45 s of mission combat: no empty blocks while sound plays (`PORT_AUDIO_STATS=1` reports this), still at about 30 fps. The interpreter got a decode cache, and the SDK channel layer's per-access `getenv` was cached. Prolonged sessions and other stages have not been checked.

**The experience is still not smooth:** there is intermittent excessive brightness and incorrect effects/colors. Defeating enemies, completing missions, the full game, and prolonged stability have not been validated.

The long gameplay session used a six-second PAMF replacement solely to speed up the introduction. Original assets were not modified; the normal launcher still uses the original video. The entire sequence with that video was not repeated during the latest gameplay validation.

## System requirements (AppImage)

The AppImage contains no game code or data. On first launch it imports your disc, translates your EBOOT and compiles the game on your computer with its bundled toolchain (see [docs/APPIMAGE.md](docs/APPIMAGE.md)). Only one system has been tested: Fedora on a laptop with a Ryzen 5 4600H and GTX 1650 (Radeon integrated graphics alongside; the backend picks the discrete GPU). Everything below meets the checks in `packaging/launcher.py`, `packaging/graphics_probe.c` and the Vulkan backend, but has not been run.

**First launch:** about 8 GB of RAM (the build runs one compiler job per 2 GB available, at least one), about 8 GB of free space in the data folder (game files, plus about 4 GB while building) and time: the compile took 13 minutes with 4 jobs on the 4600H; expect 15-60 minutes depending on the CPU. It happens once; the built game is reused until the AppImage version or the CPU changes.

**CPU:** x86_64 with SSSE3 and SSE4.1. The game is compiled with `-march=native`, so each CPU gets code for its own instruction set (AVX2 where available).

| Supported | Not supported |
|---|---|
| Intel Core 2 45 nm (Penryn/Wolfdale/Yorkfield) and newer | Intel Core 2 65 nm (Conroe/Merom): no SSE4.1 |
| Every Intel Core i3/i5/i7/i9 and Core Ultra generation, Xeon from Nehalem | Intel Atom Bonnell/Saltwell (Silvermont and newer are fine) |
| Intel Pentium/Celeron from Silvermont/Goldmont, N100/N200 | AMD Athlon 64, Phenom, Phenom II (K8/K10): SSE4a only |
| AMD FX (Bulldozer/Piledriver), A-series APUs, Jaguar | ARM and RISC-V |
| Every AMD Ryzen, Threadripper and EPYC generation | |

The 30 fps figures above were measured on that Ryzen 5 4600H with a native Zen 2 build whose render thread was already close to saturation. CPUs with lower single-thread performance than a 4600H will likely run under 30 fps in combat; old CPUs without AVX2 will be noticeably slower.

**GPU:** Vulkan 1.0 with a graphics queue that can present to the window, `VK_KHR_swapchain` and `textureCompressionBC` (PS3 DXT textures). The launcher's graphics check rejects devices without BC textures.

| Vendor | Supported | Driver |
|---|---|---|
| NVIDIA | GeForce 600 (Kepler) and newer: GTX 700/900/10/16, RTX 20/30/40/50 | Proprietary (470 legacy for Kepler); NVK (Mesa 24.1+) for Turing and newer |
| AMD | Radeon HD 7000 (GCN 1) and newer: R7/R9, RX 400/500, Vega, RX 5000-9000, Ryzen APUs, Steam Deck | Mesa RADV (`amdgpu` kernel driver for GCN 1/2) |
| Intel | Ivy Bridge/Haswell graphics and newer (HD 4000+, UHD, Iris Xe), Arc A/B | Mesa ANV (`hasvk` for Gen7/Gen8) |

Not supported: GPUs without Vulkan (NVIDIA Fermi and older, AMD TeraScale / HD 6000 and older, Intel Sandy Bridge and older). Software Vulkan (lavapipe) passes the check but is far too slow. A GTX 1650 reaches about 30 fps; older integrated and entry-level GPUs will likely be slower.

**Distribution:** glibc 2.35 or newer, with the host Vulkan loader (`libvulkan.so.1`) and GPU driver installed. The AppImage does not bundle libc, the Vulkan/GL loaders, Mesa or the X11/Wayland libraries. FUSE 3 (`fusermount3`) is needed, or run with `--appimage-extract-and-run`.

| Supported | Not supported |
|---|---|
| Ubuntu 22.04 / 24.04 and newer; Kubuntu, Xubuntu, Linux Mint 21+, Pop!_OS 22.04+, Zorin OS 17+, elementary OS 7+ | Ubuntu 20.04 and older, Linux Mint 20 |
| Debian 12 (Bookworm), 13 (Trixie) | Debian 11 and older |
| Fedora 36+; Nobara, Bazzite | RHEL / AlmaLinux / Rocky 9 (glibc 2.34) and older |
| RHEL / AlmaLinux / Rocky 10 | openSUSE Leap 15.x |
| openSUSE Tumbleweed, Leap 16 | musl distributions (Alpine, Void musl) |
| Arch, Manjaro, EndeavourOS, CachyOS, Garuda | NixOS without `steam-run` / `appimage-run` |
| Recent SteamOS 3 (Steam Deck): likely, unverified | |

On hosts whose libstdc++ is older than RPCS3 needs (below `GLIBCXX_3.4.32`, e.g. Ubuntu 22.04 and Debian 12) the importer runs the RPCS3 helper with RPCS3's own `checkrt` libstdc++/libgcc_s. No compiler or development package is needed on the host: the bundled Ubuntu 22.04 toolchain builds against its own sysroot.

## Performance tuning

The local tuning work adds exact SIMD vertex decoding, reuse of Vulkan constant
buffers and descriptors, cached pipeline binds, and grouping of adjacent draws
with the same attachments. A profiled PPU translation unit can be built with
O3 without changing the whole program's optimization level. See
[docs/PERFORMANCE.md](docs/PERFORMANCE.md) for measurements, frame interval
reports, comparison switches, and experimental GCC PGO support.

## Setup and build

Follow [docs/BUILD.md](docs/BUILD.md) for Fedora dependencies, the pinned SDK revision, data layout, EBOOT hash, PPU/SPU generation, and patch application.

After preparing the SDK and local data in a fresh checkout:

```bash
../ps3recomp/.venv/bin/python scripts/generate.py --jobs 4
cmake --preset linux-vulkan \
  -DPython3_EXECUTABLE="$PWD/../ps3recomp/.venv/bin/python"
cmake --build --preset linux-vulkan
./run-vulkan.sh
```

Generation refuses to overwrite existing results. Expect about 593 MiB of PPU sources and additional space for building. The build uses clang for C and GCC for C++.

## Port components

- `spu_bridge.c`: runs the audio task rejected by the static translator, translated where `scripts/lift_audio_spu.py` could and interpreted elsewhere (`PORT_AUDIO_INTERPRET=1` interprets all of it); another SPU image is generated and registered statically.
- `spu_interp_bridge.c`, `spu_channels_bridge.c`: the SDK's SPU interpreter with a decode cache, and its channel layer with cached environment lookups.
- `sail_bridge.cpp`, `sail_decoder.hpp`, `sail_audio.hpp`: PAMF callbacks, video, and audio. See [README_SAIL.md](README_SAIL.md).
- `audio_bridge.c`, `fs_bridge.cpp`: local extensions to SDK audio and VFS.
- `gcm_bridge.c`, `rsx_engine_bridge.c`, `vulkan_bridge.c`, `loader_bridge.cpp`: local adaptations of SDK implementations; the official checkout remains separate.
- `include/port_ppu_memory.h`: guarded inline memory access in selected hot PPU chunks; reserved SPU lines and diagnostics retain the original accessors.
- `rsx_vertex_bridge.c`: exact SIMD paths for common four-component vertex formats.
- `stubs.cpp`: game HLE adapters, blocking `sys_lwcond`, and the optional graphics buffer expansion.
- `patches/graphics-command-buffer-init.patch`: minimal integration call to apply after PPU generation.

Local firmware codecs and their limitations are documented in [README_FIRMWARE.md](README_FIRMWARE.md).

## Publishing and license

The public file allowlist is `PUBLIC_FILES.txt`. To audit the contents and prepare a source ZIP:

```bash
python3 scripts/export_source.py
```

See [docs/PUBLISHING.md](docs/PUBLISHING.md) to package or publish with Git. Preparation does not upload anything automatically.

MIT licensed, preserving the PS3Recomp notice in [LICENSE](LICENSE). Adapted file origins and dependencies with other licenses are listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Releases carry only the AppImage of tools and public sources, which builds the game from the player's own disc; no compiled game is distributed.
