"""Assemble the macOS source installer on any host; validate vendored wheels."""
import argparse
from email.parser import Parser
import hashlib
import json
from pathlib import Path
import zipfile

from packaging.requirements import Requirement
from packaging.tags import compatible_tags, cpython_tags, mac_platforms
from packaging.utils import canonicalize_name, parse_wheel_filename

ROOT = Path(__file__).resolve().parents[1]
VERSION = '1.7.0-macos-beta1'


def wheel_closure(folder, architecture):
    environment = {'implementation_name': 'cpython', 'implementation_version': '3.14.10',
                   'os_name': 'posix', 'platform_machine': architecture, 'platform_release': '',
                   'platform_system': 'Darwin', 'platform_version': '', 'python_full_version': '3.14.10',
                   'platform_python_implementation': 'CPython', 'python_version': '3.14',
                   'sys_platform': 'darwin', 'extra': ''}
    platforms = list(mac_platforms(version=(11, 0), arch=architecture))
    supported = set(cpython_tags((3, 14), abis=['cp314'], platforms=platforms))
    supported.update(compatible_tags((3, 14), interpreter='cp314', platforms=platforms))
    wheels = {}
    for path in sorted(folder.glob('*.whl')):
        name, version, _, tags = parse_wheel_filename(path.name)
        if not tags & supported:
            raise ValueError('Wheel incompatible avec ' + architecture + ' : ' + path.name)
        with zipfile.ZipFile(path) as archive:
            if archive.testzip() is not None:
                raise ValueError('Wheel endommagé : ' + path.name)
            metadata = archive.read(next(n for n in archive.namelist() if n.endswith('.dist-info/METADATA'))).decode('utf-8')
        wheels[name] = (path, version, Parser().parsestr(metadata).get_all('Requires-Dist', []))
    pending = [Requirement(line.strip()) for line in (ROOT / 'macos/requirements.txt').read_text().splitlines()
               if line.strip() and not line.startswith('#')]
    selected = {}
    while pending:
        requirement = pending.pop()
        if requirement.marker and not requirement.marker.evaluate(environment):
            continue
        name = canonicalize_name(requirement.name)
        if name not in wheels:
            raise ValueError('Dépendance macOS absente : ' + str(requirement))
        path, version, dependencies = wheels[name]
        if version not in requirement.specifier:
            raise ValueError('Version incompatible : ' + str(requirement))
        if name in selected:
            continue
        selected[name] = path
        pending.extend(Requirement(value) for value in dependencies)
    lock = ''.join(name + '==' + str(wheels[name][1]) + ' --hash=sha256:' +
                   hashlib.sha256(selected[name].read_bytes()).hexdigest() + '\n' for name in sorted(selected))
    return list(selected.values()), lock


def source_files():
    result = [ROOT / 'THIRD_PARTY_NOTICES.md', ROOT / 'DISCLAIMER.md', ROOT / '.gitignore']
    result.extend(sorted(ROOT.glob('README*.md')))
    result.extend(sorted(ROOT.glob('CONTRIBUTING*.md')))
    excluded = {'__pycache__', 'build', 'dist', 'captures', 'wheels', 'output', 'tmp'}
    for name in ('commun', 'macos', 'linux', 'windows', 'docs'):
        for path in sorted((ROOT / name).rglob('*')):
            if path.is_file() and not excluded.intersection(path.relative_to(ROOT / name).parts) and path.suffix not in ('.pyc', '.log'):
                result.append(path)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--wheels-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    payloads = {p.relative_to(ROOT).as_posix(): p for p in source_files()}
    locks = {}
    counts = {}
    for architecture in ('arm64', 'x86_64'):
        wheels, lock = wheel_closure(args.wheels_root / ('wheels-' + architecture), architecture)
        counts[architecture] = len(wheels)
        for path in wheels:
            payloads['macos/wheels/' + architecture + '/' + path.name] = path
        locks['macos/wheels/' + architecture + '/requirements-lock.txt'] = lock
    metadata = {'application': 'OpenInk', 'version': VERSION, 'artifact_type': 'macOS installation kit',
                'native_app_included': False, 'native_macos_validation': False, 'hardware_validation': False,
                'requires': 'Python 3.14 + Tkinter on macOS; Apple command-line tools for standalone .app build',
                'wheels_per_architecture': counts,
                'sha256': {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in sorted(payloads.items())}}
    metadata['sha256'].update({name: hashlib.sha256(value.encode()).hexdigest() for name, value in locks.items()})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, path in sorted(payloads.items()):
            archive.write(path, 'OpenInk/' + name)
        for name, value in locks.items():
            archive.writestr('OpenInk/' + name, value)
        archive.writestr('OpenInk/KIT_INFO.json', json.dumps(metadata, indent=2) + '\n')
    checksum = hashlib.sha256(args.output.read_bytes()).hexdigest()
    args.output.with_suffix('.zip.sha256').write_text(checksum + '  ' + args.output.name + '\n')
    print(args.output)
    print('Wheels macOS vérifiés :', counts)
    print('SHA-256 :', checksum)


if __name__ == '__main__':
    main()
