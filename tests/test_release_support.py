import struct
import tempfile
import unittest
from pathlib import Path

from scripts.release_support import validate_runtime, validate_windows_executable


class ReleaseArchitectureTests(unittest.TestCase):
    def test_x86_runtime_on_wow64(self):
        validate_runtime('windows-x86', 'Windows', 'AMD64', 32)
        validate_runtime('windows-x86', 'Windows', 'x86', 32)
        with self.assertRaises(ValueError):
            validate_runtime('windows-x86', 'Windows', 'AMD64', 64)

    def test_native_targets_reject_wrong_runtime(self):
        for target, system, machine in (
            ('linux-x86_64', 'Linux', 'x86_64'),
            ('macos-x86_64', 'Darwin', 'x86_64'),
            ('macos-arm64', 'Darwin', 'arm64'),
            ('windows-x86_64', 'Windows', 'AMD64'),
        ):
            with self.subTest(target=target):
                validate_runtime(target, system, machine, 64)
                with self.assertRaises(ValueError):
                    validate_runtime(target, system, machine, 32)

    def test_pe_header_distinguishes_x86_from_x64(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'netspector.exe'
            for target, machine, magic in (
                ('windows-x86', 0x14C, 0x10B),
                ('windows-x86_64', 0x8664, 0x20B),
            ):
                header = bytearray(90)
                header[:2] = b'MZ'
                struct.pack_into('<I', header, 60, 64)
                header[64:68] = b'PE\0\0'
                struct.pack_into('<H', header, 68, machine)
                struct.pack_into('<H', header, 88, magic)
                path.write_bytes(header)
                validate_windows_executable(path, target)
                other = 'windows-x86_64' if target == 'windows-x86' else 'windows-x86'
                with self.assertRaises(ValueError):
                    validate_windows_executable(path, other)
                struct.pack_into('<H', header, 88, 0)
                path.write_bytes(header)
                with self.assertRaises(ValueError):
                    validate_windows_executable(path, target)

    def test_invalid_pe_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'netspector.exe'
            for data in (b'', b'MZ', b'not an executable' * 10):
                path.write_bytes(data)
                with self.assertRaises(ValueError):
                    validate_windows_executable(path, 'windows-x86')
