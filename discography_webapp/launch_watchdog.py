"""Launch watchdog.py as a detached background process without deprecated wmic calls."""

import os
import subprocess
import sys

base = os.path.dirname(os.path.abspath(__file__))
watchdog = os.path.join(base, "watchdog.py")
system_python = r"C:\Python314\python.exe"
venv_python = os.path.join(base, "venv", "Scripts", "python.exe")
venv_site = os.path.join(base, "venv", "Lib", "site-packages")

if sys.platform == "win32" and os.path.isfile(system_python):
    python_exe = system_python
elif os.path.isfile(venv_python):
    python_exe = venv_python
else:
    python_exe = sys.executable

env = os.environ.copy()
sep = ";" if sys.platform == "win32" else ":"
paths = [base, os.path.dirname(base)]
if os.path.isdir(venv_site):
    paths.insert(0, venv_site)
if env.get("PYTHONPATH"):
    paths.append(env["PYTHONPATH"])
env["PYTHONPATH"] = sep.join(paths)

flags = 0
if sys.platform == "win32":
    flags = (
        getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        | getattr(subprocess, "CREATE_NO_WINDOW", 0)
    )

proc = subprocess.Popen(
    [python_exe, watchdog] + sys.argv[1:],
    cwd=base,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
    env=env,
    creationflags=flags,
    start_new_session=(sys.platform != "win32"),
)
print(f"Watchdog launched with PID {proc.pid}")
