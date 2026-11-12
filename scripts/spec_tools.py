"""Generate full contracts and check a full-spec freeze digest."""
from __future__ import annotations
import argparse
import json
import pathlib
import sys
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from framework.spec import load, parse, digest

LOCK = ROOT / "spec/contract.lock.json"
DOC = ROOT / "docs/CONTRACTS.generated.md"

def rendered(spec):
    return ("# 核心契约（生成文件）\n\n"
            "由 spec/core.json 完整生成；请改真源，不手改本文件。参考模型不等于运行时。\n\n"
            + "规格版本：" + spec["spec_version"] + "；完整摘要：" + digest(spec) + "\n\n"
            + "~~~json\n" + json.dumps(spec, ensure_ascii=False, sort_keys=True, indent=2) + "\n~~~\n")

def freeze_errors(spec, lock):
    errors = []
    if set(lock) != {"spec_version", "sha256", "previous_sha256", "reason"}:
        return ["invalid lock structure"]
    if lock["spec_version"] != spec["spec_version"]:
        errors.append("spec version drift")
    if lock["sha256"] != digest(spec):
        errors.append("full spec digest drift")
    if not isinstance(lock["reason"], str) or not lock["reason"].strip():
        errors.append("missing lock reason")
    return errors

def version(value):
    return tuple(int(part) for part in value.split("."))

def main():
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=["generate", "check", "freeze"])
    p.add_argument("--reason", default="")
    args = p.parse_args()
    spec = load()
    if args.action == "generate":
        DOC.write_text(rendered(spec), encoding="utf-8", newline="\n")
        print("generated contracts")
        return 0
    if args.action == "freeze":
        if not args.reason.strip():
            raise ValueError("freeze requires --reason")
        old = parse(LOCK.read_text(encoding="utf-8")) if LOCK.exists() else None
        if old:
            if old["sha256"] == digest(spec):
                raise ValueError("no change; refusing to rewrite lock")
            if version(spec["spec_version"]) <= version(old["spec_version"]):
                raise ValueError("freeze requires increasing spec version")
        lock = {"spec_version": spec["spec_version"], "sha256": digest(spec),
                "previous_sha256": old["sha256"] if old else None, "reason": args.reason.strip()}
        LOCK.write_text(json.dumps(lock, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        print("wrote explicit freeze lock")
        return 0
    errors = []
    if not LOCK.exists():
        errors.append("missing contract lock")
    else:
        errors += freeze_errors(spec, parse(LOCK.read_text(encoding="utf-8")))
    if not DOC.exists() or DOC.read_text(encoding="utf-8") != rendered(spec):
        errors.append("generated contracts stale")
    for error in errors:
        print("FAIL:", error)
    if not errors:
        print("PASS: complete spec digest and generated contracts")
    return bool(errors)

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, KeyError, TypeError) as e:
        print("FAIL:", str(e))
        raise SystemExit(1)
