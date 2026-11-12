"""Run a fixed public synthetic demo through the actual CLI process."""
import os
import pathlib
import subprocess
import sys

ROOT=pathlib.Path(__file__).resolve().parents[1]
if __name__=="__main__":
    q=subprocess.run([sys.executable,"-X","utf8","-B","-m","sandbox_runtime.cli","--synthetic"],input=(ROOT/"spec/context_demo.json").read_text(encoding="utf-8"),cwd=ROOT,capture_output=True,text=True,encoding="utf-8",errors="replace",env=dict(os.environ,PYTHONUTF8="1",PYTHONDONTWRITEBYTECODE="1"),shell=False,timeout=15)
    print(q.stdout,end="");print(q.stderr,end="",file=sys.stderr)
    raise SystemExit(q.returncode)
