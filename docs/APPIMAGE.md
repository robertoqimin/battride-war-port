# Linux AppImage

The AppImage contains **no game code or data**. It carries the port's public sources (exactly the files in `PUBLIC_FILES.txt`), the pinned ps3recomp SDK, an RPCS3 helper to decrypt your EBOOT, 7-Zip, FFmpeg and a compiler toolchain. On first launch it imports your disc, translates your own EBOOT into C and compiles the game for your CPU. It runs on distributions with glibc 2.35 or newer; see "System requirements" in the [README](../README.md) for CPUs, GPUs, RAM and disk. It has been run end to end on Fedora (Ryzen 5 4600H, GTX 1650); the RPCS3, 7-Zip and FFmpeg helpers were also started inside Ubuntu 22.04. Other distributions and GPUs require testing. It does not fix the remaining combat performance drops.

## Run

Make the AppImage executable and open it:

```sh
chmod +x BattrideWarPort-v0.3.0-x86_64.AppImage
./BattrideWarPort-v0.3.0-x86_64.AppImage
```

If FUSE is unavailable, run `./BattrideWarPort-v0.3.0-x86_64.AppImage --appimage-extract-and-run`.

Select the Japan BLJS10220 ISO and click **Import ISO & Play**. The first launch:

1. verifies the game files against the supported disc (size and SHA-256), decrypts the EBOOT with the included RPCS3 helper and extracts the audio codecs from the firmware update on the disc (`import.log`);
2. translates the EBOOT into PPU/SPU sources with the SDK tools (`build.log`);
3. compiles the game with `-march=native` for this CPU, one job per 2 GB of available memory (`build.log`). This took 13 minutes with 4 jobs on a Ryzen 5 4600H; expect 15-60 minutes;
4. checks that a Vulkan GPU can create a window surface, a swapchain and BC textures (`graphics.log`), then starts the game (`game.log`).

The generated sources and object files are deleted after the build; only `runner/game-runner` stays in the data folder. Later launches reuse it until the AppImage version or the CPU changes. No separate firmware download, compiler, development package or administrator access is required.

Default data: `~/.local/share/battride-war-port/`. Saves are inside this folder; copy the whole folder to transfer an installation (the game is rebuilt if the other computer has a different CPU). The ISO path is remembered in `~/.config/battride-war-port/settings.json`. If moving an imported installation changes the ISO path, select a new empty data folder and import again; existing imports are preserved. Logs are in `logs/` under the data folder. MangoHud is optional and must be installed on the destination PC if selected.

On laptops with two GPUs the game picks the discrete one. If it picks the wrong device, the `device N:` lines in `game.log` list them and `PS3RECOMP_VK_DEVICE=N` forces one.

Headless checks:

```sh
./BattrideWarPort-v0.3.0-x86_64.AppImage --check    # helpers and build tools start
./BattrideWarPort-v0.3.0-x86_64.AppImage --import-only /path/game.iso --data-dir /new/empty/data   # import and build
```

## Build the AppImage

