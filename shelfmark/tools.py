"""Кроссплатформенный поиск внешних утилит: poppler, tesseract, djvulibre.

Пакет целиком работает на Python-стандартной библиотеке; внешние утилиты
необязательны и ищутся одинаково на Linux, macOS и Windows:

1. каталог из переменной окружения SHELFMARK_TOOLS;
2. PATH системы (на Windows учитываются .exe/.bat);
3. типичные места установки (Program Files/DjVuLibre, Homebrew, MacPorts,
   ~/.local/bin и др.).

Для утилит, распакованных «вручную» рядом с библиотеками, окружение
дополняется путём к этим библиотекам (LD_LIBRARY_PATH / DYLD_LIBRARY_PATH /
PATH), чтобы они запускались без системной установки.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ENV_TOOLS_DIR = "SHELFMARK_TOOLS"


def _candidate_dirs() -> list[Path]:
    """Каталоги, где утилиты могут лежать вне PATH."""
    dirs: list[Path] = []

    env_dir = os.environ.get(ENV_TOOLS_DIR)
    if env_dir:
        dirs.append(Path(env_dir))

    if sys.platform == "win32":
        for var in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
            base = os.environ.get(var)
            if not base:
                continue
            root = Path(base)
            dirs += [
                root / "DjVuLibre",
                root / "poppler" / "bin",
                root / "poppler" / "Library" / "bin",
                root / "Tesseract-OCR",
                root / "Programs" / "Tesseract-OCR",
            ]
    elif sys.platform == "darwin":
        dirs += [Path("/opt/homebrew/bin"), Path("/usr/local/bin"),
                 Path("/opt/local/bin")]
    else:
        home = Path.home()
        dirs += [home / ".local" / "bin",
                 home / ".local" / "opt" / "djvulibre" / "usr" / "bin",
                 home / "bin"]

    return [d for d in dirs if d.is_dir()]


def find_tool(name: str) -> str | None:
    """Найти утилиту; None если её нет. Кроссплатформенно (Windows: .exe)."""
    found = shutil.which(name)          # PATH (+ PATHEXT на Windows)
    if found:
        return found
    for directory in _candidate_dirs():
        for candidate in (directory / name,
                          directory / f"{name}.exe",
                          directory / f"{name}.bat"):
            if candidate.is_file():
                return str(candidate)
    return None


def tool_env(exe: str | None = None) -> dict[str, str]:
    """Окружение для запуска утилиты: добавить путь к соседним библиотекам."""
    env = dict(os.environ)
    if not exe:
        return env

    exe_dir = Path(exe).parent
    if sys.platform == "win32":
        # DLL лежат рядом с .exe
        env["PATH"] = f"{exe_dir}{os.pathsep}{env.get('PATH', '')}"
        return env

    lib_dir = exe_dir.parent / ("lib64" if sys.platform.startswith("linux") else "lib")
    if not lib_dir.is_dir():
        lib_dir = exe_dir
    key = "DYLD_LIBRARY_PATH" if sys.platform == "darwin" else "LD_LIBRARY_PATH"
    env[key] = f"{lib_dir}{os.pathsep}{env.get(key, '')}"
    return env


def run_tool(exe: str, args: list[str], timeout: int = 120) -> str:
    """Запустить утилиту и вернуть stdout (текст); "" при любой ошибке."""
    try:
        res = subprocess.run([exe, *args], capture_output=True,
                             timeout=timeout, check=False,
                             env=tool_env(exe))
    except (subprocess.TimeoutExpired, OSError):
        return ""
    return res.stdout.decode("utf-8", errors="replace")
