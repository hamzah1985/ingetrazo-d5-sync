# SPDX-License-Identifier: GPL-3.0-or-later
"""Find locally installed dependencies without downloading vendor software."""
import os
from pathlib import Path
import re
import sys


def connector_tools():
    """Return installed D5 Blender connector directories, newest first."""
    appdata = os.environ.get('APPDATA')
    bundled = Path(__file__).resolve().parent/'vendor/d5_export/tools'
    folders = [bundled] if bundled.is_dir() else []
    if appdata:
        root = Path(appdata) / 'Blender Foundation' / 'Blender'
        folders.extend(sorted(root.glob('*/scripts/addons/d5_export/tools'), reverse=True))
    return folders


def compatible_module(python):
    """Find the native connector matching a bundled Python's DLL ABI tag."""
    for dll in python.parent.glob('python3*.dll'):
        match = re.fullmatch(r'python(3\d+)\.dll', dll.name, re.IGNORECASE)
        if match:
            for folder in connector_tools():
                matches = sorted(folder.glob('d5plugin.cp%s-win_amd64.pyd' % match[1]))
                if matches:
                    return matches[0]
    return None


def find_worker_python():
    """Use an explicit override or a compatible installed Blender runtime."""
    override = os.environ.get('INGETRAZO_D5_PYTHON')
    if override:
        path = Path(override).expanduser()
        if not path.is_file():
            raise ValueError('INGETRAZO_D5_PYTHON must point to a Python executable.')
        return path.resolve()
    if sys.platform != 'win32':
        raise ValueError('This experimental D5 Sync connector currently supports Windows only.')
    roots = []
    if os.environ.get('LOCALAPPDATA'):
        private = Path(os.environ['LOCALAPPDATA'])/'IngeTrazo/d5_sync/runtime/python.exe'
        if private.is_file() and compatible_module(private):
            return private.resolve()
        roots.append(Path(os.environ['LOCALAPPDATA']) / 'Programs' / 'Blender Foundation')
    if os.environ.get('PROGRAMFILES'):
        roots.append(Path(os.environ['PROGRAMFILES']) / 'Blender Foundation')
    for root in roots:
        for python in sorted(root.glob('Blender */*/python/bin/python.exe'), reverse=True):
            if python.is_file() and compatible_module(python):
                return python.resolve()
    raise ValueError('Install Blender and D5 LiveSync for Blender, or set INGETRAZO_D5_PYTHON.')


def dependency_report():
    """Return a read-only report; importing this module never launches a process."""
    report = {'platform': sys.platform, 'supported': sys.platform == 'win32'}
    appdata = os.environ.get('APPDATA')
    d5 = Path(appdata) / 'D5 Render' / 'd5_launcher.exe' if appdata else None
    report['d5_launcher'] = str(d5) if d5 and d5.is_file() else None
    report['connector_modules'] = [str(p) for folder in connector_tools()
                                   for p in folder.glob('d5plugin.cp*-win_amd64.pyd')]
    try:
        python = find_worker_python()
        report['python'] = str(python)
        module = compatible_module(python)
        report['matching_module'] = str(module) if module else None
        report['numpy_directory'] = next((str(p) for p in
            (python.parent / 'Lib' / 'site-packages' / 'numpy',
             python.parent.parent / 'lib' / 'site-packages' / 'numpy',
             python.parent.parent / 'Lib' / 'site-packages' / 'numpy') if p.is_dir()), None)
    except (OSError, ValueError) as error:
        report['error'] = str(error)
    report['ready'] = bool(report['supported'] and report.get('d5_launcher')
                           and report.get('python') and report.get('matching_module')
                           and report.get('numpy_directory'))
    return report


if __name__ == '__main__':
    import json
    print(json.dumps(dependency_report(), indent=2))
