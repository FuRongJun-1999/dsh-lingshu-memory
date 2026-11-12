"""Executable isolated acceptance. Trusted local checks, not a security certification."""
import ast
import hashlib
import importlib
import inspect
import io
import json
import os
import subprocess
import sys
import textwrap
import unittest
from framework.spec import ROOT,parse,canonical

CHECKS={
 "task_bound_retrieval":"test_sandbox_controller.ControllerTests.test_run_performs_search_read_key_confirmation_and_recheck",
 "filter_before_limit":"test_sandbox_store.SyntheticStoreTests.test_filter_before_limit_no_ids_or_counts_for_hidden",
 "exact_locator_readback":"test_sandbox_store.SyntheticStoreTests.test_locator_mismatch_and_unauthorized_uniform_none",
 "query_result_claim_binding":"test_sandbox_controller.ControllerTests.test_mutating_task_or_rows_after_prepare_is_rejected",
 "conditions_and_version":"test_sandbox_controller.ControllerTests.test_wrong_version_conditions_architecture_or_unauthorized",
 "no_facts_in_degraded_output":"test_sandbox_controller.ControllerTests.test_second_requirement_failure_discards_all_partial_facts",
 "bounded_refetch_alert":"test_sandbox_controller.ControllerTests.test_actual_refetch_after_irrelevant_initial_query",
 "independent_effect_probe":"test_sandbox_controller.ControllerTests.test_wrong_request_digest_does_not_count_as_action_evidence",
 "missing_logs_unknown":"test_sandbox_controller.ControllerTests.test_missing_store_log_is_unknown_not_accepted",
 "no_default_production":"test_context_cli.ContextCliTests.test_no_implicit_mode_duplicate_keys_paths_or_oversize",
 "resume_rebind":"test_replay.ReplayTests.test_compact_discards_ticket_and_resume_retrieves",
 "skip_retrieval":"test_sandbox_controller.ControllerTests.test_ticket_single_use_wrong_task_and_prepare_invalidation",
 "irrelevant_dummy_search":"test_benchmark.BenchmarkTests.test_dummy_search_and_missing_final_read_do_not_pass",
 "report_without_effect":"test_sandbox_controller.ControllerTests.test_reported_alert_without_actual_sink_effect_is_unknown",
 "large_irrelevant_corpus":"test_sandbox_store.SyntheticStoreTests.test_exact_key_locates_under_noise",
 "stale_revision":"test_sandbox_controller.ControllerTests.test_independent_review_equal_body_digest_wrong_revision",
 "same_name_wrong_task":"test_replay.ReplayTests.test_delayed_old_task_decision_never_consumes_new_task_ticket",
 "unauthorized_record":"test_sandbox_controller.ControllerTests.test_output_reauthorizes_all_context_fields_and_expiry",
 "side_effect_without_log":"test_sandbox_controller.ControllerTests.test_lost_prior_probe_or_untracked_side_effect_blocks",
 "budget_exhausted":"test_replay.ReplayTests.test_budget_carries_across_assemble_compact_resume",
 "production_fallback":"test_sandbox_store.SyntheticStoreTests.test_explicit_isolation_and_closed_input",
 "restart_or_compaction":"test_replay.ReplayTests.test_fresh_stream_bootstrap_retrieves_not_serialized_ticket",
}


def sha(value):return hashlib.sha256(canonical(value)).hexdigest()


def audited(case):
    method=getattr(case,case._testMethodName)
    tree=ast.parse(textwrap.dedent(inspect.getsource(method)))
    static=sum(isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr.startswith("assert") for n in ast.walk(tree))
    count=[0]
    for name in dir(case):
        if name.startswith("assert") and callable(getattr(case,name)):
            original=getattr(case,name)
            def wrap(*args,_original=original,**kwargs):
                count[0]+=1;return _original(*args,**kwargs)
            setattr(case,name,wrap)
    with __import__("contextlib").redirect_stdout(io.StringIO()):
        result=unittest.TextTestRunner(stream=io.StringIO()).run(unittest.TestSuite([case]))
    good=result.wasSuccessful() and result.testsRun==1 and static>0 and count[0]>0 and not (result.skipped or result.expectedFailures or result.unexpectedSuccesses)
    return dict(passed=bool(good),tests=result.testsRun,assertions=count[0],skips=len(result.skipped),expected_failures=len(result.expectedFailures),failures=len(result.failures),errors=len(result.errors))


def child(key):
    if key not in CHECKS:raise ValueError("UNKNOWN_CHECK")
    sys.path.insert(0,str(ROOT/"tests"))
    module,cls,method=CHECKS[key].split(".")
    return audited(getattr(importlib.import_module(module),cls)(method))


