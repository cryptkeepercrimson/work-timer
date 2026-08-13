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

    sys.path.insert(0, str(HERE))
    import wt_core
    version = wt_core.__version__
    print(f"Building Work Timer v{version}")
    print("If that isn't the version you meant to ship, stop now and update")
    print("__version__ in wt_core.py - see RELEASING.md.\n")

    command = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",              # one .exe, nothing to unzip
        "--windowed",             # no console window behind the widget
        # No space in the name: GitHub rewrites spaces as dots when a file is
        # attached to a release, which turns "Work Timer.exe" into the rather
        # dubious-looking "Work.Timer.exe" on an already-unsigned download.
        "--name", "WorkTimer",
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

    exe = DIST / "WorkTimer.exe"
    size = exe.stat().st_size / (1024 * 1024) if exe.exists() else 0
    print(f"\nBuilt: {exe}  ({size:.1f} MB)  version {version}")
    print("\nThat single file is the whole app. Copy it anywhere and run it;")
    print("it creates its Time Logs folder alongside itself.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
