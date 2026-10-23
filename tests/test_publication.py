"""Boundary tests for the source-only publication package (no game required)."""
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='battride-public-test-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'scripts').mkdir()
        self.script = self.root / 'scripts/export_source.py'
        self.script.write_bytes((ROOT / 'scripts/export_source.py').read_bytes())
        (self.root / 'README.md').write_text('test source package\n')
        (self.root / 'PUBLIC_FILES.txt').write_text('README.md\nPUBLIC_FILES.txt\n')

    def run_export(self, *args):
        return subprocess.run([sys.executable, str(self.script), *map(str, args)],
                              capture_output=True, text=True)

    def test_zip_contains_only_explicit_files(self):
        (self.root / 'game').mkdir()
        (self.root / 'game/EBOOT.ELF').write_bytes(b'private game fixture')
        (self.root / 'run-vulkan.sh').write_text('#!/bin/sh\nexit 0\n')
        (self.root / 'PUBLIC_FILES.txt').write_text('README.md\nPUBLIC_FILES.txt\nrun-vulkan.sh\n')
        output = self.root / 'source.zip'
        self.assertEqual(self.run_export('--output', output).returncode, 0)
        with zipfile.ZipFile(output) as archive:
            self.assertEqual(set(archive.namelist()), {
                'kamenriderbattridewarsport/README.md',
                'kamenriderbattridewarsport/PUBLIC_FILES.txt',
                'kamenriderbattridewarsport/run-vulkan.sh'})
            mode = archive.getinfo('kamenriderbattridewarsport/run-vulkan.sh').external_attr >> 16
            self.assertEqual(mode & 0o777, 0o755)

    def test_private_directory_and_traversal_rejected(self):
        for name in ('game/readme.md', '../README.md', '/tmp/example.md'):
            with self.subTest(path=name):
                (self.root / 'PUBLIC_FILES.txt').write_text(name + '\n')
                self.assertNotEqual(self.run_export().returncode, 0)

    def test_symlink_rejected(self):
        (self.root / 'link.md').symlink_to('README.md')
        (self.root / 'PUBLIC_FILES.txt').write_text('link.md\n')
        self.assertNotEqual(self.run_export().returncode, 0)

    def test_binary_disguised_as_source_rejected(self):
        (self.root / 'README.md').write_bytes(b'header\x00binary')
        self.assertNotEqual(self.run_export().returncode, 0)

    def test_existing_output_preserved(self):
        output = self.root / 'source.zip'
        output.write_bytes(b'preserve this file')
        self.assertNotEqual(self.run_export('--output', output).returncode, 0)
        self.assertEqual(output.read_bytes(), b'preserve this file')

if __name__ == '__main__':
    unittest.main()
