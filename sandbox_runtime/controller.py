"""Synchronous isolated action loop; trusted fixture inputs, not a production auth layer."""
from dataclasses import dataclass
import copy
import hashlib
from framework.api import _json_domain
from framework.spec import canonical
from framework.security import context_shape
from framework.context_recall import RecallBlocked as Halt, revalidate_evidence, select_evidence
from sandbox_runtime.store import SyntheticStore, Probe, text, integer


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def task_shape(value):
    _json_domain(value)
    if type(value) is not dict or set(value)!={"id","revision","query","requirements","budget"}:raise ValueError("INVALID_TASK")
    text(value["id"]);integer(value["revision"]);text(value["query"],4096)
    reqs=value["requirements"]
    if type(reqs) is not list or not 1<=len(reqs)<=8:raise ValueError("INVALID_TASK")
    seen=set()
    for r in reqs:
        if type(r) is not dict or set(r)!={"key","architecture","version","conditions"}:raise ValueError("INVALID_TASK")
        for k in ("key","architecture","version"):text(r[k])
        if r["key"] in seen:raise ValueError("DUPLICATE_REQUIREMENT")
        seen.add(r["key"])
        if type(r["conditions"]) is not dict or len(r["conditions"])>32:raise ValueError("INVALID_TASK")
        for k,v in r["conditions"].items():text(k);text(v)
    b=value["budget"]
    if type(b) is not dict or set(b)!={"calls","bytes","retries"}:raise ValueError("INVALID_TASK")
    for k,upper in (("calls",128),("bytes",1048576),("retries",1)):
        if type(b[k]) is not int or not 0<=b[k]<=upper:raise ValueError("INVALID_TASK")
    return copy.deepcopy(value)


class Ticket:
    """Identity capability; all content and evidence remain in Controller."""
    __slots__=()


class AlertSink:
    def __init__(self):self.events=[]
    def emit(self, reason):
        self.events.append({"event":"alert","reason":reason})


@dataclass(frozen=True)
class RecallPorts:
    """受信组装者提供端口；请求正文不能构造或改变端口。"""
    search: object
    get: object
    probe: Probe
    validate: object = None


