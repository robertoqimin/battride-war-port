"""Local, transactional import of the supported user-supplied PS3 disc."""
import hashlib
import json
import os
import re
from pathlib import Path, PurePosixPath
import shutil
import signal
import ssl
import subprocess
import threading
import time
import urllib.error
import urllib.request
import uuid


class ImportError(RuntimeError):
    pass


def digest(path):
    with Path(path).open('rb') as stream:
        value = hashlib.sha256()
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
        return value.hexdigest()


# Where distributions keep the CA bundle; the bundled Python looks in Ubuntu's place.
CA_BUNDLES = ('/etc/ssl/certs/ca-certificates.crt', '/etc/pki/tls/certs/ca-bundle.crt',
              '/etc/ssl/ca-bundle.pem', '/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem', '/etc/ssl/cert.pem')


def download(url, dest, expected_sha256, expected_size, cancelled, status=lambda _: None):
    """Fetch url over verified TLS into dest; the SHA-256 must match."""
    cafile = os.environ.get('SSL_CERT_FILE') or next((c for c in CA_BUNDLES if Path(c).is_file()), None)
    context = ssl.create_default_context(cafile=cafile)
    value, done, shown = hashlib.sha256(), 0, 0.0
    try:
        with urllib.request.urlopen(url, context=context, timeout=60) as response, dest.open('wb') as out:
            while True:
                if cancelled.is_set():
                    raise ImportError('Operation cancelled')
                block = response.read(1024 * 1024)
                if not block:
                    break
                out.write(block)
                value.update(block)
                done += len(block)
                if time.monotonic() - shown > 1:
                    shown = time.monotonic()
                    status('Downloading the official RPCS3 build: %d / %d MB' % (done >> 20, expected_size >> 20))
    except (OSError, urllib.error.URLError) as e:
        raise ImportError('Could not download RPCS3 from GitHub (%s). Check the internet connection, or start '
                          'with --rpcs3 /path/to/%s.' % (e, url.rsplit('/', 1)[-1]))
    if done != expected_size or value.hexdigest() != expected_sha256:
        dest.unlink()
        raise ImportError('The downloaded RPCS3 file does not match the expected build; it was deleted.')


# Bump when the local build recipe changes, so existing runners are rebuilt.
BUILD_RECIPE = 3
# Peak memory of one compiler job on the largest generated PPU chunk, rounded up.
BUILD_JOB_MEMORY = 2 * 1024**3


def place_profiles(source, dest, sdk):
    """Copy the shipped GCC profiles for this build.

    Profiles are named after each object's path. Objects of sources inside the
    port tree are named relative to the build directory, but the few SDK
    sources compiled into the game keep the SDK's absolute path, which differs
    here: rename those from the training machine's SDK path to this one."""
    shutil.copytree(source, dest)
    trained = json.loads((dest / 'profile.json').read_text()).get('sdk_dir', '')
    if trained:
        old, new = trained.replace('/', '#'), str(sdk).replace('/', '#')
        for f in dest.glob('*.gcda'):
            if old in f.name:
                f.rename(f.with_name(f.name.replace(old, new)))
    return dest


# Display settings the launcher offers, passed to the game's window
# (vulkan_bridge.c: PORT_DISPLAY_MODE, PORT_DISPLAY_SIZE, PORT_DISPLAY_FILTER,
# and PORT_RENDER_SCALE for the internal resolution).
DISPLAY_MODES = ('windowed', 'borderless', 'fullscreen')
DISPLAY_FILTERS = ('fsr', 'linear')
RENDER_SCALES = ('1', '2', '3', '4')