def process(argv):
    p=subprocess.run([sys.executable,"-X","utf8","-B",*argv],cwd=ROOT,capture_output=True,text=True,encoding="utf-8",errors="replace",env=dict(os.environ,PYTHONUTF8="1",PYTHONDONTWRITEBYTECODE="1"),shell=False,timeout=120)
    if p.returncode!=0:raise ValueError("SUBPROCESS_FAILED")
    return parse(p.stdout)


def validate_demos(context,replay,benchmark):
    fixture=parse((ROOT/"spec/context_demo.json").read_text(encoding="utf-8"));body=fixture["fixture"][0]["body"]
    expected=[{"body":body,"citation":{"id":fixture["fixture"][0]["id"],"revision":1,"content_sha":hashlib.sha256(body.encode()).hexdigest()}}]
    if context["output"]!={"status":"ready","task_sha":sha(fixture["task"]),"records":expected}:raise ValueError("CONTEXT_OUTPUT")
    if [a["operation"] for a in context["actions"]]!=["search","get","search","get","get"] or context["alerts"]:raise ValueError("CONTEXT_ACTIONS")
    if [x["status"] for x in replay["results"]]!=["started","prepared","compacted","prepared","ready","duplicate"]:raise ValueError("REPLAY_TRANSITIONS")
    if replay["results"][4]["records"]!=expected or replay["results"][-1]!={"status":"duplicate"}:raise ValueError("REPLAY_EVIDENCE")
    if len(replay["actions"])!=9 or replay["spent"]!={"calls":9,"bytes":5*len(body.encode())} or replay["alerts"]:raise ValueError("REPLAY_WORK")
    stored=parse((ROOT/"spec/benchmark_result.json").read_text(encoding="utf-8"))
    if benchmark!=stored or benchmark["passed"]!=39 or benchmark["total"]!=39:raise ValueError("BENCHMARK_MISMATCH")
    return {"context_sha":sha(context),"replay_sha":sha(replay),"benchmark_sha":sha(benchmark)}


def validate_child(result):
    if type(result) is not dict or set(result)!={"passed","tests","assertions","skips","expected_failures","failures","errors"}:raise ValueError("CHECK_SHAPE")
    if result["passed"] is not True or any(type(result[k]) is not int for k in result if k!="passed"):raise ValueError("CHECK_TYPES")
    if result["tests"]!=1 or result["assertions"]<1 or any(result[k]!=0 for k in ("skips","expected_failures","failures","errors")):raise ValueError("CHECK_FAILED")


def validate_coverage(contract,checks):
    if set(checks)!=set(contract["obligations"]+contract["negative_cases"]) or len(checks)!=22 or len(set(checks.values()))!=22:raise ValueError("COVERAGE")


def validate_snapshot(actual,stored):
    if actual!=stored:raise ValueError("ACCEPTANCE_DRIFT")


def run():
    contract=parse((ROOT/"spec/context_loop.json").read_text(encoding="utf-8"))
    validate_coverage(contract,CHECKS)
    evidence={}
    for key,name in CHECKS.items():
        result=process(["-m","sandbox_runtime.acceptance","--case",key])
        validate_child(result)
        evidence[key]={"test":name,**result}
    demos=validate_demos(process(["scripts/context_demo.py"]),process(["scripts/replay_demo.py"]),process(["scripts/context_benchmark.py"]))
    names=sorted({"sandbox_runtime/"+n for n in ("store.py","controller.py","replay.py","cli.py","replay_cli.py","benchmark.py","acceptance.py")} | {"scripts/context_acceptance.py","scripts/context_demo.py","scripts/replay_demo.py","scripts/context_benchmark.py","spec/core.json","spec/contract.lock.json","spec/context_loop.json","spec/context_demo.json","spec/replay_demo.json","spec/benchmark_cases.json","spec/benchmark.lock.json","spec/benchmark_result.json"} | {"tests/"+v.split(".")[0]+".py" for v in CHECKS.values()})
    names=sorted(set(names) | {p.relative_to(ROOT).as_posix() for directory in ("framework","tests") for p in (ROOT/directory).glob("*.py")})
    sources={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in names}
    return {"verdict":"ISOLATED_ACCEPTED","scope":"isolated_synthetic","contract_sha":sha(contract),"sources":sources,"checks":evidence,"demos":demos,"gui_integration":"NOT_RUN","production":"NOT_RUN","llm_evaluation":"NOT_RUN","open_semantic_retrieval":"NOT_EVALUATED"}


if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser();p.add_argument("--case",choices=CHECKS,required=True);args=p.parse_args()
    try:
        result=child(args.case);print(json.dumps(result,sort_keys=True));raise SystemExit(0 if result["passed"] else 1)
    except Exception:
        print(json.dumps({"passed":False,"reason":"CHECK_UNKNOWN"},sort_keys=True));raise SystemExit(2)
