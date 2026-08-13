"""Builds a single Work Timer.exe that runs without Python installed.

    python build_exe.py

The finished file lands in dist/. Everything else the build produces is
throwaway and is cleaned up afterwards.
"""

import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DIST = HERE / "dist"


def main():
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("PyInstaller is not installed. Run:\n\n    pip install pyinstaller\n")
        return 1

    command = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",              # one .exe, nothing to unzip
        "--windowed",             # no console window behind the widget
        "--name", "Work Timer",
        "--distpath", str(DIST),
        "--workpath", str(HERE / "build"),
        "--specpath", str(HERE / "build"),
        "--noconfirm",
        "--clean",
    ]
    icon = HERE / "docs" / "icon.ico"
    if icon.exists():
        command += ["--icon", str(icon)]
    command.append(str(HERE / "work_timer.py"))

    print("Building - this takes a minute or two...\n")
    result = subprocess.run(command)
    if result.returncode != 0:
        print("\nBuild failed.")
        return result.returncode

    # The build folder is intermediate junk; the .exe is self-contained.
    shutil.rmtree(HERE / "build", ignore_errors=True)

    exe = DIST / "Work Timer.exe"
    size = exe.stat().st_size / (1024 * 1024) if exe.exists() else 0
    print(f"\nBuilt: {exe}  ({size:.1f} MB)")
    print("\nThat single file is the whole app. Copy it anywhere and run it;")
    print("it creates its Time Logs folder alongside itself.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
