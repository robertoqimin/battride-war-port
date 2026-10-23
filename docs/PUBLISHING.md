# Publishing the code

`PUBLIC_FILES.txt` is the explicit file allowlist for this source package. `.gitignore` excludes the game, firmware, saves, generated output, builds, and logs. Do not use `git add -f` on those directories.

## Check and package

From the project root:

```bash
python3 -m unittest discover -s tests -p test_publication.py
python3 scripts/export_source.py
python3 scripts/export_source.py --output /tmp/kamenriderbattridewarsport-source.zip \
  --manifest /tmp/kamenriderbattridewarsport-source-manifest.json
```

Output paths must not already exist. The exporter never overwrites existing files. It accepts only explicitly listed text files, rejects symlinks and private paths, and creates a ZIP without Git history or local data. This check does not replace content review when the code changes in the future.

To publish through the GitHub interface, extract this ZIP and upload the files inside its directory, rather than your entire local tree.

## Publish with Git

Create an empty repository on your GitHub account. Then, from the port root, if there is no Git repository yet:

```bash
git init --initial-branch=main
git add --pathspec-from-file=PUBLIC_FILES.txt
git diff --cached --stat
git diff --cached --name-only
```

Check that the list contains no `game/`, `firmware/`, `gamedata/`, `src/recomp/`, `spu/`, `analysis/`, or `build*/` paths. Then commit and configure your repository URL:

```bash
git commit -m "Prepare experimental source release"
git remote add origin https://github.com/YOUR_USERNAME/kamenriderbattridewarsport.git
git push -u origin main
```

Replace `YOUR_USERNAME`. If Git, remotes, or commits already exist, inspect the current state and adapt the commands; do not reinitialize or replace history. Local preparation does not commit, create a remote repository, or push automatically.

Suggested description:

> Experimental Kamen Rider: Battride War (BLJS10220) port using PS3Recomp and Vulkan. The start of the mission has been validated with movement, pause, and attacks; performance is low and visual glitches remain. Requires local game data and PPU/SPU generation. No game, firmware, keys, or saves included.

Do not advertise this as a complete game or stable port. The documentation describes exactly the section validated. Licenses and credits are in `LICENSE` and `THIRD_PARTY_NOTICES.md`.
