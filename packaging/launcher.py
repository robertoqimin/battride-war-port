#!/usr/bin/env python3
"""Small desktop launcher: imports the user's disc and builds the game on this computer."""
import argparse
import json
import os
from pathlib import Path
import sys
import threading
import time

from importer import ImportError, Package, Runner

ROOT = Path(os.environ.get('PORT_APPDIR', Path(__file__).resolve().parents[1]))


def cpu_check():
    flags = set()
    try:
        for line in Path('/proc/cpuinfo').read_text().splitlines():
            if line.startswith('flags'):
                flags = set(line.split(':', 1)[1].split())
                break
    except OSError:
        pass
    # The game is compiled for the local CPU; the SPU code needs SSE4.1.
    missing = {'ssse3', 'sse4_1'} - flags
    if missing:
        raise ImportError('This game needs an x86_64 CPU with SSE4.1. Missing: ' + ', '.join(sorted(missing)))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--import-only', type=Path, metavar='ISO')
    ap.add_argument('--data-dir', type=Path)
    ap.add_argument('--screenshot', type=Path, help=argparse.SUPPRESS)
    args = ap.parse_args()
    package = Package(ROOT)
    if args.check:
        cpu_check()
        for tool in ('7z', 'ffmpeg', 'ffprobe'):
            if not (ROOT / 'usr/bin' / tool).is_file():
                raise ImportError('Missing bundled tool: ' + tool)
        code, formats = Runner().run(package.tool('7z', 'i'), capture=True)
        if code or 'Codec Load Error' in formats or 'Udf' not in formats:
            raise ImportError('Bundled ISO reader is missing UDF format support.')
        env = package.build_env(Path.home())
        compilers = {}
        for name, tool in (('c', 'usr/lib/llvm-14/bin/clang'), ('cxx', 'usr/bin/x86_64-linux-gnu-g++-11'),
                           ('cmake', 'usr/bin/cmake'), ('ninja', 'usr/bin/ninja')):
            code, text = Runner().run([ROOT / 'usr/toolchain/sysroot' / tool, '--version'], env=env, capture=True)
            if code:
                raise ImportError('Bundled build tool does not start: ' + name + '\n' + text[-800:])
            compilers[name] = text.splitlines()[0] if text else ''
        print(json.dumps({'status': 'OK', 'title_id': 'BLJS10220', 'files': len(package.manifest),
                          'cpu': 'built locally with -march=native (SSE4.1 minimum)', 'toolchain': compilers,
                          'elf_sha256': package.meta['elf_sha256']}, indent=2))
        return
    default_data = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'battride-war-port'
    data = (args.data_dir or default_data).resolve()
    if args.import_only:
        data.mkdir(parents=True, exist_ok=True)
        runner = Runner()
        with (data / 'import.log').open('wb') as log:
            package.import_iso(args.import_only, data, runner, print, log)
        print('Import verified:', data)
        with (data / 'build.log').open('wb') as log:
            print('Game built:', package.build_runner(data, runner, print, log))
        return
    import gi
    gi.require_version('Gtk', '3.0')
    from gi.repository import Gtk, GLib

    config_path = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'battride-war-port/settings.json'
    try:
        saved = json.loads(config_path.read_text())
    except (OSError, ValueError):
        saved = {}
    if not args.data_dir and saved.get('data'):
        data = Path(saved['data'])

    class Window:
        def __init__(self):
            self.closed = False
            self.runner = None
            self.playing = False
            self.log_dir = None
            self.window = Gtk.OffscreenWindow() if args.screenshot else Gtk.Window(title='Battride War Port')
            self.window.set_default_size(740, 400)
            self.window.set_border_width(24)
            self.window.connect('delete-event', self.close)
            self.window.connect('destroy', Gtk.main_quit)
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
            self.window.add(box)
            title = Gtk.Label(xalign=0)
            title.set_markup('<span size="x-large" weight="bold">Kamen Rider: Battride War</span>')
            box.pack_start(title, False, False, 0)
            subtitle = Gtk.Label(label='Experimental Linux port  •  Japan / BLJS10220', xalign=0)
            box.pack_start(subtitle, False, False, 0)
            note = Gtk.Label(label='Select your game ISO. The first launch imports its files and builds the game\nfor this computer from your disc (15-60 minutes, once). Data, saves and logs stay in the data folder.', xalign=0)
            note.set_line_wrap(True)
            box.pack_start(note, False, False, 0)
            grid = Gtk.Grid(column_spacing=16, row_spacing=12)
            box.pack_start(grid, False, False, 4)
            grid.attach(Gtk.Label(label='Game ISO', xalign=0), 0, 0, 1, 1)
            self.iso = Gtk.FileChooserButton(title='Select the game ISO', action=Gtk.FileChooserAction.OPEN)
            filt = Gtk.FileFilter(); filt.set_name('Disc image (*.iso)'); filt.add_pattern('*.iso'); filt.add_pattern('*.ISO')
            self.iso.add_filter(filt);self.iso.set_hexpand(True)
            if saved.get('iso') and Path(saved['iso']).is_file():
                self.iso.set_filename(saved['iso'])
            grid.attach(self.iso, 1, 0, 1, 1)
            grid.attach(Gtk.Label(label='Data folder', xalign=0), 0, 1, 1, 1)
            self.data = Gtk.Entry(text=str(data));self.data.set_hexpand(True)
            grid.attach(self.data, 1, 1, 1, 1)
            self.hud = Gtk.CheckButton(label='Enable MangoHud (if installed on this PC)')
            box.pack_start(self.hud, False, False, 0)
            actions = Gtk.Box(spacing=10)
            self.start = Gtk.Button(label='Import ISO & Play');self.start.connect('clicked', self.begin)
            self.stop = Gtk.Button(label='Stop');self.stop.set_sensitive(False);self.stop.connect('clicked', self.stop_job)
            actions.pack_start(self.start, False, False, 0);actions.pack_start(self.stop, False, False, 0)
            box.pack_start(actions, False, False, 0)
            self.progress = Gtk.ProgressBar();box.pack_start(self.progress, False, False, 0)
            self.status = Gtk.Label(label='Ready. Requires a Vulkan GPU, an SSE4.1 CPU, about 8 GB of RAM and 8 GB of free space.', xalign=0)
            self.status.set_line_wrap(True);box.pack_start(self.status, False, False, 0)
            self.stats = Gtk.Label(label='', xalign=0);box.pack_start(self.stats, False, False, 0)
            GLib.timeout_add(1000, self.tick)
            self.window.show_all()

        def message(self, text):
            def apply():
                if not self.closed:
                    self.status.set_text(text)
                return False
            GLib.idle_add(apply)

        def sensitive(self, enabled):
            def apply():
                if self.closed:
                    return False
                for widget in (self.iso, self.data, self.hud, self.start):widget.set_sensitive(enabled)
                self.stop.set_sensitive(not enabled)
                if enabled:self.progress.set_fraction(0)
                return False
            GLib.idle_add(apply)

        def begin(self, _):
            iso = self.iso.get_filename()
            if not iso:
                self.status.set_text('Choose the game ISO first.')
                return
            try:
                cpu_check()
                dest = Path(self.data.get_text()).expanduser().resolve()
                dest.mkdir(parents=True, exist_ok=True)
            except (OSError, ImportError) as e:
                self.status.set_text(str(e));return
            self.sensitive(False)
            self.runner = Runner()
            hud = self.hud.get_active()
            self.log_dir = dest / 'logs' / (time.strftime('%Y%m%d-%H%M%S') + '-' + str(os.getpid()))
            self.log_dir.mkdir(parents=True, exist_ok=False)
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(json.dumps({'iso': iso, 'data': str(dest)}, indent=2))
            def worker():
                try:
                    with (self.log_dir / 'import.log').open('wb') as log:
                        package.import_iso(iso, dest, self.runner, self.message, log)
                    with (self.log_dir / 'build.log').open('wb') as log:
                        game = package.build_runner(dest, self.runner, self.message, log)
                    self.message('Checking Vulkan driver and window support...')
                    code, details = self.runner.run(package.tool('graphics-probe'),
                                                    env=package.game_env(dest, self.log_dir), capture=True)
                    (self.log_dir / 'graphics.log').write_text(details)
                    if code:
                        raise ImportError('Vulkan/window check failed. See graphics.log: ' + details[-1800:])
                    self.playing = True
                    self.message('Starting game. Logs: ' + str(self.log_dir))
                    with (self.log_dir / 'game.log').open('wb') as log:
                        code, _ = self.runner.run([game, dest / 'game/EBOOT.ELF'],
                                                  cwd=dest, env=package.game_env(dest, self.log_dir, hud), log=log)
                    self.message('Game closed.' if code == 0 else 'Game exited (%d). Logs: %s' % (code, self.log_dir))
                except (OSError, ImportError, ValueError) as e:
                    self.message(str(e) + '\nLogs: ' + str(self.log_dir))
                finally:
                    self.playing = False
                    self.sensitive(True)
            threading.Thread(target=worker, daemon=False).start()

        def stop_job(self, _):
            if self.runner:
                self.message('Stopping...')
                threading.Thread(target=self.runner.stop, daemon=True).start()

        def close(self, *_):
            self.closed = True
            if self.runner:self.runner.stop()
            return False

        def tick(self):
            if self.closed:return False
            if self.runner and not self.start.get_sensitive():self.progress.pulse()
            if self.playing and self.log_dir:
                try:
                    with (self.log_dir / 'game.log').open('rb') as boot:
                        startup = boot.read(16384).decode(errors='replace')
                    if '[rsx] Vulkan backend init OK -- window open' in startup:
                        self.status.set_text('Game window opened. Use your controller or keyboard. Logs: ' + str(self.log_dir))
                    elif '[rsx] Vulkan backend init FAILED' in startup:
                        self.status.set_text('Game Vulkan startup failed. Stop the game and send game.log from: ' + str(self.log_dir))
                except OSError:
                    pass
                try:
                    with (self.log_dir / 'frames.csv').open('rb') as f:
                        f.seek(0, 2);size=f.tell();f.seek(max(0, size-32768));lines=f.read().decode().splitlines()[1:]
                    values=[float(x.split(',')[2]) for x in lines[-120:] if len(x.split(','))==3]
                    values=[x for x in values if x>0]
                    if values:
                        ordered=sorted(values);self.stats.set_text('Recent guest frames: %.1f FPS  |  p95 %.1f ms' %
                            (1000*len(values)/sum(values),ordered[min(len(ordered)-1,int(len(ordered)*.95))]))
                except (OSError, ValueError):pass
            return True

    ui = Window()
    if args.screenshot:
        def shot():
            pixbuf = ui.window.get_pixbuf()
            pixbuf.savev(str(args.screenshot), 'png', [], [])
            ui.closed = True;Gtk.main_quit();return False
        GLib.timeout_add(500, shot)
    Gtk.main()


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, ImportError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