# Keyboard and mouse controls, in the order the launcher lists them, with
# the defaults input_bridge.c uses. Each value is a list of SDL key names or
# Mouse Left/Middle/Right/X1/X2; the launcher writes them to controls.cfg.
CONTROLS = (
    ('move_up', 'Move forward', 'W'), ('move_down', 'Move back', 'S'),
    ('move_left', 'Move left', 'A'), ('move_right', 'Move right', 'D'),
    ('square', '\u25a1 Square (normal attack)', 'Mouse Left, J'),
    ('triangle', '\u25b3 Triangle (special move)', 'Mouse Right, I'),
    ('circle', '\u25cb Circle (special move, confirm)', 'Mouse Middle, L, Return, Keypad Enter'),
    ('cross', '\u00d7 Cross (jump, back)', 'Space, K, Backspace'),
    ('l1', 'L1', 'Q'), ('r1', 'R1 (transform)', 'E'),
    ('l2', 'L2', 'Left Shift'), ('r2', 'R2 (super special)', 'R'),
    ('l3', 'L3', 'V'), ('r3', 'R3', 'C'),
    ('up', 'D-pad up', 'Up'), ('down', 'D-pad down', 'Down'),
    ('left', 'D-pad left', 'Left'), ('right', 'D-pad right', 'Right'),
    ('start', 'START (pause)', 'Escape'), ('select', 'SELECT', 'Tab'),
    ('camera_up', 'Camera up (keys)', ''), ('camera_down', 'Camera down (keys)', ''),
    ('camera_left', 'Camera left (keys)', ''), ('camera_right', 'Camera right (keys)', ''),
)
CONTROL_NAMES = {name for name, _, _ in CONTROLS}

# Controller buttons (input_bridge.c's names, SDL's positional layout) and the
# PS3 button each one is read as by default; '' leaves a PS3 button unbound.
PAD_BUTTONS = (
    ('A', 'A / Cross (bottom)'), ('B', 'B / Circle (right)'), ('X', 'X / Square (left)'),
    ('Y', 'Y / Triangle (top)'), ('LB', 'LB / L1'), ('RB', 'RB / R1'), ('LT', 'LT / L2'), ('RT', 'RT / R2'),
    ('L3', 'Left stick press'), ('R3', 'Right stick press'), ('Start', 'Start / Options'),
    ('Back', 'Back / Share / Select'), ('Guide', 'Guide / PS / Home'),
    ('Up', 'D-pad up'), ('Down', 'D-pad down'), ('Left', 'D-pad left'), ('Right', 'D-pad right'),
    ('Misc', 'Capture / Mute / Share (extra)'), ('Touchpad', 'Touchpad press'),
    ('Paddle1', 'Paddle 1'), ('Paddle2', 'Paddle 2'), ('Paddle3', 'Paddle 3'), ('Paddle4', 'Paddle 4'),
    ('', 'Not set'),
)
PAD_CONTROLS = (
    ('pad_cross', '\u00d7 Cross', 'A'), ('pad_circle', '\u25cb Circle', 'B'),
    ('pad_square', '\u25a1 Square', 'X'), ('pad_triangle', '\u25b3 Triangle', 'Y'),
    ('pad_l1', 'L1', 'LB'), ('pad_r1', 'R1', 'RB'), ('pad_l2', 'L2', 'LT'), ('pad_r2', 'R2', 'RT'),
    ('pad_l3', 'L3', 'L3'), ('pad_r3', 'R3', 'R3'), ('pad_start', 'START', 'Start'), ('pad_select', 'SELECT', 'Back'),
    ('pad_up', 'D-pad up', 'Up'), ('pad_down', 'D-pad down', 'Down'),
    ('pad_left', 'D-pad left', 'Left'), ('pad_right', 'D-pad right', 'Right'),
)
STICK_DEADZONE = 0.15


def binding_ok(key):
    """One key or mouse button name that controls.cfg can carry."""
    return 0 < len(key) <= 32 and not any(c in key for c in ',\n\r#') and key == key.strip()


def controls_text(controls):
    """controls.cfg for {'bindings': {name: [keys]}, 'mouse_sensitivity', 'invert_y',
    'pad': {name: button}, 'stick_deadzone'}."""
    bindings = controls.get('bindings', {})
    out = ['# Battride War Port keyboard and mouse controls, written by the launcher.']
    for name, _, default in CONTROLS:
        keys = bindings.get(name)
        keys = [k for k in keys if binding_ok(k)] if isinstance(keys, list) else [k.strip() for k in default.split(',') if k]
        out.append('%s = %s' % (name, ', '.join(keys)))
    try:
        sens = min(max(float(controls.get('mouse_sensitivity', 1.0)), 0.1), 10.0)
    except (TypeError, ValueError):
        sens = 1.0
    out.append('mouse_sensitivity = %.2f' % sens)
    out.append('invert_y = %d' % (1 if controls.get('invert_y') else 0))
    pad = controls.get('pad') if isinstance(controls.get('pad'), dict) else {}
    buttons = {key for key, _ in PAD_BUTTONS}
    for name, _, default in PAD_CONTROLS:
        out.append('%s = %s' % (name, pad[name] if pad.get(name) in buttons else default))
    try:
        deadzone = min(max(float(controls.get('stick_deadzone', STICK_DEADZONE)), 0.0), 0.5)
    except (TypeError, ValueError):
        deadzone = STICK_DEADZONE
    out.append('stick_deadzone = %.2f' % deadzone)
    return '\n'.join(out) + '\n'


