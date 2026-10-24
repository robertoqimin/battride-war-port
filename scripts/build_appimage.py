#!/usr/bin/env python3
"""Build a private portable Linux package from an existing local build and disc metadata."""
import os,sys,subprocess,shutil,json,hashlib,re,time,argparse
from pathlib import Path
ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('--runtime', type=Path, required=True, help='Official type2-runtime x86_64 binary')
ap.add_argument('--rpcs3-dir', type=Path, required=True, help='Extracted RPCS3 AppDir')
ap.add_argument('--output', type=Path, required=True)
ap.add_argument('--stage', type=Path, default=Path('build-appimage/AppDir'))
args=ap.parse_args()
P=Path(__file__).resolve().parents[1]
args.runtime=args.runtime.resolve();args.rpcs3_dir=args.rpcs3_dir.resolve();args.output=args.output.resolve()
if args.output.exists():raise SystemExit('Output already exists; choose another filename')
S=args.stage.resolve()
if S.exists(): raise SystemExit('Stage already exists')
S.mkdir(parents=True)
def copy(a,b):
 b.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(a,b)
def sha(p):
 with open(p,'rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
for d in ['app','usr/bin','usr/lib','usr/libexec','usr/share/glib-2.0/schemas']: (S/d).mkdir(parents=True,exist_ok=True)
for n in ['importer.py','launcher.py']:copy(P/'packaging'/n,S/'app'/n)
copy(P/'build-vulkan/kamenriderbattridewarsport',S/'usr/bin/game-runner')
copy(sys.executable,S/'usr/bin/python3')
stdlib=Path('/usr/lib64/python3.14')
shutil.copytree(stdlib,S/'usr/lib/python3.14',ignore=shutil.ignore_patterns('site-packages','__pycache__','test','tests','idlelib','ensurepip'))
for n in ['gi','cairo']:shutil.copytree(stdlib/'site-packages'/n,S/'usr/lib/python3.14/site-packages'/n,ignore=shutil.ignore_patterns('__pycache__'))
shutil.copytree('/usr/lib64/girepository-1.0',S/'usr/lib/girepository-1.0')
copy('/usr/share/glib-2.0/schemas/gschemas.compiled',S/'usr/share/glib-2.0/schemas/gschemas.compiled')
shutil.copytree(args.rpcs3_dir,S/'usr/rpcs3',symlinks=True)
copy('/usr/bin/7z',S/'usr/bin/7z');copy('/usr/libexec/7zip/7z.so',S/'usr/bin/7z.so')
for n in ['ffmpeg','ffprobe']:
 copy('/usr/bin/'+n,S/'usr/libexec'/n)
 wrapper=S/'usr/bin'/n
 wrapper.write_text('#!/bin/sh\nR=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)\nexec "$R/usr/lib/ld-linux-x86-64.so.2" --library-path "$R/usr/lib" "$R/usr/libexec/'+n+'" "$@"\n');wrapper.chmod(0o755)
seeds=[]
for pattern in ['libgtk-3.so.0','libgdk-3.so.0','libgirepository-2.0.so.0','libvulkan.so.1','libwayland-*.so.*','libxkbcommon.so.0','libX*.so.*','libxcb*.so.*','libpulse.so.0','libasound.so.2','libpipewire-0.3.so.0','libdecor-0.so.0','libGL.so.1','libEGL.so.1','libGLX.so.0']:
 seeds+=list(Path('/usr/lib64').glob(pattern))
queue=seeds+[x for x in S.rglob('*') if x.is_file() and not x.is_symlink() and (x.suffix=='.so' or '.so.' in x.name or x.name in ['rpcs3','game-runner','python3','ffmpeg','ffprobe','7z'])]
seen=set();bom={}
while queue:
 p=queue.pop();resolved=p.resolve()
 if resolved in seen:continue
 seen.add(resolved)
 try:
  with p.open('rb') as f:
   if f.read(4)!=b'\x7fELF':continue
 except OSError:continue
 if not str(p).startswith(str(S)):
  dest=S/'usr/lib'/p.name
  if not dest.exists():copy(p,dest);bom[p.name]=str(resolved)
 out=subprocess.run(['ldd',str(p)],capture_output=True,text=True).stdout
 for line in out.splitlines():
  m=re.search(r'=> (/\S+)',line) or re.match(r'\s*(/\S+)',line)
  if m:
   dep=Path(m[1])
   if dep.exists():queue.append(dep)
# Always match the interpreter to the bundled libc.
copy('/lib64/ld-linux-x86-64.so.2',S/'usr/lib/ld-linux-x86-64.so.2')
manifest={}
for p in sorted((P/'game/PS3_GAME').rglob('*')):
 if p.is_file() and p.suffix.lower()!='.elf':manifest[str(p.relative_to(P/'game'))]={'size':p.stat().st_size,'sha256':sha(p)}
p=P/'game/PS3_DISC.SFB'
if p.exists():manifest['PS3_DISC.SFB']={'size':p.stat().st_size,'sha256':sha(p)}
(S/'app/disc-manifest.json').write_text(json.dumps(manifest,separators=(',',':')))
meta={'elf_sha256':'a53b7bca5d47490710ba02af5f885e1219d10c7a1a456fcf6e13a48db668a014','codecs':{p.name:sha(p) for p in (P/'firmware/dev_flash/sys/external').glob('*.pic')},'cpu':'znver2 / AVX2 FMA','runner_sha256':sha(S/'usr/bin/game-runner'),'runtime_sha256':sha(args.runtime)}
(S/'app/package.json').write_text(json.dumps(meta,indent=2));(S/'app/library-sources.json').write_text(json.dumps(bom,indent=2))
(S/'AppRun').write_text('''#!/bin/sh
APPDIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
export PORT_APPDIR="$APPDIR" PYTHONHOME="$APPDIR/usr" PYTHONPLATLIBDIR=lib
export PYTHONPATH="$APPDIR/app:$APPDIR/usr/lib/python3.14/site-packages" PYTHONDONTWRITEBYTECODE=1
export GI_TYPELIB_PATH="$APPDIR/usr/lib/girepository-1.0" GSETTINGS_SCHEMA_DIR="$APPDIR/usr/share/glib-2.0/schemas"
export GSETTINGS_BACKEND=memory GIO_USE_VFS=local
export PATH="$APPDIR/usr/bin:$PATH"
unset LD_LIBRARY_PATH LD_PRELOAD
ulimit -c 0
exec "$APPDIR/usr/lib/ld-linux-x86-64.so.2" --library-path "$APPDIR/usr/lib" "$APPDIR/usr/bin/python3" "$APPDIR/app/launcher.py" "$@"
''');(S/'AppRun').chmod(0o755)
(S/'battride-port.desktop').write_text('[Desktop Entry]\nType=Application\nName=Battride War Port\nExec=AppRun\nIcon=battride-port\nCategories=Game;\nTerminal=false\n')
(S/'battride-port.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128"><rect width="128" height="128" rx="24" fill="#14232d"/><text x="64" y="83" font-size="60" text-anchor="middle" fill="#38dfa0" font-family="sans-serif">BR</text></svg>')
(S/'.DirIcon').symlink_to('battride-port.svg')
copy(P/'LICENSE',S/'usr/share/licenses/port/LICENSE');copy(P/'THIRD_PARTY_NOTICES.md',S/'usr/share/licenses/port/THIRD_PARTY_NOTICES.md')
# Retain the installed dependency license collection with the private artifact.
shutil.copytree('/usr/share/licenses',S/'usr/share/licenses/system',symlinks=True)
print('STAGED',S,'files',len(manifest),flush=True)

args.output.parent.mkdir(parents=True,exist_ok=True)
payload=args.output.with_suffix('.squashfs.tmp')
if payload.exists():raise SystemExit('Payload already exists: '+str(payload))
subprocess.run(['mksquashfs',str(S),str(payload),'-noappend','-all-root','-no-xattrs','-comp','zstd','-processors','2'],check=True)
with args.output.open('xb') as out, args.runtime.open('rb') as runtime, payload.open('rb') as squash:
    shutil.copyfileobj(runtime,out);shutil.copyfileobj(squash,out)
args.output.chmod(0o755);payload.unlink()
args.output.with_suffix('.AppImage.sha256').write_text(sha(args.output)+'  '+args.output.name+'\n')
print('AppImage:',args.output)
