"""
Unit tests for cross-platform paths helper (fsoc.paths).
"""
import os
import sys
from pathlib import Path
from unittest import mock

from fsoc.paths import _data_root, data_dir, reports_dir, logs_dir, plugins_dir, open_reports_folder


def test_paths_macos_support():
    with mock.patch.dict(os.environ, {}, clear=True):
        with mock.patch("sys.platform", "darwin"):
            root = _data_root()
            assert root == Path.home() / "Library" / "Application Support" / "NETRA"


def test_paths_windows_support():
    with mock.patch.dict(os.environ, {"APPDATA": "/mock/appdata"}, clear=True):
        with mock.patch("sys.platform", "win32"):
            root = _data_root()
            assert root == Path("/mock/appdata/NETRA")



def test_paths_override(tmp_path):
    override_dir = tmp_path / "custom_netra"
    with mock.patch.dict(os.environ, {"NETRA_DATA_DIR": str(override_dir)}):
        root = _data_root()
        assert root == override_dir


def test_subdirectories_creation(tmp_path):
    override_dir = tmp_path / "custom_netra"
    with mock.patch.dict(os.environ, {"NETRA_DATA_DIR": str(override_dir)}):
        d = data_dir()
        r = reports_dir()
        l = logs_dir()
        p = plugins_dir()
        assert d.exists()
        assert r == override_dir / "reports"
        assert r.exists()
        assert l == override_dir / "logs"
        assert l.exists()
        assert p == override_dir / "plugins"
        assert p.exists()


def test_open_reports_folder_callable():
    assert callable(open_reports_folder)