def display_env(display):
    """Environment for a {'mode', 'size', 'filter', 'scale'} choice; unknown values are dropped."""
    env = {}
    if display.get('mode') in DISPLAY_MODES:
        env['PORT_DISPLAY_MODE'] = display['mode']
    size = str(display.get('size', ''))
    if re.fullmatch(r'[1-9][0-9]{2,4}x[1-9][0-9]{2,4}', size):
        env['PORT_DISPLAY_SIZE'] = size
    if display.get('filter') in DISPLAY_FILTERS:
        env['PORT_DISPLAY_FILTER'] = display['filter']
    if str(display.get('scale', '')) in RENDER_SCALES:
        env['PORT_RENDER_SCALE'] = str(display['scale'])
    return env


def cpu_identity():
    """The runner is built with -march=native: rebuild it if the data folder moves to another CPU."""
    model, flags = '', ''
    try:
        for line in Path('/proc/cpuinfo').read_text().splitlines():
            if line.startswith('model name') and not model:
                model = line.split(':', 1)[1].strip()
            elif line.startswith('flags') and not flags:
                flags = ' '.join(sorted(line.split(':', 1)[1].split()))
    except OSError:
        pass
    return {'model': model, 'flags_sha256': hashlib.sha256(flags.encode()).hexdigest()}