class Controller:
    def __init__(self, store, probe, *, context_provider, clock, alerts):
        synthetic = type(store) is SyntheticStore and store._probe is probe
        supplied = type(store) is RecallPorts and store.probe is probe and callable(store.search) and callable(store.get)
        if not (synthetic or supplied) or type(probe) is not Probe or type(alerts) is not AlertSink:raise ValueError("INVALID_CAPABILITY")
        if not callable(context_provider) or not callable(clock):raise ValueError("INVALID_CAPABILITY")
        if supplied and store.validate is not None and not callable(store.validate):raise ValueError("INVALID_CAPABILITY")
        self.store=store;self.probe=probe;self.provider=context_provider;self.clock=clock;self.alerts=alerts
        self.events=[];self._pending=None;self._seq=0;self.usage={"calls":0,"bytes":0}

    def invalidate(self):
        self._pending=None

    def _fresh(self, state):
        ctx=context_shape(self.provider());now=self.clock()
        if type(now) is not int or not 0<=now<=9007199254740991:raise Halt("CONTEXT_CHANGED")
        if now<state["last_now"] or now>=ctx["expires_at"] or ctx!=state["context"]:raise Halt("CONTEXT_CHANGED")
        state["last_now"]=now
        return ctx,now

    def _call(self, state, op, argument, **kwargs):
        ctx,now=self._fresh(state)
        if state["calls"]>=state["task"]["budget"]["calls"]:raise Halt("BUDGET")
        state["calls"]+=1;self._seq+=1;self.usage["calls"]+=1
        rid=state["task_sha"]+":"+str(self._seq)
        if self.probe.events[state["trace_start"]:]!=state["trace"]:raise Halt("TRACE_UNKNOWN")
        before=len(self.probe.events)
        try:result=getattr(self.store,op)(argument,ctx,now,request_id=rid,**kwargs)
        except Exception:
            # Unknown completed work cannot be refunded into repeated event attempts.
            self.usage["calls"]+=state["task"]["budget"]["calls"]-state["calls"]
            self.usage["bytes"]+=max(0,state["task"]["budget"]["bytes"]-state["bytes"])
            raise
        if op=="get" and result is not None:
            self.usage["bytes"]+=len(result["body"].encode("utf-8"))
        observed=self.probe.events[before:]
        expected={"operation":op,"request_id":rid,"argument_sha":digest({"argument":argument,"options":kwargs}),"result_sha":digest(result)}
        if op=="search":expected.update(returned=len(result),mode="key" if kwargs.get("evidence_key") is not None else "text")
        else:expected.update(matched=result is not None,bytes=0 if result is None else len(result["body"].encode("utf-8")))
        if observed!=[expected]:raise Halt("TRACE_UNKNOWN")
        state["trace"].append(copy.deepcopy(expected))
        self.events.append({"request_id":rid,"task_sha":state["task_sha"],"operation":op,"argument_sha":digest(argument),"result_sha":digest(result)})
        if op=="get" and result is not None:
            state["bytes"]+=len(result["body"].encode("utf-8"))
            if state["bytes"]>state["task"]["budget"]["bytes"]:raise Halt("BUDGET")
        return result

    def _fail(self, state, reason):
        state["reason"]=reason;state["rows"]=[]
        before=len(self.alerts.events)
        self.alerts.emit(reason)
        if self.alerts.events[before:]!=[{"event":"alert","reason":reason}]:state["reason"]="ALERT_UNKNOWN"
        self.events.append({"operation":"alert","task_sha":state["task_sha"],"reason":state["reason"]})

    def prepare(self, task):
        self.invalidate()
        value=task_shape(task);ctx=context_shape(self.provider());now=self.clock()
        if type(now) is not int or not 0<=now<=9007199254740991 or now>=ctx["expires_at"]:raise ValueError("EXPIRED_CONTEXT")
        state={"task":value,"task_sha":digest(value),"context":ctx,"last_now":now,"calls":0,"bytes":0,"rows":[],"reason":None,"trace_start":len(self.probe.events),"trace":[]}
        try:
            state["rows"] = select_evidence(
                value, search=lambda query, **options: self._call(state, "search", query, **options),
                get=lambda locator: self._call(state, "get", locator),
                refetch=lambda: self.events.append({"operation":"refetch", "task_sha":state["task_sha"]}),
            )
        except Exception as e:
            self._fail(state,str(e) if isinstance(e,Halt) else "BACKEND_UNKNOWN")
        ticket=Ticket();self._pending=(ticket,state)
        return ticket

    def emit(self, ticket, task):
        if self._pending is None or ticket is not self._pending[0]:
            self.alerts.emit("INVALID_TICKET")
            return {"status":"blocked","reason":"INVALID_TICKET"}
        _,state=self._pending;self._pending=None
        try:
            if digest(task_shape(task))!=state["task_sha"]:raise Halt("TASK_CHANGED")
            if state["reason"] is not None:return {"status":"blocked","reason":state["reason"]}
            checked = revalidate_evidence(state["task"], state["rows"],
                                          get=lambda loc: self._call(state, "get", loc))
            actor, now = self._fresh(state)
            if type(self.store) is RecallPorts and self.store.validate is not None:
                self.store.validate(actor, now)
            output={"status":"ready","task_sha":state["task_sha"],"records":checked}
            self.events.append({"operation":"emit","task_sha":state["task_sha"],"response_sha":digest(output)})
            return output
        except Exception as e:
            reason=str(e) if isinstance(e,Halt) else "BACKEND_UNKNOWN"
            self._fail(state,reason)
            return {"status":"blocked","reason":state["reason"]}

    def run(self, task):
        return self.emit(self.prepare(task),task)
