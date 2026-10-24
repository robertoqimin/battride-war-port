"""Local, transactional import of the supported user-supplied PS3 disc."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import signal
import subprocess
import threading
import time
import uuid


class ImportError(RuntimeError):
    pass


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def safe_name(name):
    p = PurePosixPath(name)
    if not name or p.is_absolute() or '..' in p.parts or '\\' in name or '\n' in name or '\r' in name:
        raise ImportError('Unsafe path in disc image')
    return name


def disc_entries(text):
    entries = {}
    for block in text.replace('\r\n', '\n').split('\n\n'):
        fields = dict(line.split(' = ', 1) for line in block.splitlines() if ' = ' in line)
        if 'Path' not in fields:
            continue
        name = safe_name(fields['Path'])
        if fields.get('Symbolic Link') or fields.get('Hard Link'):
            raise ImportError('Links in disc images are not supported')
        if name in entries:
            raise ImportError('Duplicate disc path: ' + name)
        entries[name] = fields
    return entries


class Runner:
    def __init__(self):
        self.cancelled = threading.Event()
        self.lock = threading.Lock()
        self.current = None

    def stop(self):
        self.cancelled.set()
        with self.lock:
            p = self.current
        if p and p.poll() is None:
            try:
                os.killpg(p.pid, signal.SIGTERM)
                p.wait(timeout=2)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(p.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            except ProcessLookupError:
                pass

    def run(self, args, env=None, cwd=None, log=None, capture=False):
        if self.cancelled.is_set():
            raise ImportError('Operation cancelled')
        p = subprocess.Popen([str(x) for x in args], env=env, cwd=cwd,
                             stdout=subprocess.PIPE if capture else (log or subprocess.DEVNULL),
                             stderr=subprocess.STDOUT, start_new_session=True)
        with self.lock:
            self.current = p
        if self.cancelled.is_set():
            self.stop()
        try:
            output = p.communicate()[0] if capture else None
            code = p.wait()
        finally:
            with self.lock:
                if self.current is p:
                    self.current = None
        if self.cancelled.is_set():
            raise ImportError('Operation cancelled')
        return code, (output or b'').decode('utf-8', errors='replace')


class Package:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.meta = json.loads((self.root / 'app/package.json').read_text())
        self.manifest = json.loads((self.root / 'app/disc-manifest.json').read_text())

    def tool(self, name, *args):
        return [self.root / 'usr/lib/ld-linux-x86-64.so.2', '--library-path',
                self.root / 'usr/lib', self.root / 'usr/bin' / name, *args]

    def helper_env(self, stage):
        env = os.environ.copy()
        for key in list(env):
            if key.startswith(('APPIMAGE', 'PYTHON', 'GI_', 'GTK_', 'GDK_', 'QT_')) or key in (
                    'APPDIR', 'LD_LIBRARY_PATH', 'LD_PRELOAD', 'GIO_MODULE_DIR', 'GSETTINGS_SCHEMA_DIR', 'MANGOHUD'):
                env.pop(key, None)
        env.update(XDG_CONFIG_HOME=str(stage / 'rpcs3-config'),
                   XDG_CACHE_HOME=str(stage / 'rpcs3-cache'), XDG_DATA_HOME=str(stage / 'rpcs3-data'))
        return env

    def rpcs3(self, *args):
        return [self.root / 'usr/lib/ld-linux-x86-64.so.2', '--library-path',
                str(self.root / 'usr/lib') + ':' + str(self.root / 'usr/rpcs3/usr/lib'),
                self.root / 'usr/rpcs3/usr/bin/rpcs3', '--allow-any-location', '--headless', *args]

    def verify_game(self, game, status=lambda _: None):
        for i, (name, info) in enumerate(self.manifest.items()):
            safe_name(name)
            p = game / name
            if p.is_symlink() or any(x.is_symlink() for x in p.parents if x != game.parent):
                raise ImportError('Imported game contains a link: ' + name)
            if not p.is_file() or p.stat().st_size != info['size'] or digest(p) != info['sha256']:
                raise ImportError('Disc data is incomplete, encrypted, or differs from BLJS10220: ' + name)
            if i % 500 == 0:
                status('Verifying game files: %d / %d' % (i + 1, len(self.manifest)))

    def import_iso(self, iso, data, runner, status=lambda _: None, log=None):
        iso, data = Path(iso).resolve(), Path(data).resolve()
        if not iso.is_file():
            raise ImportError('Select a readable ISO file')
        data.mkdir(parents=True, exist_ok=True)
        initial = iso.stat()
        identity = {'path': str(iso), 'bytes': initial.st_size, 'mtime_ns': initial.st_mtime_ns}
        marker = data / 'import.json'
        if marker.exists():
            old = json.loads(marker.read_text())
            game = data / 'game'
            codecs = data / 'firmware/dev_flash/sys/external'
            if (old.get('source') == identity and (game / 'EBOOT.ELF').is_file()
                    and digest(game / 'EBOOT.ELF') == self.meta['elf_sha256']
                    and all((codecs / n).is_file() and digest(codecs / n) == h
                            for n, h in self.meta['codecs'].items())):
                status('Using previously imported game')
                return game
            raise ImportError('This data folder already contains another import. Choose a new data folder; existing data and saves were preserved.')
        if (data / 'game').exists() or (data / 'firmware').exists():
            raise ImportError('The data folder contains an incomplete import. Choose an empty data folder; existing files were preserved.')
        free = shutil.disk_usage(data).free
        required = sum(x['size'] for x in self.manifest.values()) + 2 * 1024**3
        if free < required:
            raise ImportError('Not enough free space. Allow at least 5 GB for import and game data.')
        stage = data / ('.import-' + uuid.uuid4().hex)
        game = stage / 'game'
        game.mkdir(parents=True)
        committed = []
        try:
            status('Checking disc image...')
            code, listing = runner.run(self.tool('7z', 'l', '-slt', '-ba', '--', iso), capture=True, log=None)
            if log:
                log.write(('ISO listing (7-Zip exit %d):\n' % code + listing + '\n').encode('utf-8'))
                log.flush()
            if 'Codec Load Error' in listing:
                raise ImportError('The bundled ISO reader could not load its format support. Update the AppImage; see import.log for details.')
            entries = disc_entries(listing)
            if not entries:
                raise ImportError('Could not read the ISO filesystem. Check that the file is a complete ISO image. See import.log for the ISO reader output.')
            for name, info in self.manifest.items():
                if name not in entries:
                    raise ImportError('Required disc file is missing from the ISO: ' + name + '. Expected the Japan BLJS10220 edition; see import.log.')
                if entries[name].get('Size') != str(info['size']):
                    raise ImportError('Disc file size differs from the supported Japan BLJS10220 edition: ' + name +
                                      ' (expected %s bytes, found %s). See import.log.' % (info['size'], entries[name].get('Size', 'unknown')))
            pup = 'PS3_UPDATE/PS3UPDAT.PUP'
            if pup not in entries:
                raise ImportError('The ISO must include PS3_UPDATE/PS3UPDAT.PUP for local audio codec setup.')
            selected = stage / 'selected-files.txt'
            selected.write_text('\n'.join([*self.manifest, pup]) + '\n')
            status('Extracting your ISO. This can take a few minutes...')
            code, _ = runner.run(self.tool('7z', 'x', '-y', '-bd', '-bb0', '-spd', '-scsUTF-8',
                                          '-i@' + str(selected), '-o' + str(game), '--', iso), log=log)
            # Some PS3 UDF images return a header warning/error. Accept output
            # only after every expected file passes a size and SHA-256 check.
            self.verify_game(game, status)
            if code and log:
                log.write(b'Archive returned a nonzero status; every expected game file was verified.\n')
            status('Preparing EBOOT from your disc...')
            runner.run(self.rpcs3('--decrypt', game / 'PS3_GAME/USRDIR/EBOOT.BIN'),
                       env=self.helper_env(stage), log=log)
            elf = game / 'PS3_GAME/USRDIR/EBOOT.elf'
            if not elf.is_file() or digest(elf) != self.meta['elf_sha256']:
                raise ImportError('EBOOT could not be prepared or does not match this port.')
            elf.rename(game / 'EBOOT.ELF')
            status('Extracting audio codecs from your disc firmware...')
            runner.run(self.rpcs3('--installfw', game / pup), env=self.helper_env(stage), log=log)
            fw = stage / 'firmware/dev_flash/sys/external'
            fw.mkdir(parents=True)
            source = stage / 'rpcs3-config/rpcs3/dev_flash/sys/external'
            for name, expected in self.meta['codecs'].items():
                p = source / name
                if not p.is_file() or digest(p) != expected:
                    raise ImportError('The disc firmware did not produce the supported audio codec: ' + name)
                shutil.copy2(p, fw / name)
            shutil.rmtree(game / 'PS3_UPDATE')
            end = iso.stat()
            if end.st_size != initial.st_size or end.st_mtime_ns != initial.st_mtime_ns:
                raise ImportError('The ISO changed during import. Please try again.')
            if runner.cancelled.is_set():
                raise ImportError('Operation cancelled')
            for name in ('game', 'firmware'):
                target = data / name
                if target.exists():
                    raise ImportError('Import destination appeared during setup; it was not overwritten.')
                (stage / name).rename(target)
                committed.append(target)
            tmp = data / 'import.json.tmp'
            tmp.write_text(json.dumps({'source': identity, 'title_id': 'BLJS10220', 'elf_sha256': self.meta['elf_sha256']}, indent=2))
            tmp.replace(marker)
            return data / 'game'
        except BaseException:
            for p in committed:
                shutil.rmtree(p)
            raise
        finally:
            shutil.rmtree(stage, ignore_errors=True)

    def game_env(self, data, logs, mangohud=False):
        env = os.environ.copy()
        # Keep developer diagnostics and automated controller input out of the
        # portable player's launch, even if inherited from a build terminal.
        for k in list(env):
            if k.startswith(('PAD_', 'PORT_', 'PPU_', 'SPU_', 'YDKJ_', 'GCM_', 'RSX_')) or k in (
                    'LD_LIBRARY_PATH', 'LD_PRELOAD', 'PS3_VFS_ROOT', 'PS3_GAMEDATA_ROOT', 'PS3_DEV_FLASH'):
                env.pop(k, None)
        env.update(PS3_VFS_ROOT=str(data / 'game'), PS3_GAMEDATA_ROOT=str(data / 'gamedata'),
                   PS3_DEV_FLASH=str(data / 'firmware/dev_flash'), PS3RECOMP_VK_GUEST_PROGRAMS='1',
                   PS3RECOMP_VK_WINDOW='1', PORT_GCM_EXPAND_BUFFERS='0',
                   PORT_FRAME_TIMES=str(logs / 'frames.csv'))
        if mangohud:
            env.update(MANGOHUD='1', MANGOHUD_CONFIG='fps,frametime,frame_timing,cpu_stats,gpu_stats,ram,vram')
        else:
            env.pop('MANGOHUD', None)
        return env