def build_jobs():
    cpus = len(os.sched_getaffinity(0))
    try:
        available = int(re.search(r'MemAvailable:\s+(\d+) kB', Path('/proc/meminfo').read_text())[1]) * 1024
    except (OSError, TypeError, ValueError):
        available = 4 * 1024**3
    return max(1, min(cpus, (available - 1024**3) // BUILD_JOB_MEMORY))


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

    def run(self, args, env=None, cwd=None, log=None, capture=False, on_line=None):
        """Run a tool in its own session; on_line receives each output line (also logged)."""
        if self.cancelled.is_set():
            raise ImportError('Operation cancelled')
        p = subprocess.Popen([str(x) for x in args], env=env, cwd=cwd,
                             stdout=subprocess.PIPE if capture or on_line else (log or subprocess.DEVNULL),
                             stderr=subprocess.STDOUT, start_new_session=True)
        with self.lock:
            self.current = p
        if self.cancelled.is_set():
            self.stop()
        try:
            output = None
            if on_line:
                for raw in p.stdout:
                    if log:
                        log.write(raw)
                    on_line(raw.decode('utf-8', errors='replace').rstrip())
                if log:
                    log.flush()
            elif capture:
                output = p.communicate()[0]
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
        return [self.root / 'usr/bin' / name, *args]

    def helper_env(self, stage):
        # RPCS3's own AppRun sets up its libraries (and its checkrt C++ runtime
        # on older hosts); nothing of this AppImage's environment may leak in.
        env = os.environ.copy()
        for key in list(env):
            if key.startswith(('APPIMAGE', 'PYTHON', 'GI_', 'GTK_', 'GDK_', 'QT_')) or key in (
                    'APPDIR', 'LD_LIBRARY_PATH', 'LD_PRELOAD', 'GIO_MODULE_DIR', 'GSETTINGS_SCHEMA_DIR', 'MANGOHUD'):
                env.pop(key, None)
        env.update(XDG_CONFIG_HOME=str(stage / 'rpcs3-config'),
                   XDG_CACHE_HOME=str(stage / 'rpcs3-cache'), XDG_DATA_HOME=str(stage / 'rpcs3-data'))
        return env

    def rpcs3_helper(self, data, runner, status=lambda _: None, local=None, log=None):
        """The official RPCS3 build pinned in rpcs3.json, extracted once into the data folder.

        RPCS3 is not redistributed with this AppImage: it is downloaded from the
        RPCS3 project's own release, or taken from a copy the user already has.
        """
        info = self.meta['rpcs3']
        base = Path(data) / 'tools' / ('rpcs3-' + info['version'])
        apprun = base / 'squashfs-root/AppRun'
        if apprun.is_file() and (base / 'verified').is_file():
            return apprun
        shutil.rmtree(base, ignore_errors=True)
        base.mkdir(parents=True)
        image = base / info['file']
        candidates = [Path(local)] if local else []
        candidates += [Path(os.environ.get('XDG_DOWNLOAD_DIR', Path.home() / 'Downloads')) / info['file'],
                       Path.home() / 'Downloads' / info['file']]
        for candidate in candidates:
            if candidate.is_file() and candidate.stat().st_size == info['size'] and digest(candidate) == info['sha256']:
                status('Using your RPCS3 copy: ' + str(candidate))
                shutil.copy2(candidate, image)
                break
        else:
            if local:
                raise ImportError('The selected RPCS3 file is not the expected build ' + info['file'])
            status('Downloading the official RPCS3 build (%d MB) from GitHub...' % (info['size'] >> 20))
            download(info['url'], image, info['sha256'], info['size'], runner.cancelled, status)
        image.chmod(0o755)
        status('Unpacking RPCS3...')
        # --appimage-extract needs no FUSE.
        code, _ = runner.run([image, '--appimage-extract'], cwd=base, log=log)
        image.unlink()
        if code or not apprun.is_file():
            raise ImportError('RPCS3 could not be unpacked. See import.log.')
        (base / 'verified').write_text(info['sha256'] + '\n')
        return apprun

    def rpcs3(self, apprun, *args):
        return [apprun, '--allow-any-location', '--headless', *args]

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

    def import_iso(self, iso, data, runner, status=lambda _: None, log=None, rpcs3=None):
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
            # Only a disc that passed the listing checks is worth fetching RPCS3 for.
            apprun = self.rpcs3_helper(data, runner, status, rpcs3, log)
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
            runner.run(self.rpcs3(apprun, '--decrypt', game / 'PS3_GAME/USRDIR/EBOOT.BIN'),
                       env=self.helper_env(stage), log=log)
            elf = game / 'PS3_GAME/USRDIR/EBOOT.elf'
            if not elf.is_file() or digest(elf) != self.meta['elf_sha256']:
                raise ImportError('EBOOT could not be prepared or does not match this port.')
            elf.rename(game / 'EBOOT.ELF')
            status('Extracting audio codecs from your disc firmware...')
            runner.run(self.rpcs3(apprun, '--installfw', game / pup), env=self.helper_env(stage), log=log)
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
            # RPCS3 was only needed for the EBOOT and the codecs.
            shutil.rmtree(apprun.parent.parent, ignore_errors=True)
            try:
                (data / 'tools').rmdir()
            except OSError:
                pass
            return data / 'game'
        except BaseException:
            for p in committed:
                shutil.rmtree(p)
            raise
        finally:
            shutil.rmtree(stage, ignore_errors=True)

    def build_env(self, data):
        """Environment for translating and compiling with the bundled toolchain only.

        No LD_LIBRARY_PATH: the bundled tools find their libraries through their
        own RPATH, and host programs the build starts (ninja runs /bin/sh) must
        keep using the host's libraries.
        """
        env = os.environ.copy()
        for key in list(env):
            if key.startswith(('APPIMAGE', 'PYTHON', 'GI_', 'GTK_', 'GDK_', 'QT_', 'CMAKE_', 'PKG_CONFIG',
                               'NINJA', 'CCACHE', 'DISTCC')) or key in (
                    'APPDIR', 'LD_LIBRARY_PATH', 'LD_PRELOAD', 'LD_RUN_PATH', 'CC', 'CXX', 'CPP', 'CFLAGS',
                    'CXXFLAGS', 'CPPFLAGS', 'LDFLAGS', 'CPATH', 'C_INCLUDE_PATH', 'CPLUS_INCLUDE_PATH',
                    'LIBRARY_PATH', 'GCC_EXEC_PREFIX', 'COMPILER_PATH', 'MAKEFLAGS', 'PS3_DEV_FLASH'):
                env.pop(key, None)
        toolchain = self.root / 'usr/toolchain'
        env['PATH'] = os.pathsep.join([str(toolchain / 'sysroot/usr/bin'), str(self.root / 'usr/bin'),
                                       env.get('PATH', '/usr/bin:/bin')])
        env.update(PYTHONHOME=str(self.root / 'usr'), PYTHONPLATLIBDIR='lib', PYTHONDONTWRITEBYTECODE='1',
                   LC_ALL='C.UTF-8', PS3_DEV_FLASH=str(Path(data) / 'firmware/dev_flash'))
        return env

    def profiles(self):
        """GCC profiles shipped for this game and this toolchain, or None.

        They are execution counts recorded by running the translated code
        (scripts/pgo_train.py), applied when compiling it on this computer."""
        path = self.root / 'usr/share/battride/pgo'
        try:
            info = json.loads((path / 'profile.json').read_text())
        except (OSError, ValueError):
            return None
        if info.get('sdk_commit') != self.meta['sdk_commit'] or info.get('eboot_sha256') != self.meta['elf_sha256']:
            return None
        return path

    def sources_sha256(self):
        """The port sources this AppImage builds, so a rebuilt AppImage of the same version rebuilds the game."""
        if not hasattr(self, '_sources_sha256'):
            h = hashlib.sha256()
            port = self.root / 'usr/share/battride/port'
            for f in sorted(p for p in port.rglob('*') if p.is_file()) if port.is_dir() else ():
                h.update(str(f.relative_to(port)).encode() + b'\0' + f.read_bytes() + b'\0')
            self._sources_sha256 = h.hexdigest()
        return self._sources_sha256

    def build_identity(self):
        return {'recipe': BUILD_RECIPE, 'package': self.meta['version'], 'sdk': self.meta['sdk_commit'],
                'elf_sha256': self.meta['elf_sha256'], 'sources': self.sources_sha256(), 'cpu': cpu_identity(),
                'pgo': self.profiles() is not None}

    def built_runner(self, data):
        """The game built on this computer, or None when it must be (re)built."""
        out = Path(data) / 'runner'
        try:
            if json.loads((out / 'build.json').read_text()) == self.build_identity() and (out / 'game-runner').is_file():
                return out / 'game-runner'
        except (OSError, ValueError):
            pass
        return None

    def build_runner(self, data, runner, status=lambda _: None, log=None):
        """Translate the imported EBOOT and compile the game for this CPU.

        Nothing from the game is shipped: the PPU/SPU sources are generated
        from the user's own disc and compiled here with the bundled toolchain,
        guided by the shipped GCC profiles when they match.
        """
        data = Path(data).resolve()
        existing = self.built_runner(data)
        if existing:
            status('Using the game already built on this computer')
            return existing
        if shutil.disk_usage(data).free < 4 * 1024**3:
            raise ImportError('Building the game needs about 4 GB of free space in the data folder.')
        jobs = build_jobs()
        python = self.root / 'usr/bin/python3'
        sdk = self.root / 'usr/share/battride/ps3recomp'
        env = self.build_env(data)
        work = data / ('.build-' + uuid.uuid4().hex)
        try:
            port = work / 'port'
            shutil.copytree(self.root / 'usr/share/battride/port', port)
            (port / 'game').mkdir(exist_ok=True)
            try:
                os.link(data / 'game/EBOOT.ELF', port / 'game/EBOOT.ELF')
            except OSError:
                shutil.copy2(data / 'game/EBOOT.ELF', port / 'game/EBOOT.ELF')
            status('Step 1 of 2: translating the game code from your EBOOT. This takes a few minutes...')
            code, _ = runner.run([python, port / 'scripts/generate.py', '--sdk', sdk, '--jobs', jobs],
                                 cwd=port, env=env, log=log, on_line=lambda _: None)
            if code:
                raise ImportError('Translating the game code failed. See build.log.')
            build = work / 'build'
            profiles = self.profiles()
            if profiles:
                profiles = place_profiles(profiles, work / 'pgo', sdk)
            lines = []
            code, _ = runner.run([self.root / 'usr/toolchain/sysroot/usr/bin/cmake', '-S', port, '-B', build,
                                  '-G', 'Ninja', '-DCMAKE_TOOLCHAIN_FILE=' + str(self.root / 'usr/toolchain/toolchain.cmake'),
                                  '-DCMAKE_BUILD_TYPE=Debug', '-DCMAKE_C_FLAGS_DEBUG=-O2', '-DCMAKE_CXX_FLAGS_DEBUG=-O2',
                                  '-DPORT_ENABLE_SPU=ON', '-DPS3RECOMP_RSX_VULKAN=ON', '-DPORT_MARCH=native',
                                  '-DPORT_PORTABLE=ON', '-DPS3RECOMP_DIR=' + str(sdk),
                                  '-DPython3_EXECUTABLE=' + str(python),
                                  '-Dglslang_DIR=' + str(port / 'packaging/glslang-compat'),
                                  *(['-DPORT_PGO=use', '-DPORT_PGO_DIR=' + str(profiles)] if profiles else [])],
                                 env=env, log=log, on_line=lines.append)
            if code:
                raise ImportError('Configuring the game build failed. See build.log.')
            if not any('guest programs available' in line for line in lines):
                raise ImportError('The bundled shader compiler was not found by the build. See build.log.')
            progress = re.compile(r'^\[(\d+)/(\d+)\]')
            shown = [0.0]
            def compiled(line):
                match = progress.match(line)
                if match and time.monotonic() - shown[0] > 1:
                    shown[0] = time.monotonic()
                    status('Step 2 of 2: compiling the game for this CPU (%d jobs): %s / %s files'
                           % (jobs, match[1], match[2]))
            status('Step 2 of 2: compiling the game for this CPU (%d jobs). This takes 15-60 minutes...' % jobs)
            code, _ = runner.run([self.root / 'usr/toolchain/sysroot/usr/bin/cmake', '--build', build, '-j', jobs],
                                 env=env, log=log, on_line=compiled)
            if code:
                raise ImportError('Compiling the game failed. See build.log.')
            out = data / 'runner'
            shutil.rmtree(out / 'lib', ignore_errors=True)
            (out / 'lib').mkdir(parents=True)
            for name in self.meta['game_libs']:
                shutil.copy2(self.root / 'usr/lib' / name, out / 'lib' / name)
            tmp = out / 'game-runner.tmp'
            shutil.copy2(build / 'kamenriderbattridewarsport', tmp)
            # The game finds SDL2 and its bundled libraries in lib/ next to it.
            # Set exactly this DT_RPATH (inherited by SDL2's own dependencies);
            # CMake's build RPATH would add an empty entry, i.e. the current directory.
            code, _ = runner.run([self.root / 'usr/toolchain/sysroot/usr/bin/patchelf', '--force-rpath',
                                  '--set-rpath', '$ORIGIN/lib', tmp], env=env, log=log)
            if code:
                raise ImportError('Could not finish the game executable. See build.log.')
            tmp.replace(out / 'game-runner')
            (out / 'build.json').write_text(json.dumps(self.build_identity(), indent=2))
            status('Game built for this computer.')
            return out / 'game-runner'
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def game_env(self, data, logs, mangohud=False, display=None, controls=None):
        env = os.environ.copy()
        # Keep developer diagnostics and automated controller input out of the
        # portable player's launch, even if inherited from a build terminal.
        for k in list(env):
            if k.startswith(('PAD_', 'PORT_', 'PPU_', 'SPU_', 'YDKJ_', 'GCM_', 'RSX_')) or k in (
                    'LD_LIBRARY_PATH', 'LD_PRELOAD', 'PS3_VFS_ROOT', 'PS3_GAMEDATA_ROOT', 'PS3_DEV_FLASH'):
                env.pop(k, None)
        # The game finds its libraries through its RPATH (runner/lib).
        env.setdefault('VK_LOADER_DEBUG', 'error,warn')
        env.update(PS3_VFS_ROOT=str(data / 'game'), PS3_GAMEDATA_ROOT=str(data / 'gamedata'),
                   PS3_DEV_FLASH=str(data / 'firmware/dev_flash'), PS3RECOMP_VK_GUEST_PROGRAMS='1',
                   PS3RECOMP_VK_WINDOW='1', PORT_GCM_EXPAND_BUFFERS='0',
                   PORT_FRAME_TIMES=str(logs / 'frames.csv'))
        env.update(display_env(display or {}))
        if controls is not None:
            path = Path(data) / 'controls.cfg'
            path.write_text(controls_text(controls))
            env['PORT_CONTROLS'] = str(path)
        # Mappings for controllers newer than the bundled SDL.
        db = self.root / 'usr/share/battride/port/third_party/SDL_GameControllerDB/gamecontrollerdb.txt'
        if db.is_file():
            env['PORT_CONTROLLER_DB'] = str(db)
        if mangohud:
            env.update(MANGOHUD='1', MANGOHUD_CONFIG='fps,frametime,frame_timing,cpu_stats,gpu_stats,ram,vram')
        else:
            env.pop('MANGOHUD', None)
        return env
