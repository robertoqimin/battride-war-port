#!/usr/bin/env python3
"""Build the portable AppImage inside the documented Ubuntu 22.04 build image."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import sysconfig

ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('--sevenzip-dir',type=Path,required=True)
ap.add_argument('--runtime',type=Path,required=True)
ap.add_argument('--rpcs3-dir',type=Path,required=True)
ap.add_argument('--output',type=Path,required=True)
ap.add_argument('--stage',type=Path,default=Path('build-appimage/portable/AppDir'))
ap.add_argument('--runner',type=Path,default=Path('build-portable/kamenriderbattridewarsport'))
args=ap.parse_args()
P=Path(__file__).resolve().parents[1];S=args.stage.resolve()
if S.exists() or args.output.exists():raise SystemExit('Choose new stage and output paths; existing files are preserved.')
# Never package a newer build as if it had the documented compatibility floor.
if subprocess.check_output(['getconf','GNU_LIBC_VERSION'],text=True).strip()!='glibc 2.35':
    raise SystemExit('Build inside the Ubuntu 22.04 container (glibc 2.35).')

def copy(a,b):
    b.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(a,b)
def sha(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

# These libraries must match the host's GPU driver. Never ship a second libc,
# dynamic loader, C++ runtime, Vulkan/GL loader, DRM or LLVM/SPIRV implementation.
def host_library(name):
    return (name.startswith(('ld-linux','libc.so','libm.so','libpthread.so','libdl.so','librt.so',
            'libresolv.so','libnss_','libutil.so','libanl.so','libstdc++','libgcc_s','libatomic.so',
            'libvulkan','libGL','libEGL','libOpenGL','libdrm','libgbm','libLLVM','libSPIRV',
            'libudev','libX','libxcb','libwayland','libxkbcommon','libexpat','libelf','libz.so','libzstd')))

for d in ('app','usr/bin','usr/lib','usr/share/glib-2.0/schemas'):(S/d).mkdir(parents=True,exist_ok=True)
for n in ('importer.py','launcher.py'):copy(P/'packaging'/n,S/'app'/n)
copy(args.runner,S/'usr/bin/game-runner')
# Shader tools must be static/hidden; an unversioned SPIRV library can break RADV.
needed=subprocess.check_output(['readelf','-d',str(args.runner)],text=True)
if 'libSPIRV' in needed:raise SystemExit('Runner depends on shared SPIRV-Tools; rebuild with static libraries.')
copy(sys.executable,S/'usr/bin/python3')
version='%d.%d'%sys.version_info[:2]
shutil.copytree(sysconfig.get_path('stdlib'),S/'usr/lib'/('python'+version),ignore=shutil.ignore_patterns('site-packages','dist-packages','__pycache__','test','tests','idlelib','ensurepip','venv'))
for n in ('gi','cairo'):
    copyfrom=next((Path(p)/n for p in sys.path if (Path(p)/n).is_dir()))
    shutil.copytree(copyfrom,S/'usr/lib'/('python'+version)/'site-packages'/n,ignore=shutil.ignore_patterns('__pycache__'))
# GTK resources are private; application GIO plugins from the host are disabled.
shutil.copytree('/usr/lib/x86_64-linux-gnu/girepository-1.0',S/'usr/lib/girepository-1.0')
copy('/usr/share/glib-2.0/schemas/gschemas.compiled',S/'usr/share/glib-2.0/schemas/gschemas.compiled')
shutil.copytree(args.rpcs3_dir,S/'usr/rpcs3',symlinks=True)
for p in list((S/'usr/rpcs3/usr/lib').glob('*')):
    if host_library(p.name) and (p.is_file() or p.is_symlink()):p.unlink()
copy(args.sevenzip_dir/'7zz',S/'usr/bin/7z');copy(args.sevenzip_dir/'License.txt',S/'usr/share/licenses/7zip/License.txt')
for n in ('ffmpeg','ffprobe'):copy('/usr/bin/'+n,S/'usr/bin'/n)
subprocess.run(['cc','-O2','-march=x86-64','-msse4.1',str(P/'packaging/graphics_probe.c'),'-o',str(S/'usr/bin/graphics-probe'),*subprocess.check_output(['pkg-config','--cflags','--libs','sdl2','vulkan'],text=True).split()],check=True)
seeds=[]
libdir=Path('/usr/lib/x86_64-linux-gnu')
for pattern in ('libgtk-3.so.0','libgdk-3.so.0','libgirepository-1.0.so.1','libpulse.so.0','libasound.so.2','libdecor-0.so.0'):
    seeds.extend(libdir.glob(pattern))
queue=seeds+[p for p in S.rglob('*') if p.is_file() and not p.is_symlink()]
seen=set();bom={};missing=set()
while queue:
    p=queue.pop();real=p.resolve()
    if real in seen:continue
    seen.add(real)
    try:
        with p.open('rb') as f:
            if f.read(4)!=b'\x7fELF':continue
    except OSError:continue
    if not str(p).startswith(str(S)):
        if host_library(p.name):continue
        dest=S/'usr/lib'/p.name
        if not dest.exists():copy(p,dest);bom[p.name]=str(real)
    out=subprocess.run(['ldd',str(p)],capture_output=True,text=True).stdout
    for line in out.splitlines():
        match=re.search(r'=> (/\S+)',line) or re.match(r'\s*(/\S+)',line)
        if match and Path(match[1]).exists():queue.append(Path(match[1]))
        elif 'not found' in line:missing.add(line.strip())
# RPCS3's private Qt libraries carry its optional dependencies. Record unresolved
# imports for review, but the actual helper must pass its integration test.
(S/'app/unresolved-build-libraries.txt').write_text('\n'.join(sorted(missing)))
manifest={}
for p in sorted((P/'game/PS3_GAME').rglob('*')):
    if p.is_file() and p.suffix.lower()!='.elf':manifest[str(p.relative_to(P/'game'))]={'size':p.stat().st_size,'sha256':sha(p)}
p=P/'game/PS3_DISC.SFB'
if p.exists():manifest['PS3_DISC.SFB']={'size':p.stat().st_size,'sha256':sha(p)}
(S/'app/disc-manifest.json').write_text(json.dumps(manifest,separators=(',',':')))
meta={'version':'0.2.0','glibc_min':'2.35','cpu':'x86_64 / SSE4.1; no AVX requirement','elf_sha256':'a53b7bca5d47490710ba02af5f885e1219d10c7a1a456fcf6e13a48db668a014',
      'codecs':{p.name:sha(p) for p in (P/'firmware/dev_flash/sys/external').glob('*.pic')},'runner_sha256':sha(args.runner),'sevenzip_sha256':sha(S/'usr/bin/7z'),'runtime_sha256':sha(args.runtime)}
(S/'app/package.json').write_text(json.dumps(meta,indent=2));(S/'app/library-sources.json').write_text(json.dumps(bom,indent=2))
(S/'AppRun').write_text('''#!/bin/sh
APPDIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
export PORT_APPDIR="$APPDIR" PYTHONHOME="$APPDIR/usr" PYTHONPLATLIBDIR=lib
export PYTHONPATH="$APPDIR/app:$APPDIR/usr/lib/python'''+version+'''/site-packages" PYTHONDONTWRITEBYTECODE=1
export GI_TYPELIB_PATH="$APPDIR/usr/lib/girepository-1.0" GSETTINGS_SCHEMA_DIR="$APPDIR/usr/share/glib-2.0/schemas"
export GSETTINGS_BACKEND=memory GIO_USE_VFS=local GIO_MODULE_DIR="$APPDIR/usr/lib/gio/modules"
export LD_LIBRARY_PATH="$APPDIR/usr/lib" PATH="$APPDIR/usr/bin:$PATH"
unset LD_PRELOAD
ulimit -c 0
exec "$APPDIR/usr/bin/python3" "$APPDIR/app/launcher.py" "$@"
''');(S/'AppRun').chmod(0o755)
(S/'usr/lib/gio/modules').mkdir(parents=True,exist_ok=True)
(S/'battride-port.desktop').write_text('[Desktop Entry]\nType=Application\nName=Battride War Port\nExec=AppRun\nIcon=battride-port\nCategories=Game;\nTerminal=false\n')
(S/'battride-port.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128"><rect width="128" height="128" rx="24" fill="#14232d"/><text x="64" y="83" font-size="60" text-anchor="middle" fill="#38dfa0" font-family="sans-serif">BR</text></svg>')
(S/'.DirIcon').symlink_to('battride-port.svg')
for n in ('LICENSE','THIRD_PARTY_NOTICES.md'):copy(P/n,S/'usr/share/licenses/port'/n)
shutil.copytree('/usr/share/doc',S/'usr/share/licenses/build-packages',symlinks=True,ignore=shutil.ignore_patterns('examples','html'))
print('STAGED',S,flush=True)
args.output.parent.mkdir(parents=True,exist_ok=True);payload=args.output.with_suffix('.squashfs.tmp')
if payload.exists():raise SystemExit('Temporary payload already exists')
subprocess.run(['mksquashfs',str(S),str(payload),'-noappend','-all-root','-no-xattrs','-comp','zstd','-processors','2'],check=True)
with args.output.open('xb') as out,args.runtime.open('rb') as rt,payload.open('rb') as squash:
    shutil.copyfileobj(rt,out);shutil.copyfileobj(squash,out)
args.output.chmod(0o755);payload.unlink()
args.output.with_suffix('.AppImage.sha256').write_text(sha(args.output)+'  '+args.output.name+'\n')
print('AppImage:',args.output)
