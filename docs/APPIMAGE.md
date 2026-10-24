# Private Linux AppImage

This experimental package uses the current local compiled runner (AVX2/FMA, Zen 2 target), compatible with Ryzen 7 5700X. It does not fix the remaining combat performance drops. A Vulkan-capable GPU with working Linux drivers is required. Only the build Fedora system has been validated; other distributions and GPUs require testing.

## Run

Copy `dist/BattrideWarPort-x86_64.AppImage` to the other PC, make it executable, and open it:

```sh
chmod +x BattrideWarPort-x86_64.AppImage
./BattrideWarPort-x86_64.AppImage
```

If FUSE is unavailable, run `./BattrideWarPort-x86_64.AppImage --appimage-extract-and-run`.
Select the Japan BLJS10220 ISO and click **Import ISO & Play**. Allow at least 5 GB of free space. First import verifies the game files, decrypts its EBOOT using the included RPCS3 helper and extracts the required audio codecs from the firmware update on the disc. No separate firmware download or administrator access is required. The helper does not run the game.

Default data: `~/.local/share/battride-war-port/`. Saves are inside this folder; copy the whole folder to transfer an installation. The ISO path is remembered in `~/.config/battride-war-port/settings.json`. If moving an imported installation changes the ISO path, select a new empty data folder and import again; existing imports are preserved. Logs are in `logs/` under the data folder. MangoHud is optional and must be installed on the destination PC if selected.

The AppImage contains tools and libraries, but no ISO, game assets, EBOOT ELF, saves, firmware PUP or firmware codecs. It is a private local test artifact and is not uploaded by the builder. The runner contains the locally translated game program. Keep source export separate from this private binary.

## Build

Requires an existing `build-vulkan/kamenriderbattridewarsport`, the original extracted disc under `game/`, local firmware codecs under `firmware/`, Python 3.14/PyGObject/GTK 3, the official standalone 7-Zip Linux distribution (`7zz`), FFmpeg, mksquashfs, an extracted official RPCS3 AppImage and the official AppImage type2-runtime x86_64 binary. No files are downloaded automatically. Obtain the runtime from https://github.com/AppImage/type2-runtime and verify its published SHA-256.

```sh
python3 scripts/build_appimage.py --runtime /path/runtime-x86_64 --rpcs3-dir /path/RPCS3/AppDir --sevenzip-dir /path/7zip-linux --output dist/BattrideWarPort-x86_64.AppImage
```

The builder refuses existing stage/output paths. Use `--stage` and another output filename for subsequent builds. It bundles the matching Fedora dynamic loader and glibc; GPU drivers remain supplied by the host. Dependency paths are recorded in `app/library-sources.json`; component hashes are in `app/package.json`. Installed dependency licenses and RPCS3 notices are retained. RPCS3 source: https://github.com/RPCS3/rpcs3 (helper build 0b0fa082). Generic Vulkan/GL loaders are bundled; vendor driver implementations are not.

Headless checks:

```sh
./BattrideWarPort-x86_64.AppImage --check
./BattrideWarPort-x86_64.AppImage --import-only /path/game.iso --data-dir /new/empty/data
```

## ISO import fix in 0.1.1

The initial 0.1 package inadvertently depended on Fedora’s `/usr/libexec/7zip/7z.so`, so a different PC could fail at the first manifest file (`PS3_GAME/ICON0.PNG`). Version 0.1.1 uses the official standalone `7zz`, checks actual UDF support in `--check`, and records the ISO reader output in the import log. Disc size/hash validation remains enabled.
