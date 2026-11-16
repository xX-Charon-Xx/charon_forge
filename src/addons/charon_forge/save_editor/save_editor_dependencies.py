"""Installing lz4, which save files are compressed with, into Blender's python."""

import importlib
import importlib.util
import os
import site
import subprocess
import sys
import threading

PYTHON_EXE_PATH = sys.executable
PACKAGES = ("lz4",)

for p in site.getusersitepackages().split(os.pathsep):
    if p not in sys.path:
        sys.path.append(p)

_lock = threading.Lock()
_thread = None
# why the last install failed, for the error save_file.py raises
last_error = None


def check_package(package_name):
    importlib.invalidate_caches()
    return importlib.util.find_spec(package_name) is not None


def _run(command):
    # no console window flashing up on Windows
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    result = subprocess.run(command, capture_output=True, text=True, creationflags=flags)
    return result.returncode == 0, (result.stderr or result.stdout).strip()


def install_pip():
    return _run([PYTHON_EXE_PATH, "-m", "ensurepip", "--upgrade"])


def install_package(package_name):
    """pip install, falling back to the user site-packages when Blender's own
    is not writable. Returns (ok, output)."""
    ok, output = _run([PYTHON_EXE_PATH, "-m", "pip", "install", package_name])
    if not ok:
        ok, output = _run([PYTHON_EXE_PATH, "-m", "pip", "install", "--user", package_name])
    return ok, output


def missing_packages():
    return [name for name in PACKAGES if not check_package(name)]


def _install_missing():
    """Install whatever is missing. Returns True when nothing is left missing."""
    global last_error
    with _lock:
        missing = missing_packages()
        if not missing:
            return True
        print("Charon Forge: installing %s for the save manager" % ", ".join(missing))
        if not check_package("pip"):
            install_pip()
        for name in missing:
            ok, output = install_package(name)
            if not ok:
                last_error = "pip could not install %s: %s" % (name, output.splitlines()[-1] if output else "no output")
                print("Charon Forge: %s" % last_error)
        # a --user install lands in a folder that may not have existed when
        # sys.path was set up
        for p in site.getusersitepackages().split(os.pathsep):
            if p not in sys.path and os.path.isdir(p):
                sys.path.append(p)
        still_missing = missing_packages()
        if not still_missing:
            last_error = None
            print("Charon Forge: save manager dependencies installed")
        return not still_missing


def install_in_background():
    """Start installing anything missing on a thread, without holding up
    Blender. Does nothing when everything is already there."""
    global _thread
    if not missing_packages():
        return
    if _thread is not None and _thread.is_alive():
        return
    _thread = threading.Thread(target=_install_missing, name="CharonForgeDeps", daemon=True)
    _thread.start()


def ensure_dependencies():
    """Make sure everything the save files need can be imported, installing
    it now if it is missing. Returns True when it can."""
    if not missing_packages():
        return True
    if _thread is not None and _thread.is_alive():
        _thread.join()
    return _install_missing()


# the name the save manager called it by
def installDependencies():
    return ensure_dependencies()
