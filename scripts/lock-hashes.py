#!/usr/bin/env python3
"""Adds pip --hash lines to every pin in the two requirements files from PyPI's file digests.

Keeps the pinned versions as they are; only the hashes are (re)written. Every sdist and every wheel a
CPython 3.12 interpreter on any platform can install is hashed, so the same file serves the amd64 bundle
build, the arm64 test images and a macOS dev venv. Run after changing a version: scripts/lock-hashes.py
"""
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQUIREMENTS = [ROOT / 'requirements-py312.txt', ROOT / 'requirements-py312-test.txt']
PIN = re.compile(r'^([A-Za-z0-9_.-]+)==([^\s\\;]+)')


def read_pins(text):
    pins = []
    for line in text.splitlines():
        match = PIN.match(line)
        if match:
            pins.append(match.groups())
        elif line.strip() and not line.lstrip().startswith(('--hash', '#')):
            sys.exit(f'lock-hashes.py: not an exact pin: {line!r}')
    return pins


def is_installable_on_cpython312(filename):
    if not filename.endswith('.whl'):
        return filename.endswith(('.tar.gz', '.zip'))
    python_tags, abi_tag = filename[:-4].split('-')[-3:-1]
    for tag in python_tags.split('.'):
        if tag in ('cp312', 'py3', 'py2.py3') or tag.startswith('py3'):
            return True
        version = re.fullmatch(r'cp3(\d+)', tag)
        if version and abi_tag == 'abi3' and int(version.group(1)) <= 12:
            return True
    return False


def load_hashes(name, version):
    with urllib.request.urlopen(f'https://pypi.org/pypi/{name}/{version}/json', timeout=30) as response:
        files = json.load(response)['urls']
    hashes = sorted({file['digests']['sha256'] for file in files
                     if not file.get('yanked') and is_installable_on_cpython312(file['filename'])})
    if not hashes:
        sys.exit(f'lock-hashes.py: PyPI has no CPython 3.12 file for {name}=={version}')
    return hashes


def write_hashes(requirements):
    lines = []
    for name, version in read_pins(requirements.read_text()):
        hashes = load_hashes(name, version)
        lines.append(f'{name}=={version} \\')
        lines.extend(f'    --hash=sha256:{digest}' + (' \\' if index < len(hashes) - 1 else '')
                     for index, digest in enumerate(hashes))
        print(f'{name}=={version}: {len(hashes)} files', file=sys.stderr)
    requirements.write_text('\n'.join(lines) + '\n')


def main():
    for requirements in REQUIREMENTS:
        write_hashes(requirements)


if __name__ == '__main__':
    main()
