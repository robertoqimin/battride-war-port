# kamenriderbattridewarsport

An **experimental** port of Kamen Rider: Battride War (Japan), **BLJS10220**, using PS3Recomp 0.11.0 and Vulkan on Linux. This project is not affiliated with the game's rights holders.

This repository contains port code, configuration, tests, and instructions. **It does not include the game, ISO, EBOOT, firmware, keys, saves, a compiled executable, or complete generated PPU/SPU sources.** Each user must prepare their own local data and generate the sources before building.

## Validated status as of October 22, 2026

- PAMF opening playback with `cellSail` callbacks; playback completion and reaching the title screen were validated in earlier stages.
- `cellFsReadWithOffset`, game data installation, and save adapters are implemented. In the tested environment, 21,107 installed files were compared with the disc files using SHA-256, with no differences.
- Vertex textures are implemented in the local Vulkan backend, allowing the character animation to render.
- The start of mission **STG02** was reached: scenery, character, enemies, HUD, movement, pause/resume, and attacks were observed. The counter reached **5 Combo**. A session lasting approximately 557 seconds was stopped intentionally; the original save remained unchanged.
- The opening mission used to produce about 19 MiB of commands per flip, overflowing the title's 4 MiB command buffers. The cause was the SDK's `sys_lwcond`, a 1 ms poll whose signals do nothing: the game's render thread waits once on a frame event and fell through, redrawing the whole frame dozens of times per flip (708 renders against 9 flips in a 15 s sample). The port now overrides `sys_lwcond` with real blocking (`stubs.cpp`). A mission frame then peaks near 0.5 MiB, and the mission ran with the original 4 MiB buffers. The earlier 2×32 MiB workaround is off by default and remains available with `PORT_GCM_EXPAND_BUFFERS=1`; `PORT_LWCOND_SDK=1` restores the SDK behaviour. `PORT_GCM_FRAME_STATS=<flips>` prints per-flip command volume, draw signatures and buffer usage.

- Performance in mission combat went from about 6 to about 25 frames per second (GTX 1650): the preset now builds with `-O2` instead of `-O0`; the Vulkan backend records draws, clears and uploads into batched command buffers (two slots, so the GPU renders one frame while the next is recorded) instead of submitting and waiting per draw (`PS3RECOMP_VK_SYNC=1` restores that); guest stores skip the debug watch checks when none is armed; the frame clock wakes on guest fence waits and presents without waiting for the GPU. The last two changes have only been checked manually up to the menu. The original 30 fps has not been reached yet.

**The experience is still not smooth:** performance is still below the original frame rate, with intermittent excessive brightness and incorrect effects/colors. Defeating enemies, completing missions, the full game, and prolonged stability have not been validated. Audio still has interruptions.

The long gameplay session used a six-second PAMF replacement solely to speed up the introduction. Original assets were not modified; the normal launcher still uses the original video. The entire sequence with that video was not repeated during the latest gameplay validation.

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

- `spu_bridge.c`: interprets the audio task rejected by the static translator; another SPU image is generated and registered statically.
- `sail_bridge.cpp`, `sail_decoder.hpp`, `sail_audio.hpp`: PAMF callbacks, video, and audio. See [README_SAIL.md](README_SAIL.md).
- `audio_bridge.c`, `fs_bridge.cpp`: local extensions to SDK audio and VFS.
- `gcm_bridge.c`, `rsx_engine_bridge.c`, `vulkan_bridge.c`, `loader_bridge.cpp`: local adaptations of SDK implementations; the official checkout remains separate.
- `stubs.cpp`: game HLE adapters, blocking `sys_lwcond`, and the optional graphics buffer expansion.
- `patches/graphics-command-buffer-init.patch`: minimal integration call to apply after PPU generation.

Local firmware codecs and their limitations are documented in [README_FIRMWARE.md](README_FIRMWARE.md).

## Publishing and license

The public file allowlist is `PUBLIC_FILES.txt`. To audit the contents and prepare a source ZIP:

```bash
python3 scripts/export_source.py
```

See [docs/PUBLISHING.md](docs/PUBLISHING.md) to package or publish with Git. Preparation does not upload anything automatically.

MIT licensed, preserving the PS3Recomp notice in [LICENSE](LICENSE). Adapted file origins and dependencies with other licenses are listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). This package contains no binary release.
