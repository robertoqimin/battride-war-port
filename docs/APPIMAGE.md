# Linux AppImage

The AppImage contains **no game code or data**. It carries the port's public sources (exactly the files in `PUBLIC_FILES.txt`), the pinned ps3recomp SDK, 7-Zip, FFmpeg and a compiler toolchain. On first launch it downloads the official RPCS3 build to decrypt your EBOOT, imports your disc, translates your own EBOOT into C and compiles the game for your CPU. Corresponding source for every bundled binary is published next to the AppImage on each release page (`BattrideWarPort-v<version>-sources.tar`; see [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)). It runs on distributions with glibc 2.35 or newer; see "System requirements" in the [README](../README.md) for CPUs, GPUs, RAM and disk. It has been run end to end on Fedora (Ryzen 5 4600H, GTX 1650); the RPCS3, 7-Zip and FFmpeg helpers were also started inside Ubuntu 22.04. Other distributions and GPUs require testing. It does not fix the remaining combat performance drops.

## Run

Make the AppImage executable and open it:

```sh
chmod +x BattrideWarPort-v0.3.2-x86_64.AppImage
./BattrideWarPort-v0.3.2-x86_64.AppImage
```

If FUSE is unavailable, run `./BattrideWarPort-v0.3.2-x86_64.AppImage --appimage-extract-and-run`.

Select the Japan BLJS10220 ISO and click **Import ISO & Play**. The first launch:

