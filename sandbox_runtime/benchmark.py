"""Deterministic synthetic behavior benchmark; not LLM or production evaluation."""
import copy
import hashlib
import random
from framework.spec import canonical
from sandbox_runtime.store import SyntheticStore, Probe
from sandbox_runtime.controller import Controller, AlertSink


def row(name="zz-target",**changes):
    value=dict(id=name,revision=1,tenant="a",sensitivity=1,creation_readers=["p"],current_readers=["p"],edges=[],tombstoned=False,body="blue widget limit 8 蓝色组件限额八",key="widget.limit",architecture="widget",version="v1",conditions={"region":"east"})
    value.update(changes);return value


def build(case):
    ctx=dict(tenant="a",principal="p",clearance=2,auth_epoch=1,policy_generation=1,expires_at=100)
    req=dict(key="widget.limit",architecture="widget",version="v1",conditions={"region":"east"})
    task=dict(id=case["id"],revision=1,query=case["query"],requirements=[req],budget=copy.deepcopy(case["budget"]))
    rows=[row("noise-%04d"%i,key="noise.%d"%i,body="blue widget 蓝色组件 noise %d"%i) for i in range(case["noise"])]
    target=row();kind=case["variant"]
    if kind=="missing":target=None
    elif kind=="private":target=row(current_readers=[])
    elif kind=="tenant":target=row(tenant="b")
    elif kind=="version":target=row(version="v0")
    elif kind=="architecture":target=row(architecture="other")
    elif kind=="condition":target=row(conditions={"region":"west"})
    elif kind=="tombstone":target=row(tombstoned=True)
    elif kind=="dangling":target=row(edges=[dict(target="missing-parent",relation="derived",revision=1,content_sha="0"*64)])
    if target is not None:rows.append(target)
    if kind=="ambiguous":rows.append(row("conflict",body="alternative limit 9"))
    if kind=="candidate_cap":rows.extend(row("candidate-%02d"%i,version="old") for i in range(63))
    random.Random(case["seed"]).shuffle(rows)
    return rows,ctx,task


def sha(value):return hashlib.sha256(canonical(value)).hexdigest()


def assess(case, output, actions, alerts):
    # Oracle is the reviewed manifest, never inferred from SUT status or its citations.
    expected=case["expected"]
    errors=[]
    if output.get("status")!=expected["status"]:errors.append("status")
    if expected["status"]=="blocked":
        if output!={"status":"blocked","reason":expected["reason"]}:errors.append("blocked_shape")
        if alerts!=[{"event":"alert","reason":expected["reason"]}]:errors.append("alert")
    else:
        body=expected["body"];loc={"id":expected["id"],"revision":1,"content_sha":hashlib.sha256(body.encode("utf-8")).hexdigest()}
        if output.get("records")!=[{"body":body,"citation":loc}]:errors.append("evidence")
        if alerts:errors.append("unexpected_alert")
    if case["budget"]["calls"] and not actions:errors.append("no_actual_call")
    if len(actions)>case["budget"]["calls"]:errors.append("call_budget")
    projection=[{k:v for k,v in a.items() if k in ("operation","mode","returned","matched","bytes")} for a in actions]
    if projection!=case["expected_actions"]:errors.append("action_oracle")
    if sha(actions)!=case["expected_trace_sha"]:errors.append("trace_oracle")
    return errors


def run_case(case):
    rows,ctx,task=build(case)
    lexical_probe=Probe();lexical=SyntheticStore(rows,synthetic=True,probe=lexical_probe)
    hits=lexical.search(task["query"],ctx,1,limit=4)
    actual_ids=[x["id"] for x in hits]
    probe=Probe();alerts=AlertSink();store=SyntheticStore(rows,synthetic=True,probe=probe)
    controller=Controller(store,probe,context_provider=lambda:copy.deepcopy(ctx),clock=lambda:1,alerts=alerts)
    output=controller.run(task)
    errors=assess(case,output,probe.events,alerts.events)
    if sha(rows)!=case["fixture_sha"]:errors.append("fixture_drift")
    if output.get("status")=="ready" and output.get("task_sha")!=sha(task):errors.append("task_binding")
    if actual_ids!=case["text_top4"]:errors.append("lexical_oracle")
    # This counterfactual control executes no retrieval and claims no model answer.
    passive={"status":"NOT_RUN","calls":0,"evidence":[]}
    return {"id":case["id"],"query":case["query"],"noise":case["noise"],"seed":case["seed"],"variant":case["variant"],"case_sha":sha(case),"fixture_sha":sha(rows),"passive":passive,"text_top4":actual_ids,"text_target_hit":case["expected"].get("id") in actual_ids,"output":output,"actions":probe.events,"calls":len(probe.events),"bytes":sum(x.get("bytes",0) for x in probe.events),"alerts":alerts.events,"errors":errors}


def run(manifest):
    if set(manifest)!={"version","cases"} or manifest["version"]!=1:raise ValueError("INVALID_MANIFEST")
    results=[run_case(case) for case in manifest["cases"]]
    ids=[r["id"] for r in results]
    if not results or len(ids)!=len(set(ids)):raise ValueError("DUPLICATE_CASE")
    groups=[]
    for query,noise in sorted({(r["query"],r["noise"]) for r in results if r["variant"]=="normal"}):
        rs=[r for r in results if r["variant"]=="normal" and r["query"]==query and r["noise"]==noise]
        groups.append({"query":query,"noise":noise,"cases":len(rs),"text_target_hits":sum(r["text_target_hit"] for r in rs),"keyed_ready":sum(r["output"]["status"]=="ready" for r in rs),"passive_evidence":0})
    return {"manifest_sha":sha(manifest),"cases":results,"groups":groups,"passed":sum(not r["errors"] for r in results),"total":len(results),"transcript_sha":sha(results),"llm_evaluation":"NOT_RUN","production":"NOT_RUN"}
