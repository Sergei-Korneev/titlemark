"""Тесты кроссплатформенного поиска внешних утилит (shelfmark.tools)."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from shelfmark.tools import ENV_TOOLS_DIR, find_tool, run_tool, tool_env


class TestFindTool(unittest.TestCase):
    def test_found_on_path(self):
        with mock.patch("shelfmark.tools.shutil.which",
                        return_value="/usr/bin/tesseract"):
            self.assertEqual(find_tool("tesseract"), "/usr/bin/tesseract")

    def test_found_in_env_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            tool = Path(tmp) / "djvutxt"
            tool.write_bytes(b"#!/bin/sh\n")
            with mock.patch("shelfmark.tools.shutil.which", return_value=None), \
                 mock.patch.dict(os.environ, {ENV_TOOLS_DIR: tmp}):
                self.assertEqual(find_tool("djvutxt"), str(tool))

    def test_found_in_env_dir_windows_suffix(self):
        with tempfile.TemporaryDirectory() as tmp:
            tool = Path(tmp) / "ddjvu.exe"
            tool.write_bytes(b"MZ")
            with mock.patch("shelfmark.tools.shutil.which", return_value=None), \
                 mock.patch.dict(os.environ, {ENV_TOOLS_DIR: tmp}):
                self.assertEqual(find_tool("ddjvu"), str(tool))

    def test_not_found(self):
        with mock.patch("shelfmark.tools.shutil.which", return_value=None), \
             mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(ENV_TOOLS_DIR, None)
            self.assertIsNone(find_tool("definitely-missing-tool"))


class TestToolEnv(unittest.TestCase):
    def test_library_path_for_local_install(self):
        """Утилита рядом с нераспакованными библиотеками должна их находить."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            exe_dir = root / "usr" / "bin"
            lib_dir = root / "usr" / "lib64"
            exe_dir.mkdir(parents=True)
            lib_dir.mkdir()
            exe = exe_dir / "djvutxt"
            exe.write_bytes(b"bin")
            env = tool_env(str(exe))
            self.assertIn(str(lib_dir), env.get("LD_LIBRARY_PATH", "")
                          + env.get("DYLD_LIBRARY_PATH", ""))

    def test_plain_env_without_exe(self):
        env = tool_env(None)
        self.assertEqual(env.get("PATH"), os.environ.get("PATH"))


class TestRunTool(unittest.TestCase):
    def test_stdout_returned(self):
        fake = mock.Mock(return_value=mock.Mock(stdout=b"hello",
                                                returncode=0))
        with mock.patch("shelfmark.tools.subprocess.run", fake):
            self.assertEqual(run_tool("/usr/bin/tool", ["arg"]), "hello")

    def test_error_returns_empty(self):
        with mock.patch("shelfmark.tools.subprocess.run",
                        side_effect=OSError("no such file")):
            self.assertEqual(run_tool("/usr/bin/tool", []), "")

    def test_timeout_returns_empty(self):
        with mock.patch("shelfmark.tools.subprocess.run",
                        side_effect=subprocess.TimeoutExpired("tool", 1)):
            self.assertEqual(run_tool("/usr/bin/tool", []), "")


if __name__ == "__main__":
    unittest.main()
