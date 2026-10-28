# SPDX-License-Identifier: GPL-3.0-or-later
"""Dependency discovery never needs the vendor packages installed in CI."""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    'd5_sync_runtime_test', ROOT/'ingetrazo_d5_sync/runtime.py')
runtime = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runtime)


def test_override_requires_an_existing_executable(tmp_path, monkeypatch):
    python = tmp_path/'custom-python.exe'
    monkeypatch.setenv('INGETRAZO_D5_PYTHON', str(python))
    with pytest.raises(ValueError, match='executable'):
        runtime.find_worker_python()
    python.touch()
    assert runtime.find_worker_python() == python.resolve()


def test_discovery_matches_native_abi_and_reports_ready(tmp_path, monkeypatch):
    monkeypatch.delenv('INGETRAZO_D5_PYTHON', raising=False)
    monkeypatch.setenv('APPDATA',str(tmp_path/'roaming'))
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path/'local'))
    monkeypatch.setenv('PROGRAMFILES',str(tmp_path/'program-files'))
    monkeypatch.setattr(runtime.sys,'platform','win32')
    python = tmp_path/'local/Programs/Blender Foundation/Blender 5.2/5.2/python/bin/python.exe'
    python.parent.mkdir(parents=True)
    python.touch()
    (python.parent/'python313.dll').touch()
    numpy = python.parent.parent/'lib/site-packages/numpy'
    numpy.mkdir(parents=True)
    module = tmp_path/'roaming/Blender Foundation/Blender/5.2/scripts/addons/d5_export/tools/d5plugin.cp313-win_amd64.pyd'
    module.parent.mkdir(parents=True)
    module.touch()
    d5 = tmp_path/'roaming/D5 Render/d5_launcher.exe'
    d5.parent.mkdir(parents=True)
    d5.touch()
    assert runtime.find_worker_python() == python.resolve()
    assert runtime.dependency_report()['ready']
    module.rename(module.with_name('d5plugin.cp311-win_amd64.pyd'))
    with pytest.raises(ValueError, match='Install Blender'):
        runtime.find_worker_python()
    assert not runtime.dependency_report()['ready']


def test_non_windows_reports_unsupported_without_importing_vendor_code(monkeypatch):
    monkeypatch.delenv('INGETRAZO_D5_PYTHON', raising=False)
    monkeypatch.setattr(runtime.sys,'platform','linux')
    report = runtime.dependency_report()
    assert not report['ready']
    assert not report['supported']
    assert 'Windows' in report['error']
