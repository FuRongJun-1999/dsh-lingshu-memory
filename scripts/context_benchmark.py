"""Run and verify the fixed public benchmark; no discovered production inputs."""
import hashlib
import json
import pathlib
import sys
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from framework.spec import parse
from sandbox_runtime.benchmark import run, sha


def main():
    manifest=parse((ROOT/"spec/benchmark_cases.json").read_text(encoding="utf-8"))
    lock=parse((ROOT/"spec/benchmark.lock.json").read_text(encoding="utf-8"))
    if sha(manifest)!=lock["manifest_sha"]:raise ValueError("MANIFEST_DRIFT")
    report=run(manifest)
    report["source_sha"]={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in ("sandbox_runtime/store.py","sandbox_runtime/controller.py","sandbox_runtime/benchmark.py")}
    print(json.dumps(report,ensure_ascii=True,sort_keys=True,allow_nan=False))
    return 0 if report["passed"]==report["total"] else 1

if __name__=="__main__":raise SystemExit(main())
