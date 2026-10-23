# Credits and third-party components

## PS3Recomp

- Project: https://github.com/sp00nznet/ps3recomp
- Revision used: `a6d76c895f77eb30b90a806c830544e61821b77f` (0.11.0).
- Copyright (c) 2026 Ned Heller / sp00nznet.
- MIT license: full text preserved in `LICENSE`.

The project started from the PS3Recomp template. `CMakeLists.txt`, `config.toml`, the `main.cpp` scaffold, and parts of `stubs.cpp` derive from that template. The adapted local copies are:

| Port file | SDK origin |
| --- | --- |
| `loader_bridge.cpp` | `runtime/ppu/ppu_loader.cpp` |
| `gcm_bridge.c` | `libs/video/cellGcmSys.c` |
| `rsx_engine_bridge.c` | `libs/video/rsx_draw_engine.c` |
| `vulkan_bridge.c` | `libs/video/rsx_vulkan_backend.c` |
| `spu_interp_bridge.c` | `runtime/spu/spu_interp.c` |

`audio_bridge.c`, `fs_bridge.cpp` and `spu_channels_bridge.c` include SDK implementations at build time. The FIFO fixtures in `tests/test_gcm_jump.c` also derive from SDK tests. The official checkout remains separate, with its original licenses and notices.

## Dependencies obtained separately

The source package does not include SDL, Vulkan, glslang, SPIR-V Tools, FFmpeg, or their binaries. Each dependency retains its own terms and notices. This package's MIT license must not be interpreted as licensing those dependencies.

The SDK includes an ATRAC3/ATRAC3plus decoder in `third_party/at3_standalone`, derived from FFmpeg and obtained from PPSSPP, under LGPL-2.1-or-later. This ZIP does not contain that decoder, but the executable produced by the build incorporates it. Before distributing a binary, review that component's `README` and `COPYING.LGPLv2.1` files and the notices for other dependencies. This preparation covers source publication, without a binary release.

RPCS3 was used as a reference for firmware interfaces and, in the local development environment, to extract user-supplied firmware. The package does not include its executable or the extracted files.

## Game and firmware

Kamen Rider: Battride War and its assets are not part of this source package. There is no affiliation with or endorsement by the game's rights holders. Sony firmware, `.pic` codecs, keys, saves, the game ELF, and complete generated PPU/SPU sources are local data and are not covered by this repository's license.
