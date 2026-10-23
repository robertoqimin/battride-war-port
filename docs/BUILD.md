# Building from the published sources

This package contains port code, configuration, and a small integration patch. Game files, firmware, and complete generated PPU/SPU sources remain on the builder's computer. None of this data is downloaded automatically.

## Validated environment

Fedora 44 x86_64, clang 22, GCC 16, CMake 4, Ninja, and NVIDIA GTX 1650. The project uses C17/C++20 and Python 3.11 or later. Other distributions and GPUs still require validation.

The following package names match those used on this Fedora system. Install them in your terminal:

```bash
sudo dnf install git patch cmake ninja-build clang gcc-c++ python3 python3-pip \
  sdl2-compat-devel vulkan-headers vulkan-loader \
  glslang glslang-devel spirv-tools-devel pkgconf-pkg-config ffmpeg-free
```

A working Vulkan driver for your GPU is required. `ffmpeg` and `ffprobe` must be on PATH for PAMF video playback. FFmpeg development headers and spirv-cross are not required for this port's Vulkan backend.

## 1. Pin the SDK

Keep the official checkout alongside this port's directory:

```text
workspace/
  ps3recomp/
  kamenriderbattridewarsport/
```

Run these commands in the workspace directory to create a fresh SDK checkout:

```bash
git clone https://github.com/sp00nznet/ps3recomp.git
cd ps3recomp
git checkout --detach a6d76c895f77eb30b90a806c830544e61821b77f
python3 -m venv .venv
.venv/bin/python -m pip install -r tools/requirements.txt
cd ../kamenriderbattridewarsport
```

If the SDK already exists, do not clone over or replace its directory: check the commit and preserve local changes. The local `*_bridge.*` files depend on this revision's interfaces. Updating the SDK requires renewed validation.

## 2. Prepare local data

Use a local extraction of your disc and the decrypted ELF matching **BLJS10220**:

```text
kamenriderbattridewarsport/
  game/
    EBOOT.ELF
    PS3_GAME/
      PARAM.SFO
      USRDIR/
        nativePS/
          ...game files...
```

The expected SHA-256 of `game/EBOOT.ELF` is:

```text
a53b7bca5d47490710ba02af5f885e1219d10c7a1a456fcf6e13a48db668a014
```

Check it with `sha256sum game/EBOOT.ELF`. Other executables, updates, or regions have not been validated: the patch and SPU bridge addresses are specific to this version. This repository does not supply an ISO, EBOOT, keys, firmware, assets, or saves.

Firmware codecs are optional for building but required for the audio paths used by the game. See [README_FIRMWARE.md](../README_FIRMWARE.md) for the placement of locally obtained files.

## 3. Generate PPU/SPU sources and apply the patch

From the port root, in a fresh checkout:

```bash
../ps3recomp/.venv/bin/python scripts/generate.py --jobs 4
```

The script checks the SDK commit and ELF hash, analyzes the executable, generates the 84 PPU files, applies `patches/graphics-command-buffer-init.patch` without fuzz, and generates the accepted SPU programs. It refuses to replace existing `src/recomp/`, `spu/`, or `analysis/regeneration/` directories. Use `--verify-only` to check prerequisites only. For a different SDK location, add `--sdk /path/to/ps3recomp`.

PPU generation produces about 593 MiB of sources; also allow space for object files and the executable. On machines with limited RAM, reduce `--jobs` and build parallelism.

SPU generation deliberately uses `--allow-partial`: of the two detected images, only `615f0131…dc0657` is registered statically. The rejected audio image uses the interpreter in `spu_bridge.c`; this is not complete static translation. The generated registry is checked before installing the results. All generated results are ignored by Git.

The script uses these tools and options:

```text
ppu_loader.py game/EBOOT.ELF -o <analysis>
ppu_lifter.py game/EBOOT.ELF --functions <analysis>/EBOOT.functions.json
  --hle-stubs <analysis>/EBOOT.imports.json --output <ppu-sources>
  --jobs 4 --chunk-lines 80000
patch --batch --fuzz=0 -p1 -i patches/graphics-command-buffer-init.patch
build_spu_workloads.py --input game/EBOOT.ELF --lifted <spu-sources>
  --out <spu-sources>/spu_workloads.c --constructor --allow-partial
```

Use the script to run the sequence: it manages temporary directories and checks. `config.toml` is a reference configuration; this generation is controlled by the options above and `recompile.json`.

## 4. Build and launch

```bash
cmake --preset linux-vulkan \
  -DPython3_EXECUTABLE="$PWD/../ps3recomp/.venv/bin/python"
cmake --build --preset linux-vulkan
./run-vulkan.sh
```

For a different SDK location, add `-DPS3RECOMP_DIR=/path/to/ps3recomp` during configuration. Check that CMake reports `guest programs available` for Vulkan: without glslang, game shaders do not work correctly. The SDK loads Vulkan dynamically.

The game uses the `game/` tree as its VFS and creates installed data/saves in `gamedata/`. The launcher enables the window, shaders, and expanded buffers. There is no automatic time limit; `PORT_TEST_SECONDS=300 ./run-vulkan.sh` limits a diagnostic run. Graceful shutdown has not been validated on every path; time-limited tests sometimes required SIGKILL.

## 5. Verify

```bash
python3 -m unittest discover -s tests -p test_publication.py
python3 scripts/export_source.py
bash tests/test_graphics_buffers.sh
bash tests/test_gcm_jump.sh
bash tests/test_sail.sh
```

The C/C++ tests require generated/build results according to their dependencies. The audio regression uses the local disc's PAMF:

```bash
bash tests/test_sail_audio.sh
```

To check reads at a specified offset:

```bash
c++ -std=c++20 -O0 -ffunction-sections -fdata-sections \
  -Isrc/recomp -I../ps3recomp/include -I../ps3recomp/runtime/ppu \
  tests/test_fs_offset.cpp -Wl,--gc-sections -o build-vulkan/test_fs_offset
./build-vulkan/test_fs_offset
```

No test publishes files to GitHub. The build does not install dependencies or fetch game data automatically.