1. checks the disc listing, then downloads the official RPCS3 build pinned in `packaging/rpcs3.json` (83 MB, from the RPCS3 project's GitHub release; SHA-256 verified). If `~/Downloads` already holds that exact file, or you pass `--rpcs3 /path/to/rpcs3-v0.0.43-20370-0b0fa082_linux64.AppImage`, no download happens. It then extracts and verifies the game files (size and SHA-256), decrypts the EBOOT with RPCS3 and extracts the audio codecs from the firmware update on the disc, and deletes RPCS3 again (`import.log`);
2. translates the EBOOT into PPU/SPU sources with the SDK tools (`build.log`);
3. compiles the game with `-march=native` for this CPU, one job per 2 GB of available memory (`build.log`). This took 13 minutes with 4 jobs on a Ryzen 5 4600H; expect 15-60 minutes;
4. checks that a Vulkan GPU can create a window surface, a swapchain and BC textures (`graphics.log`), then starts the game (`game.log`).

The generated sources and object files are deleted after the build; only `runner/game-runner` stays in the data folder. Later launches reuse it until the AppImage version or the CPU changes. No separate firmware download, compiler, development package or administrator access is required; only the RPCS3 download needs an internet connection.

Default data: `~/.local/share/battride-war-port/`. Saves are inside this folder; copy the whole folder to transfer an installation (the game is rebuilt if the other computer has a different CPU). The ISO path is remembered in `~/.config/battride-war-port/settings.json`. If moving an imported installation changes the ISO path, select a new empty data folder and import again; existing imports are preserved. Logs are in `logs/` under the data folder. MangoHud is optional and must be installed on the destination PC if selected.

On laptops with two GPUs the game picks the discrete one. If it picks the wrong device, the `device N:` lines in `game.log` list them and `PS3RECOMP_VK_DEVICE=N` forces one.

Headless checks:

```sh
./BattrideWarPort-v0.3.2-x86_64.AppImage --check    # helpers and build tools start
./BattrideWarPort-v0.3.2-x86_64.AppImage --import-only /path/game.iso --data-dir /new/empty/data   # import and build
```

## Build the AppImage

Everything is built inside the Ubuntu 22.04 image; `build_appimage.py` refuses any other glibc. Inputs: the original extracted disc under `game/` and the firmware codecs under `firmware/` (only their names, sizes and SHA-256 are recorded, to verify the player's disc), a git checkout of ps3recomp next to this one, the official standalone 7-Zip Linux distribution (`7zz` and `License.txt`) and the official AppImage type2-runtime x86_64 binary. No files are downloaded automatically. Obtain the runtime from https://github.com/AppImage/type2-runtime and verify its published SHA-256.

```sh
podman build -t battride-build:ubuntu22.04 packaging/build-image
G=$(cd .. && pwd)   # parent holding this checkout and ../ps3recomp
podman run --rm --userns=keep-id --security-opt label=disable \
  -v "$G:$G" -v /path/inputs:/path/inputs:ro -w "$PWD" battride-build:ubuntu22.04 \
  python3 scripts/build_appimage.py \
    --runtime /path/inputs/runtime-x86_64 \
    --sevenzip-dir /path/inputs/7zip-linux --stage build-appimage/v0.3.2/AppDir \
    --output dist/BattrideWarPort-v0.3.2-x86_64.AppImage
# Corresponding source for the release page (runs as container root; needs network):
podman run --rm --security-opt label=disable -v "$G:$G" -w "$PWD" battride-build:ubuntu22.04 \
  python3 scripts/collect_sources.py --stage build-appimage/v0.3.2/AppDir \
    --out dist/BattrideWarPort-v0.3.2-sources.tar --runtime-commit <type2-runtime commit>
```

Publish the sources tar with every AppImage, from the same build: `collect_sources.py` maps each file listed in `app/system-files.txt` to its Ubuntu package, downloads the source packages of exactly the installed versions, and adds 7-Zip and the AppImage runtime with the libfuse and squashfuse sources it links.

What goes in:

- `usr/share/battride/port/`: the files listed in `PUBLIC_FILES.txt`, nothing else.
- `usr/share/battride/ps3recomp/`: `git archive` of the commit pinned in `recompile.json` (local changes never ship) and a `.ps3recomp-commit` stamp, which `scripts/generate.py` accepts in place of a git checkout.
- `usr/toolchain/`: assembled by `scripts/appimage_toolchain.py` from the build image's packages: GCC 11, Clang 14, binutils, CMake 3.22, Ninja, patch, the glibc 2.35 and Linux headers, SDL2, Vulkan headers and the static glslang/SPIRV-Tools libraries. The compilers run with `--sysroot`, so the game links against glibc 2.35 whatever the host has; `toolchain.cmake` points CMake at the sysroot, and the package CMake files that hardcode `/usr` are rewritten to follow `CMAKE_SYSROOT`. Tool processes take only glibc and the C++ runtime from the host (`runtime/` holds their other libraries, LLVM 14 included under its own soname).
- `packaging/glslang-compat`: Ubuntu 22.04's glslang installs neither `glslangConfig.cmake` nor `Public/ResourceLimits.h`; the shim supplies both on top of the packaged static libraries, so the SDK stays unmodified. The local build must report `Vulkan: guest programs available (glslang 11.8.0)`, or the launcher stops.

The runner is linked with `PORT_PORTABLE=ON`, which hides the static shader-tool symbols (an exported SPIRV-Tools copy can break RADV), and with an `$ORIGIN/lib` RPATH: the launcher copies SDL2 and the libraries it needs from the AppImage (`game_libs` in `app/package.json`) into `runner/lib/`.

Nothing in the AppImage uses `LD_LIBRARY_PATH`. It would leak the bundled libraries into host programs started from it: ninja runs every command through `/bin/sh`, which on Arch-based systems is bash linked against the host's newer readline, and the bundled Ubuntu readline broke it. Instead, `patchelf` gives each bundled executable a relative DT_RPATH (inherited by the libraries it loads), the toolchain's tools point at `usr/toolchain/runtime/`, and libraries with their own RUNPATH (LLVM, libpulse) are rewritten the same way.

The builder refuses existing stage/output paths. It never bundles libc, the dynamic loader, the C++ runtime, the GL/Vulkan loaders, DRM/GBM/LLVM, or the core X11/xcb/Wayland libraries that Mesa and NVIDIA link; those come from the host so they match its GPU driver. Toolkit helpers that are not on every host (GTK, SDL2, xcb-util, xkbcommon) are bundled. RPCS3 runs through its own `AppRun`, which uses RPCS3's `checkrt` C++ runtime on hosts older than it needs. Unresolved imports seen at build time are listed in `app/unresolved-build-libraries.txt` (none are expected). Dependency paths are recorded in `app/library-sources.json`; component hashes are in `app/package.json`. Build-image package documentation (including the toolchain's licenses) is retained, and `app/CREDITS.md` is shown by the launcher's **Credits & licenses** button.

## Arch-based distributions in 0.3.2

On CachyOS the build stopped at CMake's first compiler check with `/bin/sh: symbol lookup error: undefined symbol: rl_trim_arg_from_keyseq`: the build environment's `LD_LIBRARY_PATH` made the host's bash load Ubuntu's older readline. Version 0.3.2 drops `LD_LIBRARY_PATH` everywhere in favour of relative RPATHs (see above). The game build was verified end to end in an Arch Linux container (bash 5.3, readline 8.3, glibc 2.44).

## RPCS3 download and published sources in 0.3.1

Version 0.3.0 carried RPCS3's AppImage, with its Qt and other libraries, without their sources. Version 0.3.1 no longer redistributes RPCS3: the launcher downloads the official pinned build when importing and deletes it afterwards. Every other bundled binary's source is published as `BattrideWarPort-v0.3.1-sources.tar` beside the AppImage, and the launcher has a **Credits & licenses** button ([CREDITS.md](../CREDITS.md)).

## Builds on the player's computer in 0.3.0

Version 0.2.0 carried a prebuilt runner, that is the game's code translated from the EBOOT, so it could not be published. Version 0.3.0 ships no runner: the launcher generates the sources from the player's EBOOT and compiles them with the bundled toolchain. The CPU requirement drops to SSE4.1, and every CPU gets a native build.

## Portable build in 0.2.0

Version 0.1.1 bundled Fedora's glibc and loader and needed the build machine's own libraries. Version 0.2.0 is built in Ubuntu 22.04 against the host graphics stack: an x86-64-v3 runner with shader translation linked statically, a launcher CPU check for the x86-64-v3 features, the Vulkan window check before the game starts, and RPCS3's `checkrt` runtime on hosts with an older libstdc++.

## ISO import fix in 0.1.1

The initial 0.1 package inadvertently depended on Fedora’s `/usr/libexec/7zip/7z.so`, so a different PC could fail at the first manifest file (`PS3_GAME/ICON0.PNG`). Version 0.1.1 uses the official standalone `7zz`, checks actual UDF support in `--check`, and records the ISO reader output in the import log. Disc size/hash validation remains enabled.
