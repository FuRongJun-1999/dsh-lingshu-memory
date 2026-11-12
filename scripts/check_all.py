"""Run all local specification gates with explicit UTF-8 subprocesses."""
import os
import pathlib
import subprocess
import sys
ROOT = pathlib.Path(__file__).resolve().parents[1]
ENV = dict(os.environ, PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")

def main():
    commands = [[sys.executable, "-B", "scripts/spec_tools.py", "check"],
                [sys.executable, "-B", "scripts/workspace_index.py"],
                [sys.executable, "-B", "scripts/public_guard.py"],
                [sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-v"]]
    failures = 0
    for argv in commands:
        r = subprocess.run(argv, cwd=ROOT, env=ENV, shell=False, capture_output=True,
                           text=True, encoding="utf-8", errors="replace")
        print("GATE", " ".join(argv[1:]), "EXIT", r.returncode)
        print(r.stdout, end="")
        print(r.stderr, end="")
        failures += r.returncode != 0
    print("SPECIFICATION TOOLS:", "PASS" if not failures else "FAIL")
    print("PRODUCTION RUNTIME GATES: NOT_RUN (isolated synthetic store tests are not production acceptance)")
    return bool(failures)

if __name__ == "__main__":
    raise SystemExit(main())
