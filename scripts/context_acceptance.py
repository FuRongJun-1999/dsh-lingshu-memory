"""Execute complete isolated acceptance; compare existing report, never auto-approve drift."""
import json
import pathlib
import sys
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from framework.spec import parse
from sandbox_runtime.acceptance import run,validate_snapshot

if __name__=="__main__":
    result=run()
    stored=parse((ROOT/"spec/context_acceptance.json").read_text(encoding="utf-8"))
    validate_snapshot(result,stored)
    print(json.dumps(result,ensure_ascii=True,sort_keys=True))
