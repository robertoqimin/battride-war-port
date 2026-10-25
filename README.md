# Battride War Port

An **experimental** native Linux port of Kamen Rider: Battride War (Japan), **BLJS10220**, built with PS3Recomp 0.11.0 and Vulkan. This project is not affiliated with the game's rights holders.

This repository contains the port's code, configuration, tests and instructions. **It does not include the game, ISO, EBOOT, firmware, keys, saves, a compiled game executable, or generated PPU/SPU sources.** You need your own copy of the Japan disc.

**Download:** the [latest release](https://github.com/robertoqimin/battride-war-port/releases/latest) (v0.4.1) is an AppImage that imports your ISO, translates your own EBOOT and compiles the game on your computer. See [System requirements](#system-requirements-appimage).

## Current status (October 25, 2026)

**Playable through the opening mission.** The intro movie, title screen, menus, the opening cutscene and mission **STG02** work, and STG02 was completed by hand, returning to mission select. The rest of the game has not been played.

What works in the tested parts:

- **Graphics:** scenery, characters with animation, enemies, HUD, special-attack effects and character shadows. Shadows, lighting and effects in the opening cutscene and STG02 were compared with footage of the original game and match.
- **Audio:** music, voices and effects, with the game's audio SPU task and its MP3 codec translated to native code.
- **Saves and data:** game data installation and saves; 21,107 installed files matched the disc byte for byte.
- **Movies:** PAMF playback through `cellSail`.
- **Input:** keyboard and controllers through SDL2.

Known issues ([docs/ISSUES.md](docs/ISSUES.md) has the full list, in Portuguese):

- **Frame drops in the most crowded fights.** The game's main thread is the limit: it runs at 98% of a CPU core whenever the frame rate drops.
- **Audio** was measured without gaps in the title music and scripted combat, but a manual session still reported breakups during heavy fights, coinciding with frame drops.
- **One graphics glitch:** a large untextured polygon was seen for a single frame at the start of a special attack and could not be reproduced.
- **Not validated:** the full game, sessions longer than about 30 minutes, a clean exit on every path, and the ATRAC audio codec.

### Performance

Measured on a Ryzen 5 4600H with a GTX 1650, in 60-second windows of STG02 combat (four alternating runs per build):

| Build | Average | Frames over 33 ms | Worst 5 seconds |
|---|---|---|---|
| AppImage v0.4.x (bundled GCC 11, optimization profiles) | 47.9 fps | 3 | 42.9 fps |
| Same code without the profiles | 46.4 fps | 17 | 35.4 fps |
| Development build (GCC 16, optimization profiles) | 51.3 fps | 4 | 47.0 fps |

These are guest frames per second: the game runs its logic in real time and renders as fast as the host allows. Bigger crowds than in these scripted fights lower the rate; a manual session before v0.4.0 reported about 25 fps on this laptop in the heaviest fights, and the same session ran at about 40 fps on a Ryzen 7 5700X with an RX 6750 XT. Those manual figures have not been re-measured since.

What got it there, from about 6 fps at the start (details in [docs/PERFORMANCE.md](docs/PERFORMANCE.md)):

- `-O2` for the translated code, batched Vulkan command buffers, non-blocking presentation (MAILBOX when available) and a frame clock driven by the game's own fences.
- Real blocking for the game's lightweight condition variables (`sys_lwcond`): the SDK's polling version made the render thread redraw each frame dozens of times and overflow its 4 MiB command buffers.
- The audio SPU task and its codec translated instead of interpreted.
- Inline guest memory access in the hottest translated chunks, SIMD vertex decoding, and reuse of Vulkan constant buffers, descriptors and pipeline binds.
- Guest mutex locks no longer read the system clock twice per call, which cut frames over 33 ms by about two thirds.
- The translated code runs from transparent huge pages where the kernel allows them.
- GCC profile-guided optimization, trained on the opening mission and shipped with the AppImage.

## System requirements (AppImage)

The AppImage contains no game code or assets. It includes GCC optimization profiles: counts of how often each branch of the translated code ran while the developer played the opening mission, which make the build on your computer faster. They contain no game code, text, graphics or sound. On first launch it imports your disc, translates your EBOOT and compiles the game on your computer with its bundled toolchain (see [docs/APPIMAGE.md](docs/APPIMAGE.md)). Only one system has run the game end to end: Fedora on a laptop with a Ryzen 5 4600H and GTX 1650 (Radeon integrated graphics alongside; the backend picks the discrete GPU). The on-device build was also verified in an Arch Linux container, and the import helpers in Ubuntu 22.04. Everything below meets the checks in `packaging/launcher.py`, `packaging/graphics_probe.c` and the Vulkan backend, but has not been run.

**First launch:** an internet connection to download the official RPCS3 build (83 MB) that reads your disc, unless you already have that exact file; about 8 GB of RAM (the build runs one compiler job per 2 GB available, at least one), about 8 GB of free space in the data folder (game files, plus about 4 GB while building) and time: the compile took 12-14 minutes with 3-4 jobs on the 4600H; expect 15-60 minutes depending on the CPU. It happens once; the built game is reused until the AppImage version or the CPU changes.

**CPU:** x86_64 with SSSE3 and SSE4.1. The game is compiled with `-march=native`, so each CPU gets code for its own instruction set (AVX2 where available).

| Supported | Not supported |
|---|---|
| Intel Core 2 45 nm (Penryn/Wolfdale/Yorkfield) and newer | Intel Core 2 65 nm (Conroe/Merom): no SSE4.1 |
| Every Intel Core i3/i5/i7/i9 and Core Ultra generation, Xeon from Nehalem | Intel Atom Bonnell/Saltwell (Silvermont and newer are fine) |
| Intel Pentium/Celeron from Silvermont/Goldmont, N100/N200 | AMD Athlon 64, Phenom, Phenom II (K8/K10): SSE4a only |
| AMD FX (Bulldozer/Piledriver), A-series APUs, Jaguar | ARM and RISC-V |
| Every AMD Ryzen, Threadripper and EPYC generation | |

Single-thread speed decides the frame rate in combat, since one game thread is the limit. CPUs slower per core than a Ryzen 5 4600H will drop further in crowded fights; old CPUs without AVX2 will be noticeably slower.

**GPU:** Vulkan 1.0 with a graphics queue that can present to the window, `VK_KHR_swapchain` and `textureCompressionBC` (PS3 DXT textures). The launcher's graphics check rejects devices without BC textures.

| Vendor | Supported | Driver |
|---|---|---|
| NVIDIA | GeForce 600 (Kepler) and newer: GTX 700/900/10/16, RTX 20/30/40/50 | Proprietary (470 legacy for Kepler); NVK (Mesa 24.1+) for Turing and newer |
| AMD | Radeon HD 7000 (GCN 1) and newer: R7/R9, RX 400/500, Vega, RX 5000-9000, Ryzen APUs, Steam Deck | Mesa RADV (`amdgpu` kernel driver for GCN 1/2) |
| Intel | Ivy Bridge/Haswell graphics and newer (HD 4000+, UHD, Iris Xe), Arc A/B | Mesa ANV (`hasvk` for Gen7/Gen8) |

Not supported: GPUs without Vulkan (NVIDIA Fermi and older, AMD TeraScale / HD 6000 and older, Intel Sandy Bridge and older). Software Vulkan (lavapipe) passes the check but is far too slow. The GTX 1650 is not the limit at the frame rates above; older integrated and entry-level GPUs may be.

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

On hosts whose libstdc++ is older than RPCS3 needs (below `GLIBCXX_3.4.32`, e.g. Ubuntu 22.04 and Debian 12) RPCS3's own `AppRun` uses its bundled `checkrt` libstdc++/libgcc_s. No compiler or development package is needed on the host: the bundled Ubuntu 22.04 toolchain builds against its own sysroot.

**For more frames:** set the CPU governor to performance (`powerprofilesctl set performance`), run through `gamemoderun` if GameMode is installed, and keep laptops plugged in.

## Building from source

Follow [docs/BUILD.md](docs/BUILD.md) for Fedora dependencies, the pinned SDK revision, data layout, the EBOOT hash and PPU/SPU generation.

After preparing the SDK and local data in a fresh checkout:

```bash
../ps3recomp/.venv/bin/python scripts/generate.py --jobs 4
cmake --preset linux-vulkan \
  -DPython3_EXECUTABLE="$PWD/../ps3recomp/.venv/bin/python"
cmake --build --preset linux-vulkan -j2
./run-vulkan.sh
```

Generation refuses to overwrite existing results. Expect about 593 MiB of PPU sources and more for building. Each generated chunk takes about 1.5 GB of RAM to compile, so limit parallel jobs to the memory you have (`-j2` on 16 GB with a desktop running). The build uses clang for C and GCC for C++. The AppImage itself is built in an Ubuntu 22.04 container ([docs/APPIMAGE.md](docs/APPIMAGE.md)), including the optional optimization profiles (`scripts/pgo_train.py`).

## Port components

- `stubs.cpp`: game HLE adapters, blocking `sys_lwcond`, the optional graphics buffer expansion, and the CPU sampler (`PORT_PROFILE`).
- `main.cpp`: the runner, including the huge-page remapping of the translated code (`PORT_HUGEPAGES=0` disables it) and the PGO training hooks.
- `sync_bridge.c`: the SDK's Win32 compatibility layer with clock-free zero-timeout waits, used by every guest mutex lock.
- `gcm_bridge.c`, `rsx_engine_bridge.c`, `vulkan_bridge.c`, `loader_bridge.cpp`: local adaptations of SDK implementations (the official checkout remains separate), including the RSX depth-comparison direction and texture border colours that the shadows need (`PORT_SHADOW_REVERSE=0` restores the SDK behaviour).
- `rsx_vertex_bridge.c`: exact SIMD paths for common four-component vertex formats.
- `include/port_ppu_memory.h`: guarded inline memory access in selected hot PPU chunks; reserved SPU lines and diagnostics retain the original accessors.
- `spu_bridge.c`: runs the audio task rejected by the static translator, translated where `scripts/lift_audio_spu.py` could and interpreted elsewhere (`PORT_AUDIO_INTERPRET=1` interprets all of it); another SPU image is generated and registered statically.
- `spu_interp_bridge.c`, `spu_channels_bridge.c`: the SDK's SPU interpreter with a decode cache, and its channel layer with cached environment lookups.
- `sail_bridge.cpp`, `sail_decoder.hpp`, `sail_audio.hpp`: PAMF callbacks, video, and audio. See [README_SAIL.md](README_SAIL.md).
- `audio_bridge.c`, `fs_bridge.cpp`: local extensions to SDK audio and VFS.
- `scripts/generate.py`: translates your EBOOT and inserts the one integration call `stubs.cpp` needs, located by its guest return address.
- `packaging/`: the AppImage launcher and importer.

Local firmware codecs and their limitations are documented in [README_FIRMWARE.md](README_FIRMWARE.md). Diagnostic switches and measurement tools are in [docs/PERFORMANCE.md](docs/PERFORMANCE.md).

## Publishing and license

The public file allowlist is `PUBLIC_FILES.txt`. To audit the contents and prepare a source ZIP:

```bash
python3 scripts/export_source.py
```

See [docs/PUBLISHING.md](docs/PUBLISHING.md) to package or publish with Git. Preparation does not upload anything automatically.

Credits for the people and projects behind this port are in [CREDITS.md](CREDITS.md).

MIT licensed, preserving the PS3Recomp notice in [LICENSE](LICENSE). Adapted file origins and dependencies with other licenses are listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Releases carry only the AppImage of tools and public sources, which builds the game from the player's own disc, and the corresponding source of every third-party binary in it; no compiled game is distributed.
