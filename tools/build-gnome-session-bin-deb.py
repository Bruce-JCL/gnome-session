#!/usr/bin/env python3

import gzip
import hashlib
import math
import shutil
import subprocess
import sys
from pathlib import Path


PACKAGE_NAME = 'gnome-session-bin'

MESON_STAGE_PATHS = [
    '/usr/bin/gnome-session',
    '/usr/bin/gnome-session-custom-session',
    '/usr/bin/gnome-session-inhibit',
    '/usr/bin/gnome-session-quit',
    '/usr/libexec/gnome-session-binary',
    '/usr/libexec/gnome-session-check-accelerated',
    '/usr/libexec/gnome-session-check-accelerated-gl-helper',
    '/usr/libexec/gnome-session-check-accelerated-gles-helper',
    '/usr/libexec/gnome-session-ctl',
    '/usr/libexec/gnome-session-failed',
    '/usr/share/GConf/gsettings/gnome-session.convert',
    '/usr/share/glib-2.0/schemas/org.gnome.SessionManager.gschema.xml',
    '/usr/share/gnome-session/hardware-compatibility',
    '/usr/share/man/man1/gnome-session-inhibit.1.gz',
    '/usr/share/man/man1/gnome-session-quit.1.gz',
    '/usr/share/man/man1/gnome-session.1.gz',
]

SYSTEM_COPY_PATHS = [
    '/usr/libexec/run-systemd-session',
    '/usr/share/doc/gnome-session-bin/changelog.Debian.gz',
    '/usr/share/doc/gnome-session-bin/copyright',
]

SYMLINKS = {
    '/usr/lib/gnome-session/run-systemd-session': '../../libexec/run-systemd-session',
}

CONTROL_FIELDS = [
    'Package',
    'Source',
    'Version',
    'Section',
    'Priority',
    'Architecture',
    'Installed-Size',
    'Maintainer',
    'Original-Maintainer',
    'Depends',
    'Recommends',
    'Breaks',
    'Description',
]


def fail(message: str) -> None:
    print(f'error: {message}', file=sys.stderr)
    raise SystemExit(1)


def run_command(command, *, cwd=None, capture_output=False):
    return subprocess.run(
        command,
        cwd=cwd,
        check=False,
        text=True,
        capture_output=capture_output,
    )


def parse_control_fields(text: str):
    fields = {}
    current_key = None

    for line in text.splitlines():
        if not line:
            continue
        if line[0].isspace():
            if current_key is None:
                fail('unexpected continuation line in dpkg metadata')
            fields[current_key] += '\n' + line
            continue

        key, value = line.split(':', 1)
        current_key = key
        fields[key] = value.lstrip()

    return fields


def format_control_field(key: str, value: str) -> str:
    lines = value.splitlines()
    if len(lines) == 1:
        return f'{key}: {lines[0]}\n'
    return f'{key}: {lines[0]}\n' + ''.join(f'{line}\n' for line in lines[1:])


def copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def gzip_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with source.open('rb') as input_file, destination.open('wb') as output_file:
        with gzip.GzipFile(filename='', mode='wb', fileobj=output_file, mtime=0) as gz_file:
            shutil.copyfileobj(input_file, gz_file)


def stage_meson_output(install_root: Path, package_root: Path, destination: str) -> None:
    if destination.endswith('.gz'):
        plain_destination = destination[:-3]
        source = install_root / plain_destination.lstrip('/')
        if not source.exists():
            fail(f'missing installed file for packaging: {source}')
        gzip_file(source, package_root / destination.lstrip('/'))
        return

    source = install_root / destination.lstrip('/')
    if not source.exists():
        fail(f'missing installed file for packaging: {source}')
    copy_file(source, package_root / destination.lstrip('/'))


def stage_system_file(package_root: Path, source_path: str) -> None:
    source = Path(source_path)
    if not source.exists():
        fail(f'missing required system file: {source}')
    copy_file(source, package_root / source_path.lstrip('/'))


def compute_installed_size_kib(package_root: Path) -> int:
    total_bytes = 0
    for path in package_root.rglob('*'):
        if 'DEBIAN' in path.parts:
            continue
        if path.is_file() and not path.is_symlink():
            total_bytes += path.stat().st_size
    return max(1, math.ceil(total_bytes / 1024))


def write_md5sums(package_root: Path) -> None:
    md5_lines = []
    for path in sorted(package_root.rglob('*')):
        if not path.is_file() or path.is_symlink() or 'DEBIAN' in path.parts:
            continue
        digest = hashlib.md5(path.read_bytes()).hexdigest()
        md5_lines.append(f'{digest}  {path.relative_to(package_root).as_posix()}')

    (package_root / 'DEBIAN' / 'md5sums').write_text('\n'.join(md5_lines) + '\n', encoding='utf-8')


def query_package_metadata():
    result = run_command(['dpkg-query', '-s', PACKAGE_NAME], capture_output=True)
    if result.returncode != 0:
        fail(f'failed to query installed package metadata: {result.stderr.strip()}')
    return parse_control_fields(result.stdout)


def write_control(package_root: Path, metadata) -> None:
    metadata = dict(metadata)
    metadata['Installed-Size'] = str(compute_installed_size_kib(package_root))

    control_text = ''.join(
        format_control_field(field, metadata[field])
        for field in CONTROL_FIELDS
        if field in metadata and metadata[field]
    )
    (package_root / 'DEBIAN' / 'control').write_text(control_text, encoding='utf-8')


def main(argv):
    if len(argv) != 3:
        fail('usage: build-gnome-session-bin-deb.py <build_root> <output_path>')

    build_root = Path(argv[1]).resolve()
    output_path = Path(argv[2]).resolve()

    install_root = build_root / 'deb-install-root'
    package_root = build_root / 'deb-package-root' / PACKAGE_NAME

    if install_root.exists():
        shutil.rmtree(install_root)
    if package_root.exists():
        shutil.rmtree(package_root)

    install_root.mkdir(parents=True)
    (package_root / 'DEBIAN').mkdir(parents=True)

    install_result = run_command(
        ['meson', 'install', '-C', str(build_root), '--destdir', str(install_root), '--no-rebuild', '--quiet']
    )
    if install_result.returncode != 0:
        fail('meson install failed; run ninja -C build first so packaging can reuse existing build outputs')

    metadata = query_package_metadata()

    for destination in MESON_STAGE_PATHS:
        stage_meson_output(install_root, package_root, destination)

    for source_path in SYSTEM_COPY_PATHS:
        stage_system_file(package_root, source_path)

    (package_root / 'usr/lib/gnome-session').mkdir(parents=True, exist_ok=True)
    for link_path, link_target in SYMLINKS.items():
        full_link_path = package_root / link_path.lstrip('/')
        full_link_path.parent.mkdir(parents=True, exist_ok=True)
        full_link_path.symlink_to(link_target)

    write_control(package_root, metadata)
    write_md5sums(package_root)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()

    build_result = run_command(
        ['dpkg-deb', '--root-owner-group', '--build', str(package_root), str(output_path)]
    )
    if build_result.returncode != 0:
        fail('dpkg-deb failed to create the package')


if __name__ == '__main__':
    main(sys.argv)