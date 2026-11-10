#!/usr/bin/env python3
"""Changes one exact pin in the requirements files and the three setup.py files, after checking PyPI has that version.

Usage: scripts/bump-pin.py <package> <version>   (normally through `make bump PKG=... VERSION=...`,
which then rewrites the hashes with scripts/lock-hashes.py). New transitive dependencies are not added:
the CI bundle build installs with --require-hashes and fails if one is missing.
"""
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQUIREMENTS = [ROOT / 'requirements-py312.txt', ROOT / 'requirements-py312-test.txt']
SETUP_FILES = [ROOT / package / 'setup.py' for package in ('bigchaindb', 'bigchaindb-abci', 'cryptoconditions')]
PIN = re.compile(r'^([A-Za-z0-9_.-]+)==([^\s\\;]+)', re.M)
SETUP_PIN = re.compile(r"""(['"])([A-Za-z0-9_.-]+)==([^'"]+)\1""")


def normalize_name(name):
    return re.sub(r'[-_.]+', '-', name).lower()


def check_version_on_pypi(name, version):
    try:
        urllib.request.urlopen(f'https://pypi.org/pypi/{name}/{version}/json', timeout=30).close()
    except urllib.error.HTTPError as error:
        sys.exit(f'bump-pin.py: PyPI has no {name}=={version} (HTTP {error.code})')


def set_requirements_pin(requirements, name, version):
    text = requirements.read_text()
    old_versions = [match.group(2) for match in PIN.finditer(text) if normalize_name(match.group(1)) == name]
    requirements.write_text(PIN.sub(lambda match: f'{match.group(1)}=={version}'
                                    if normalize_name(match.group(1)) == name else match.group(0), text))
    return old_versions


def set_setup_pin(setup_file, name, version):
    text = setup_file.read_text()
    old_versions = [match.group(3) for match in SETUP_PIN.finditer(text) if normalize_name(match.group(2)) == name]
    setup_file.write_text(SETUP_PIN.sub(lambda match: f'{match.group(1)}{match.group(2)}=={version}{match.group(1)}'
                                        if normalize_name(match.group(2)) == name else match.group(0), text))
    return old_versions


def main():
    if len(sys.argv) != 3:
        sys.exit('usage: scripts/bump-pin.py <package> <version>')
    name, version = normalize_name(sys.argv[1]), sys.argv[2]
    check_version_on_pypi(name, version)
    changed = {requirements.name: set_requirements_pin(requirements, name, version) for requirements in REQUIREMENTS}
    if not any(changed.values()):
        sys.exit(f'bump-pin.py: {name} is not pinned in {", ".join(changed)}')
    changed.update({str(setup_file.relative_to(ROOT)): set_setup_pin(setup_file, name, version)
                    for setup_file in SETUP_FILES})
    for filename, old_versions in changed.items():
        for old_version in old_versions:
            print(f'{filename}: {name} {old_version} -> {version}', file=sys.stderr)


if __name__ == '__main__':
    main()
