"""Launch watchdog.py as a fully detached background process.

Uses the system Python because it does NOT
have the venv Python 3.14.6 stub-process bug that spawns a child
for every launched process, causing duplicates.
"""

import os
import subprocess
import sys
import shutil

base = os.path.dirname(os.path.abspath(__file__))
watchdog = os.path.join(base, "watchdog.py")

# Find the system python executable, falling back to sys.executable if not found
system_python = shutil.which("python") or shutil.which("python3") or sys.executable

# Use wmic process call create for reliable independent process creation
cmd = f'"{system_python}" "{watchdog}"'
result = subprocess.run(
    ["wmic", "process", "call", "create", cmd],
    capture_output=True,
    text=True,
    timeout=15,
)
# Parse ProcessId from output
for line in result.stdout.splitlines():
    if "ProcessId" in line:
        pid = line.split("=")[-1].strip().strip(";")
        print(f"Watchdog launched with PID {pid}")
        break
else:
    print("Failed to launch watchdog")
    print(result.stdout)
    print(result.stderr)
    sys.exit(1)
