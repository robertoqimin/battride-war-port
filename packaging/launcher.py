#!/usr/bin/env python3
"""Small desktop launcher: imports the user's disc and builds the game on this computer."""
import argparse
import json
import os
from pathlib import Path
import re
import sys
import threading
import time

from importer import CONTROLS, DISPLAY_FILTERS, DISPLAY_MODES, RENDER_SCALES, ImportError, Package, Runner, binding_ok

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
    ap.add_argument('--rpcs3', type=Path, metavar='APPIMAGE',
                    help='use this copy of the pinned RPCS3 AppImage instead of downloading it')
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
            package.import_iso(args.import_only, data, runner, print, log, args.rpcs3)
        print('Import verified:', data)
        with (data / 'build.log').open('wb') as log:
            print('Game built:', package.build_runner(data, runner, print, log))
        return
    import gi
    gi.require_version('Gtk', '3.0')
    from gi.repository import Gtk, GLib, Gdk

    config_path = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'battride-war-port/settings.json'
    try:
        saved = json.loads(config_path.read_text())
    except (OSError, ValueError):
        saved = {}
    if not args.data_dir and saved.get('data'):
        data = Path(saved['data'])

    def display_sizes():
        """Common 16:9 sizes that fit the largest connected monitor (in device pixels)."""
        largest = (1920, 1080)
        screen = Gdk.Display.get_default()
        if screen:
            for i in range(screen.get_n_monitors()):
                monitor = screen.get_monitor(i)
                g, scale = monitor.get_geometry(), monitor.get_scale_factor()
                if g.width * g.height * scale * scale > largest[0] * largest[1]:
                    largest = (g.width * scale, g.height * scale)
        sizes = [(1280, 720), (1600, 900), (1920, 1080), (2560, 1440), (3200, 1800), (3840, 2160)]
        return ['%dx%d' % (w, h) for w, h in sizes if (w, h) == (1280, 720) or (w <= largest[0] and h <= largest[1])]

    # GDK key names that differ from SDL's (input_bridge.c resolves SDL names).
    SDL_KEYS = {'space': 'Space', 'Return': 'Return', 'KP_Enter': 'Keypad Enter', 'BackSpace': 'Backspace',
                'Escape': 'Escape', 'Tab': 'Tab', 'ISO_Left_Tab': 'Tab', 'Shift_L': 'Left Shift',
                'Shift_R': 'Right Shift', 'Control_L': 'Left Ctrl', 'Control_R': 'Right Ctrl',
                'Alt_L': 'Left Alt', 'Alt_R': 'Right Alt', 'Super_L': 'Left GUI', 'Super_R': 'Right GUI',
                'Up': 'Up', 'Down': 'Down', 'Left': 'Left', 'Right': 'Right', 'Insert': 'Insert',
                'Delete': 'Delete', 'Home': 'Home', 'End': 'End', 'Page_Up': 'PageUp', 'Page_Down': 'PageDown',
                'Caps_Lock': 'CapsLock', 'KP_Add': 'Keypad +', 'KP_Subtract': 'Keypad -',
                'KP_Multiply': 'Keypad *', 'KP_Divide': 'Keypad /', 'KP_Decimal': 'Keypad .'}
    SDL_MOUSE = {1: 'Mouse Left', 2: 'Mouse Middle', 3: 'Mouse Right', 8: 'Mouse X1', 9: 'Mouse X2'}

    def sdl_key_name(event):
        """The SDL name of the key pressed, ignoring Shift and other modifiers; None if unusable."""
        keymap = Gdk.Keymap.get_for_display(Gdk.Display.get_default())
        found, keyval, _, _, _ = keymap.translate_keyboard_state(event.hardware_keycode, 0, event.group)
        name = Gdk.keyval_name(keyval if found else event.keyval) or ''
        if name in SDL_KEYS:
            return SDL_KEYS[name]
        if name.startswith('KP_') and name[3:].isdigit():
            return 'Keypad ' + name[3:]
        if len(name) <= 3 and name[:1] == 'F' and name[1:].isdigit():
            return name
        code = Gdk.keyval_to_unicode(keyval)
        char = chr(code).upper() if code else ''
        return char if char.isprintable() and binding_ok(char) and char != ' ' else None

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
            note = Gtk.Label(label='Select your game ISO. The first launch downloads the official RPCS3 build to read your disc,\nimports its files and builds the game for this computer (15-60 minutes, once). Data, saves and logs stay in the data folder.', xalign=0)
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
            display = saved.get('display', {})
            grid.attach(Gtk.Label(label='Display', xalign=0), 0, 2, 1, 1)
            row = Gtk.Box(spacing=10)
            self.mode = Gtk.ComboBoxText()
            for key, label in (('windowed', 'Windowed'), ('borderless', 'Borderless fullscreen'),
                               ('fullscreen', 'Fullscreen')):
                self.mode.append(key, label)
            self.mode.set_active_id(display.get('mode') if display.get('mode') in DISPLAY_MODES else 'windowed')
            self.size = Gtk.ComboBoxText()
            for size in display_sizes():
                self.size.append(size, size.replace('x', ' × '))
            if not self.size.set_active_id(display.get('size', '')):
                self.size.set_active_id('1600x900') or self.size.set_active(0)
            self.filter = Gtk.ComboBoxText()
            self.filter.append('fsr', 'FSR 1 upscaling')
            self.filter.append('linear', 'Bilinear upscaling')
            self.filter.set_active_id(display.get('filter') if display.get('filter') in DISPLAY_FILTERS else 'fsr')
            self.mode.connect('changed', lambda _: self.size.set_sensitive(self.mode.get_active_id() != 'borderless'))
            self.size.set_sensitive(self.mode.get_active_id() != 'borderless')
            for widget in (self.mode, self.size, self.filter):
                row.pack_start(widget, False, False, 0)
            grid.attach(row, 1, 2, 1, 1)
            grid.attach(Gtk.Label(label='Rendering', xalign=0), 0, 3, 1, 1)
            self.scale = Gtk.ComboBoxText()
            for scale, label in (('1', 'Native resolution (1280 × 720)'), ('2', '2× (2560 × 1440)'),
                                 ('3', '3× (3840 × 2160)'), ('4', '4× (5120 × 2880)')):
                self.scale.append(scale, label)
            self.scale.set_active_id(str(display.get('scale')) if str(display.get('scale')) in RENDER_SCALES else '1')
            scale_row = Gtk.Box(spacing=10)
            scale_row.pack_start(self.scale, False, False, 0)
            grid.attach(scale_row, 1, 3, 1, 1)
            hint = Gtk.Label(xalign=0)
            hint.set_markup('<small>Higher internal resolutions render the game sharper and need a faster GPU. '
                            'The picture keeps 16:9; Alt+Enter or F11 switches window and fullscreen while playing.</small>')
            grid.attach(hint, 1, 4, 1, 1)
            keys = Gtk.Label(xalign=0)
            keys.set_markup('<small>Controller, or keyboard and mouse: WASD move, mouse camera (click the window; Alt releases), '
                            'left/right/middle click □/△/○, Space ×, Q/E L1/R1, Shift/R L2/R2, Enter confirm, Esc pause.</small>')
            keys.set_line_wrap(True)
            box.pack_start(keys, False, False, 0)
            self.hud = Gtk.CheckButton(label='Enable MangoHud (if installed on this PC)')
            box.pack_start(self.hud, False, False, 0)
            actions = Gtk.Box(spacing=10)
            self.start = Gtk.Button(label='Import ISO & Play');self.start.connect('clicked', self.begin)
            self.stop = Gtk.Button(label='Stop');self.stop.set_sensitive(False);self.stop.connect('clicked', self.stop_job)
            self.controls = saved.get('controls', {}) if isinstance(saved.get('controls'), dict) else {}
            self.keys_button = Gtk.Button(label='Controls…');self.keys_button.connect('clicked', self.show_controls)
            credits = Gtk.Button(label='Credits & licenses');credits.connect('clicked', self.show_credits)
            actions.pack_start(self.start, False, False, 0);actions.pack_start(self.stop, False, False, 0)
            actions.pack_end(credits, False, False, 0)
            actions.pack_end(self.keys_button, False, False, 0)
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
                for widget in (self.iso, self.data, self.hud, self.start, self.mode, self.filter, self.scale,
                               self.keys_button):widget.set_sensitive(enabled)
                self.size.set_sensitive(enabled and self.mode.get_active_id() != 'borderless')
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
            display = {'mode': self.mode.get_active_id(), 'size': self.size.get_active_id(),
                       'filter': self.filter.get_active_id(), 'scale': self.scale.get_active_id()}
            self.log_dir = dest / 'logs' / (time.strftime('%Y%m%d-%H%M%S') + '-' + str(os.getpid()))
            self.log_dir.mkdir(parents=True, exist_ok=False)
            config_path.parent.mkdir(parents=True, exist_ok=True)
            self.save_settings({'iso': iso, 'data': str(dest), 'display': display})
            def worker():
                try:
                    with (self.log_dir / 'import.log').open('wb') as log:
                        package.import_iso(iso, dest, self.runner, self.message, log, args.rpcs3)
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
                                                  cwd=dest, env=package.game_env(dest, self.log_dir, hud, display, self.controls), log=log)
                    self.message('Game closed.' if code == 0 else 'Game exited (%d). Logs: %s' % (code, self.log_dir))
                except (OSError, ImportError, ValueError) as e:
                    self.message(str(e) + '\nLogs: ' + str(self.log_dir))
                finally:
                    self.playing = False
                    self.sensitive(True)
            threading.Thread(target=worker, daemon=False).start()

        def save_settings(self, changes):
            saved.update(changes)
            saved['controls'] = self.controls
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(json.dumps(saved, indent=2))

        def show_controls(self, _):
            dialog = Gtk.Dialog(title='Keyboard and mouse controls', transient_for=self.window, modal=True)
            dialog.add_button('Reset to defaults', 1)
            dialog.add_button('Cancel', Gtk.ResponseType.CANCEL)
            dialog.add_button('Save', Gtk.ResponseType.OK)
            dialog.set_default_size(620, 680)
            stored = self.controls.get('bindings', {})
            defaults = {name: [k.strip() for k in default.split(',') if k] for name, _, default in CONTROLS}
            bindings = {name: list(stored[name]) if isinstance(stored.get(name), list) else list(defaults[name])
                        for name, _, _ in CONTROLS}
            labels = {name: label for name, label, _ in CONTROLS}
            grid = Gtk.Grid(column_spacing=8, row_spacing=6, margin=12)
            buttons = {}

            def refresh(name):
                buttons[name].set_label(', '.join(bindings[name]) or '(not set)')

            def capture(name, replace):
                cap = Gtk.Dialog(title='Press a key', transient_for=dialog, modal=True)
                cap.add_button('Cancel', Gtk.ResponseType.CANCEL)
                area = Gtk.EventBox()
                area.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
                text = Gtk.Label(label='Press a key, or click here with a mouse button, for\n' + labels[name])
                text.set_justify(Gtk.Justification.CENTER)
                area.add(text)
                area.set_size_request(420, 150)
                cap.get_content_area().pack_start(area, True, True, 0)
                got = []

                def on_key(_, event):
                    key = sdl_key_name(event)
                    if key:
                        got.append(key)
                        cap.response(Gtk.ResponseType.OK)
                    return True              # Esc is a key too: it can be bound

                def on_click(_, event):
                    if event.button in SDL_MOUSE:
                        got.append(SDL_MOUSE[event.button])
                        cap.response(Gtk.ResponseType.OK)
                    return True

                cap.connect('key-press-event', on_key)
                area.connect('button-press-event', on_click)
                cap.show_all()
                cap.run()
                cap.destroy()
                if got:
                    if replace:
                        bindings[name] = got[:1]
                    elif got[0] not in bindings[name] and len(bindings[name]) < 6:
                        bindings[name].append(got[0])
                    refresh(name)

            def clear(name):
                bindings[name] = []
                refresh(name)

            for row, (name, label, _) in enumerate(CONTROLS):
                grid.attach(Gtk.Label(label=label, xalign=0), 0, row, 1, 1)
                buttons[name] = Gtk.Button()
                buttons[name].set_hexpand(True)
                buttons[name].set_tooltip_text('Click, then press the key or mouse button to use')
                buttons[name].connect('clicked', lambda _, n=name: capture(n, True))
                refresh(name)
                add = Gtk.Button(label='+')
                add.set_tooltip_text('Add another key')
                add.connect('clicked', lambda _, n=name: capture(n, False))
                remove = Gtk.Button(label='Clear')
                remove.connect('clicked', lambda _, n=name: clear(n))
                grid.attach(buttons[name], 1, row, 1, 1)
                grid.attach(add, 2, row, 1, 1)
                grid.attach(remove, 3, row, 1, 1)
            row = len(CONTROLS)
            grid.attach(Gtk.Label(label='Mouse camera sensitivity', xalign=0), 0, row, 1, 1)
            sens = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.1, 5.0, 0.1)
            try:
                sens.set_value(float(self.controls.get('mouse_sensitivity', 1.0)))
            except (TypeError, ValueError):
                sens.set_value(1.0)
            sens.add_mark(1.0, Gtk.PositionType.BOTTOM, None)
            grid.attach(sens, 1, row, 3, 1)
            invert = Gtk.CheckButton(label='Invert camera up/down')
            invert.set_active(bool(self.controls.get('invert_y')))
            grid.attach(invert, 1, row + 1, 3, 1)
            note = Gtk.Label(xalign=0)
            note.set_markup('<small>Click the game window to let the mouse turn the camera; Alt releases it. '
                            'A controller keeps working alongside.</small>')
            note.set_line_wrap(True)
            grid.attach(note, 0, row + 2, 4, 1)
            scroll = Gtk.ScrolledWindow()
            scroll.set_vexpand(True)
            scroll.add(grid)
            dialog.get_content_area().pack_start(scroll, True, True, 0)
            dialog.show_all()
            while True:
                response = dialog.run()
                if response == 1:
                    for name in bindings:
                        bindings[name] = list(defaults[name])
                        refresh(name)
                    sens.set_value(1.0)
                    invert.set_active(False)
                    continue
                if response == Gtk.ResponseType.OK:
                    self.controls = {'bindings': bindings, 'mouse_sensitivity': round(sens.get_value(), 2),
                                     'invert_y': invert.get_active()}
                    self.save_settings({})
                break
            dialog.destroy()

        def show_credits(self, _):
            dialog = Gtk.Dialog(title='Credits & licenses', transient_for=self.window, modal=True)
            dialog.add_button('Close', Gtk.ResponseType.CLOSE)
            dialog.set_default_size(680, 520)
            view = Gtk.TextView(editable=False, cursor_visible=False, wrap_mode=Gtk.WrapMode.WORD)
            view.set_left_margin(12);view.set_right_margin(12)
            try:
                text = (ROOT / 'app/CREDITS.md').read_text()
            except OSError:
                text = 'CREDITS.md is missing from this AppImage.'
            # Plain text view: drop the Markdown emphasis, heading marks and link targets.
            text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
            text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
            text = re.sub(r'^#+ ', '', text, flags=re.M)
            text += ('\nLicense texts and THIRD_PARTY_NOTICES.md: ' + str(ROOT / 'usr/share/licenses') +
                     '\nCorresponding source code for every bundled component is published next to this '
                     'AppImage on the release page:\nhttps://github.com/robertoqimin/battride-war-port/releases\n')
            view.get_buffer().set_text(text)
            scroll = Gtk.ScrolledWindow();scroll.add(view);scroll.set_vexpand(True)
            dialog.get_content_area().pack_start(scroll, True, True, 0)
            dialog.show_all();dialog.run();dialog.destroy()

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
