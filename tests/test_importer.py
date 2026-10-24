import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import threading

spec=importlib.util.spec_from_file_location('port_importer',Path(__file__).resolve().parents[1]/'packaging/importer.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class ImporterTests(unittest.TestCase):
    def test_unsafe_paths(self):
        for name in ('../x','/x','a/../../b','a\\b','a\nb',''):
            with self.subTest(name=name),self.assertRaises(m.ImportError):m.safe_name(name)
    def test_archive_links_and_duplicates(self):
        for text in ('Path = x\nSymbolic Link = /tmp/x','Path = x\n\nPath = x'):
            with self.assertRaises(m.ImportError):m.disc_entries(text)
    def test_listing(self):
        self.assertEqual(m.disc_entries('Path = PS3_GAME/EBOOT.BIN\nSize = 123\n\n')['PS3_GAME/EBOOT.BIN']['Size'],'123')
    def test_bad_iso_leaves_no_partial_import(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'app').mkdir()
            (root/'app/package.json').write_text(json.dumps({'elf_sha256':'x','codecs':{}}))
            (root/'app/disc-manifest.json').write_text(json.dumps({'PS3_GAME/test':{'size':1,'sha256':'x'}}))
            iso=root/'game.iso';iso.write_bytes(b'bad')
            data=root/'data'
            class FakeRunner:
                cancelled=threading.Event()
                def run(self,*a,**kw):return 2,'ERROR: invalid archive'
            with self.assertRaises(m.ImportError):m.Package(root).import_iso(iso,data,FakeRunner())
            self.assertEqual(list(data.iterdir()),[])
    def test_existing_import_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'app').mkdir()
            (root/'app/package.json').write_text('{}');(root/'app/disc-manifest.json').write_text('{}')
            iso=root/'game.iso';iso.write_bytes(b'iso');data=root/'data';(data/'game').mkdir(parents=True)
            sentinel=data/'game/keep';sentinel.write_text('saved')
            with self.assertRaises(m.ImportError):m.Package(root).import_iso(iso,data,m.Runner())
            self.assertEqual(sentinel.read_text(),'saved')
    def test_cancelled_runner_does_not_start_process(self):
        r=m.Runner();r.stop()
        with self.assertRaises(m.ImportError):r.run(['/does/not/exist'])

if __name__=='__main__':unittest.main()