Everything is built inside the Ubuntu 22.04 image; `build_appimage.py` refuses any other glibc. Inputs: the original extracted disc under `game/` and the firmware codecs under `firmware/` (only their names, sizes and SHA-256 are recorded, to verify the player's disc), a git checkout of ps3recomp next to this one, the official standalone 7-Zip Linux distribution (`7zz` and `License.txt`), an extracted official RPCS3 AppImage (with its `checkrt/` directory) and the official AppImage type2-runtime x86_64 binary. No files are downloaded automatically. Obtain the runtime from https://github.com/AppImage/type2-runtime and verify its published SHA-256.

```sh
podman build -t battride-build:ubuntu22.04 packaging/build-image
G=$(cd .. && pwd)   # parent holding this checkout and ../ps3recomp
podman run --rm --userns=keep-id --security-opt label=disable \
  -v "$G:$G" -v /path/inputs:/path/inputs:ro -w "$PWD" battride-build:ubuntu22.04 \
  python3 scripts/build_appimage.py \
    --runtime /path/inputs/runtime-x86_64 --rpcs3-dir /path/inputs/RPCS3/AppDir \
    --sevenzip-dir /path/inputs/7zip-linux --stage build-appimage/v0.3.0/AppDir \
    --output dist/BattrideWarPort-v0.3.0-x86_64.AppImage
```

What goes in:

- `usr/share/battride/port/`: the files listed in `PUBLIC_FILES.txt`, nothing else.
- `usr/share/battride/ps3recomp/`: `git archive` of the commit pinned in `recompile.json` (local changes never ship) and a `.ps3recomp-commit` stamp, which `scripts/generate.py` accepts in place of a git checkout.
- `usr/toolchain/`: assembled by `scripts/appimage_toolchain.py` from the build image's packages: GCC 11, Clang 14, binutils, CMake 3.22, Ninja, patch, the glibc 2.35 and Linux headers, SDL2, Vulkan headers and the static glslang/SPIRV-Tools libraries. The compilers run with `--sysroot`, so the game links against glibc 2.35 whatever the host has; `toolchain.cmake` points CMake at the sysroot, and the package CMake files that hardcode `/usr` are rewritten to follow `CMAKE_SYSROOT`. Tool processes take only glibc and the C++ runtime from the host (`runtime/` holds their other libraries, LLVM 14 included under its own soname).
- `packaging/glslang-compat`: Ubuntu 22.04's glslang installs neither `glslangConfig.cmake` nor `Public/ResourceLimits.h`; the shim supplies both on top of the packaged static libraries, so the SDK stays unmodified. The local build must report `Vulkan: guest programs available (glslang 11.8.0)`, or the launcher stops.

The runner is linked with `PORT_PORTABLE=ON`, which hides the static shader-tool symbols (an exported SPIRV-Tools copy can break RADV).

The builder refuses existing stage/output paths. It never bundles libc, the dynamic loader, the C++ runtime, the GL/Vulkan loaders, DRM/GBM/LLVM, or the core X11/xcb/Wayland libraries that Mesa and NVIDIA link; those come from the host so they match its GPU driver. Toolkit helpers that are not on every host (GTK, SDL2, GLEW, xcb-util, xkbcommon) are bundled. RPCS3 needs a newer libstdc++ than GCC 12 hosts provide; the importer then runs it with RPCS3's own `checkrt` runtime. Unresolved imports seen at build time are listed in `app/unresolved-build-libraries.txt` (only RPCS3's `GLIBCXX` versions, which `checkrt` covers, are expected). Dependency paths are recorded in `app/library-sources.json`; component hashes are in `app/package.json`. Build-image package documentation (including the toolchain's licenses) and RPCS3 notices are retained. RPCS3 source: https://github.com/RPCS3/rpcs3 (helper build 0b0fa082).

## Builds on the player's computer in 0.3.0

Version 0.2.0 carried a prebuilt runner, that is the game's code translated from the EBOOT, so it could not be published. Version 0.3.0 ships no runner: the launcher generates the sources from the player's EBOOT and compiles them with the bundled toolchain. The CPU requirement drops to SSE4.1, and every CPU gets a native build.

## Portable build in 0.2.0

Version 0.1.1 bundled Fedora's glibc and loader and needed the build machine's own libraries. Version 0.2.0 is built in Ubuntu 22.04 against the host graphics stack: an x86-64-v3 runner with shader translation linked statically, a launcher CPU check for the x86-64-v3 features, the Vulkan window check before the game starts, and RPCS3's `checkrt` runtime on hosts with an older libstdc++.

## ISO import fix in 0.1.1

The initial 0.1 package inadvertently depended on Fedora’s `/usr/libexec/7zip/7z.so`, so a different PC could fail at the first manifest file (`PS3_GAME/ICON0.PNG`). Version 0.1.1 uses the official standalone `7zz`, checks actual UDF support in `--check`, and records the ISO reader output in the import log. Disc size/hash validation remains enabled.
