"""Validate the interpreter and executable architecture before distribution."""
import struct
from pathlib import Path

TARGETS = {
    'linux-x86_64': ('Linux', 64, {'amd64', 'x86_64'}),
    'macos-x86_64': ('Darwin', 64, {'amd64', 'x86_64'}),
    'macos-arm64': ('Darwin', 64, {'arm64', 'aarch64'}),
    # platform.machine() can describe the 64-bit host under WOW64.
    'windows-x86': ('Windows', 32, {'x86', 'i386', 'i686', 'amd64', 'x86_64'}),
    'windows-x86_64': ('Windows', 64, {'amd64', 'x86_64'}),
}


def validate_runtime(target, system, machine, pointer_bits):
    expected_system, expected_bits, machines = TARGETS[target]
    if system != expected_system or machine.lower() not in machines or pointer_bits != expected_bits:
        raise ValueError(f'{target} requires {expected_system}/{expected_bits}-bit Python; got {system}/{machine}/{pointer_bits}-bit')


def validate_windows_executable(path, target):
    """Check both the PE Machine and Optional Header Magic, not the filename."""
    expected = {'windows-x86': (0x014C, 0x010B), 'windows-x86_64': (0x8664, 0x020B)}[target]
    with Path(path).open('rb') as stream:
        dos = stream.read(64)
        if len(dos) != 64 or dos[:2] != b'MZ':
            raise ValueError('Missing DOS executable header')
        offset, = struct.unpack_from('<I', dos, 60)
        if offset < 64:
            raise ValueError('Invalid PE header offset')
        stream.seek(offset)
        header = stream.read(26)
    if len(header) != 26 or header[:4] != b'PE\0\0':
        raise ValueError('Missing PE executable header')
    machine, = struct.unpack_from('<H', header, 4)
    magic, = struct.unpack_from('<H', header, 24)
    if (machine, magic) != expected:
        raise ValueError(f'{target} architecture mismatch: Machine={machine:#x}, Magic={magic:#x}')
    return 'PE32 / I386' if target == 'windows-x86' else 'PE32+ / AMD64'
