# Credits

Battride War Port exists thanks to the people and projects below. Licenses and redistribution details are in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## The game

**Kamen Rider: Battride War** (Japan, BLJS10220), developed by Eighting and published in 2013 by Namco Bandai Games (now Bandai Namco Entertainment). Kamen Rider belongs to Ishimori Productions and Toei. This project is not affiliated with or endorsed by any of them, and contains none of their code or data: players use their own disc.

## Port

- **robertoqimin**: the port, its bridges, fixes, performance work, launcher and packaging.
- Development assisted by **Claude Code** (Anthropic).

## Recompilation toolkit

- **PS3Recomp** by **Ned Heller (sp00nznet)** and contributors: the static recompiler, runtime and HLE libraries this port is built on. MIT. https://github.com/sp00nznet/ps3recomp
- The **FFmpeg** developers, for the ATRAC3/ATRAC3plus decoder, as extracted by the **PPSSPP** project (Henrik Rydgård and contributors) and vendored in PS3Recomp. LGPL-2.1-or-later.

## Used while importing your disc

- **RPCS3** team and contributors: decrypts your EBOOT and installs the firmware update from your disc to extract the audio codecs. The official build is downloaded from the RPCS3 project's own release page; it is not redistributed here. GPL-2.0. https://rpcs3.net
- **7-Zip** by **Igor Pavlov**: reads the ISO. LGPL-2.1 with the unRAR restriction. https://www.7-zip.org

## Runtime libraries and tools in the AppImage

- **SDL2** (Sam Lantinga and contributors): window, input and audio. zlib.
- **Khronos Group**: Vulkan headers, glslang and SPIRV-Tools, used to translate the game's shaders. Apache-2.0 / BSD.
- **FFmpeg** developers: video playback. LGPL/GPL.
- **GTK**, **GLib**, **PyGObject**, **pycairo** and **Python** (Python Software Foundation): the launcher.
- **GCC** and **GNU binutils** (Free Software Foundation), **Clang/LLVM** (LLVM project), **CMake** (Kitware), **Ninja**, **GNU patch**, **glibc**: the toolchain that builds the game on your computer.
- **Ubuntu** and **Debian** maintainers: every one of these components is packaged by them; the AppImage takes them from Ubuntu 22.04.
- **AppImage** project: the type2 runtime (probonopd and contributors), with **libfuse** and **squashfuse** (Dave Vasilevsky and contributors).

## Hardware drivers

Rendering uses the Vulkan driver installed on your system: **Mesa** (RADV, ANV, NVK) or the vendor's driver.

Thank you all.
