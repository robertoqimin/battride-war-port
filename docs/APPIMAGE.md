# Private Linux AppImage

This experimental package carries a runner built for x86-64-v3 (AVX2/FMA) in an Ubuntu 22.04 image, so it runs on distributions with glibc 2.35 or newer. It does not fix the remaining combat performance drops. A Vulkan GPU with BC texture support and working host drivers is required; see "System requirements" in the [README](../README.md). It has been run on Fedora (Ryzen 5 4600H, GTX 1650); the RPCS3, 7-Zip and FFmpeg helpers were also started inside Ubuntu 22.04. Other distributions and GPUs require testing.

## Run

Copy `dist/BattrideWarPort-v0.2.0-x86_64.AppImage` to the other PC, make it executable, and open it:

```sh
chmod +x BattrideWarPort-v0.2.0-x86_64.AppImage
./BattrideWarPort-v0.2.0-x86_64.AppImage
```

If FUSE is unavailable, run `./BattrideWarPort-v0.2.0-x86_64.AppImage --appimage-extract-and-run`.
Select the Japan BLJS10220 ISO and click **Import ISO & Play**. Allow at least 5 GB of free space. First import verifies the game files, decrypts its EBOOT using the included RPCS3 helper and extracts the required audio codecs from the firmware update on the disc. No separate firmware download or administrator access is required. The helper does not run the game. Before the game starts, a small Vulkan check (`graphics.log`) confirms that a GPU can create a window surface, a swapchain and BC textures.

Default data: `~/.local/share/battride-war-port/`. Saves are inside this folder; copy the whole folder to transfer an installation. The ISO path is remembered in `~/.config/battride-war-port/settings.json`. If moving an imported installation changes the ISO path, select a new empty data folder and import again; existing imports are preserved. Logs are in `logs/` under the data folder. MangoHud is optional and must be installed on the destination PC if selected.

On laptops with two GPUs the game picks the discrete one. If it picks the wrong device, the `device N:` lines in `game.log` list them and `PS3RECOMP_VK_DEVICE=N` forces one.

The AppImage contains tools and libraries, but no ISO, game assets, EBOOT ELF, saves, firmware PUP or firmware codecs. It is a private local test artifact and is not uploaded by the builder. The runner contains the locally translated game program. Keep source export separate from this private binary.

## Build

Everything is built inside the Ubuntu 22.04 image; `build_appimage.py` refuses any other glibc. Inputs: the generated PPU/SPU sources, the original extracted disc under `game/`, local firmware codecs under `firmware/`, the official standalone 7-Zip Linux distribution (`7zz` and `License.txt`), an extracted official RPCS3 AppImage (with its `checkrt/` directory) and the official AppImage type2-runtime x86_64 binary. No files are downloaded automatically. Obtain the runtime from https://github.com/AppImage/type2-runtime and verify its published SHA-256.

```sh
podman build -t battride-build:ubuntu22.04 packaging/build-image
G=$(cd .. && pwd)   # parent holding this checkout and ../ps3recomp
run() { podman run --rm --userns=keep-id --security-opt label=disable \
          -v "$G:$G" -v /path/inputs:/path/inputs:ro -w "$PWD" battride-build:ubuntu22.04 "$@"; }

run cmake -S . -B build-portable -G Ninja \
  -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=g++ -DCMAKE_BUILD_TYPE=Debug \
  -DCMAKE_C_FLAGS_DEBUG=-O2 -DCMAKE_CXX_FLAGS_DEBUG=-O2 \
  -DPORT_ENABLE_SPU=ON -DPS3RECOMP_RSX_VULKAN=ON \
  -DPORT_PORTABLE=ON -DPORT_MARCH=x86-64-v3 \
  -DPython3_EXECUTABLE=/usr/bin/python3 \
  -Dglslang_DIR="$PWD/packaging/glslang-compat"
run cmake --build build-portable -j4
run python3 scripts/build_appimage.py --runner build-portable/kamenriderbattridewarsport \
  --runtime /path/inputs/runtime-x86_64 --rpcs3-dir /path/inputs/RPCS3/AppDir \
  --sevenzip-dir /path/inputs/7zip-linux --output dist/BattrideWarPort-v0.2.0-x86_64.AppImage
```

Configure must report `Vulkan: guest programs available (glslang 11.8.0)`. Ubuntu 22.04's glslang installs neither `glslangConfig.cmake` nor `Public/ResourceLimits.h`; `packaging/glslang-compat` supplies both on top of the packaged static libraries, so the SDK checkout stays unmodified. A full build takes about 15 minutes with four jobs.

The builder refuses existing stage/output paths. Use `--stage` and another output filename for subsequent builds. It never bundles libc, the dynamic loader, the C++ runtime, the GL/Vulkan loaders, DRM/GBM/LLVM, or the core X11/xcb/Wayland libraries that Mesa and NVIDIA link; those come from the host so they match its GPU driver. Toolkit helpers that are not on every host (GTK, SDL2, GLEW, xcb-util, xkbcommon) are bundled. RPCS3 needs a newer libstdc++ than GCC 12 hosts provide; the importer then runs it with RPCS3's own `checkrt` runtime. Unresolved imports seen at build time are listed in `app/unresolved-build-libraries.txt` (only RPCS3's `GLIBCXX` versions, which `checkrt` covers, are expected). Dependency paths are recorded in `app/library-sources.json`; component hashes are in `app/package.json`. Build-image package documentation and RPCS3 notices are retained. RPCS3 source: https://github.com/RPCS3/rpcs3 (helper build 0b0fa082).

Headless checks:

```sh
./BattrideWarPort-v0.2.0-x86_64.AppImage --check
./BattrideWarPort-v0.2.0-x86_64.AppImage --import-only /path/game.iso --data-dir /new/empty/data
```

## Portable build in 0.2.0

Version 0.1.1 bundled Fedora's glibc and loader and needed the build machine's own libraries. Version 0.2.0 is built in Ubuntu 22.04 against the host graphics stack: an x86-64-v3 runner with shader translation linked statically, a launcher CPU check for the x86-64-v3 features, the Vulkan window check before the game starts, and RPCS3's `checkrt` runtime on hosts with an older libstdc++.

## ISO import fix in 0.1.1

The initial 0.1 package inadvertently depended on Fedora’s `/usr/libexec/7zip/7z.so`, so a different PC could fail at the first manifest file (`PS3_GAME/ICON0.PNG`). Version 0.1.1 uses the official standalone `7zz`, checks actual UDF support in `--check`, and records the ISO reader output in the import log. Disc size/hash validation remains enabled.
