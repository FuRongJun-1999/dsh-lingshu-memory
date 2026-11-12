"""Normalized synthetic DSH event protocol. Not installed host hooks or persistence."""
import copy
from framework.api import _json_domain
from sandbox_runtime.controller import Controller, digest, task_shape
from sandbox_runtime.store import text, integer


class Replay:
    def __init__(self, controller, *, stream, session, bootstrap_task):
        if type(controller) is not Controller:raise ValueError("INVALID_CONTROLLER")
        self.bootstrap_sha=digest(task_shape(bootstrap_task))
        self.controller=controller;self.stream=text(stream);self.session=text(session)
        self.seq=0;self.highwater=0;self.seen={};self.revisions={}
        self.task=None;self.work=None;self.ticket=None;self.phase="empty";self.desync=False
        self.spent={"calls":0,"bytes":0};self.receipts=[]

    def _clear(self):
        self.controller.invalidate();self.ticket=None;self.work=None

    def _block(self, reason, *, desync=False):
        self._clear()
        if desync:self.desync=True
        before=len(self.controller.alerts.events)
        try:self.controller.alerts.emit(reason)
        except Exception:return {"status":"blocked","reason":"ALERT_UNKNOWN"}
        if self.controller.alerts.events[before:]!=[{"event":"alert","reason":reason}]:reason="ALERT_UNKNOWN"
        return {"status":"blocked","reason":reason}

    def _prepare(self):
        self._clear();self.work=copy.deepcopy(self.task)
        for k in ("calls","bytes"):self.work["budget"][k]=max(0,self.task["budget"][k]-self.spent[k])
        before=copy.deepcopy(self.controller.usage)
        try:self.ticket=self.controller.prepare(self.work)
        finally:
            for k in self.spent:self.spent[k]+=self.controller.usage[k]-before[k]
        self.phase="prepared"
        return {"status":"prepared","task_sha":digest(self.task)}

    def _decision(self):
        before=copy.deepcopy(self.controller.usage)
        try:result=self.controller.emit(self.ticket,self.work)
        finally:
            for k in self.spent:self.spent[k]+=self.controller.usage[k]-before[k]
            self._clear();self.phase="active"
        if result["status"]=="ready":result["task_sha"]=digest(self.task)
        return result

    def handle(self, event):
        # Invalid envelopes must revoke pending evidence, not leave a live ticket.
        try:
            _json_domain(event)
            if type(event) is not dict or set(event)!={"id","seq","stream","session","task_sha","kind","payload"}:raise ValueError()
            for k in ("id","stream","session","kind","task_sha"):text(event[k])
            integer(event["seq"])
            if type(event["payload"]) is not dict:raise ValueError()
        except Exception:return self._block("INVALID_EVENT",desync=True)
        if event["stream"]!=self.stream or event["session"]!=self.session:return self._block("WRONG_STREAM",desync=True)
        if self.phase=="closed":return {"status":"blocked","reason":"CLOSED"}
        sha=digest(event);eid=event["id"];seq=event["seq"];kind=event["kind"];payload=event["payload"]
        if eid in self.seen:
            if self.seen[eid]!=sha:return self._block("EVENT_COLLISION",desync=True)
            # No cached body, citation or automatic re-emission on duplicate delivery.
            return {"status":"duplicate"}
        if len(self.seen)>=256:return self._block("EVENT_LIMIT",desync=True)
        previous_highwater=self.highwater;self.highwater=max(self.highwater,seq)
        if self.desync:
            if kind!="session/resume" or seq<=previous_highwater:return self._block("DESYNC",desync=True)
        elif seq!=self.seq+1:return self._block("EVENT_ORDER",desync=True)
        allowed={"task/start","system-prompt/assemble","decision","context/compact","session/resume","session/close"}
        if kind not in allowed:return self._block("UNKNOWN_EVENT",desync=True)
        try:
            if kind in ("task/start","session/resume"):
                if set(payload)!={"task"}:raise ValueError()
                value=task_shape(payload["task"])
            elif payload:raise ValueError()
        except Exception:return self._block("INVALID_EVENT",desync=True)
        expected_task=digest(value) if kind in ("task/start","session/resume") else (digest(self.task) if self.task is not None else None)
        if event["task_sha"]!=expected_task:return self._block("EVENT_TASK",desync=True)
        # Consume only structurally valid envelopes; a failed transition still consumes seq.
        self.seen[eid]=sha;self.seq=seq
        try:
            if kind=="task/start":
                if self.task is None and digest(value)!=self.bootstrap_sha:return self._block("BOOTSTRAP_MISMATCH",desync=True)
                if value["revision"]<=self.revisions.get(value["id"],0):return self._block("TASK_REVISION",desync=True)
                self._clear();self.task=value;self.revisions[value["id"]]=value["revision"]
                self.spent={"calls":0,"bytes":0};self.phase="active"
                result={"status":"started","task_sha":digest(value)}
            elif kind=="session/resume":
                if self.task is None or digest(value)!=digest(self.task):return self._block("RESUME_MISMATCH",desync=True)
                self.desync=False;result=self._prepare()
            elif kind=="system-prompt/assemble":
                if self.task is None or self.phase not in ("active","prepared"):return self._block("NOT_ACTIVE")
                result=self._prepare()
            elif kind=="decision":
                if self.phase!="prepared" or self.ticket is None:return self._block("NOT_PREPARED")
                result=self._decision()
            elif kind=="context/compact":
                self._clear();self.phase="compacted";result={"status":"compacted"}
            else:
                self._clear();self.task=None;self.phase="closed";result={"status":"closed"}
        except Exception:result=self._block("BACKEND_UNKNOWN",desync=True)
        self.receipts.append({"event_sha":sha,"seq":seq,"status":result["status"]})
        return copy.deepcopy(result)
