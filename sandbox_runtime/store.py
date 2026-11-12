"""Explicit in-memory synthetic store. No filesystem, network or production discovery."""
from __future__ import annotations
import copy
import hashlib
import re
from framework.api import _json_domain
from framework.model import Model, Node, Edge
from framework.security import context_shape

FIELDS={"id","revision","tenant","sensitivity","creation_readers","current_readers","edges","tombstoned","body","key","architecture","version","conditions"}


def wordset(text):
    return frozenset(re.findall(r"[a-z0-9_]+|[\u3400-\u9fff]",text.lower()))


def text(value, maximum=128):
    if type(value) is not str or not 1<=len(value)<=maximum: raise ValueError("INVALID_FIXTURE")
    value.encode("utf-8",errors="strict")
    return value


def integer(value):
    if type(value) is not int or not 1<=value<=9007199254740991: raise ValueError("INVALID_FIXTURE")
    return value


def strings(value):
    if type(value) is not list or len(value)>128 or any(type(x) is not str for x in value): raise ValueError("INVALID_FIXTURE")
    if value!=sorted(set(value)): raise ValueError("INVALID_FIXTURE")
    for x in value: text(x)
    return frozenset(value)


class Probe:
    """Independent store-boundary observer; private IDs never appear in observation."""
    def __init__(self): self.events=[]
    def record(self, operation, **fields):
        self.events.append({"operation":operation,**copy.deepcopy(fields)})


class SyntheticStore:
    def __init__(self, fixture, *, synthetic, probe):
        if synthetic is not True or type(probe) is not Probe: raise ValueError("EXPLICIT_SYNTHETIC_REQUIRED")
        if type(fixture) is not list or len(fixture)>20000: raise ValueError("INVALID_FIXTURE")
        self._probe=probe;self._records={};self._nodes={};self._index={};self._tokens={};self._model=Model()
        for original in fixture:
            _json_domain(original)
            row=copy.deepcopy(original)
            if type(row) is not dict or set(row)!=FIELDS: raise ValueError("INVALID_FIXTURE")
            key=text(row["id"])
            if key in self._records: raise ValueError("DUPLICATE_ID")
            revision=integer(row["revision"]);tenant=text(row["tenant"])
            if type(row["sensitivity"]) is not int or row["sensitivity"] not in range(4) or type(row["tombstoned"]) is not bool: raise ValueError("INVALID_FIXTURE")
            readers=strings(row["creation_readers"]);current=strings(row["current_readers"])
            if not current<=readers: raise ValueError("CREATION_READER_CEILING")
            body=text(row["body"],65536)
            for f in ("key","architecture","version"): text(row[f])
            if type(row["conditions"]) is not dict or len(row["conditions"])>32: raise ValueError("INVALID_FIXTURE")
            for k,v in row["conditions"].items(): text(k);text(v)
            if type(row["edges"]) is not list or len(row["edges"])>128: raise ValueError("INVALID_FIXTURE")
            edges=[]
            for e in row["edges"]:
                if type(e) is not dict or set(e)!={"target","relation","revision","content_sha"}: raise ValueError("INVALID_FIXTURE")
                text(e["target"]);integer(e["revision"])
                if e["relation"] not in ("derived","corroborating","contradicting","unknown") or type(e["content_sha"]) is not str or re.fullmatch("[0-9a-f]{64}",e["content_sha"]) is None: raise ValueError("INVALID_FIXTURE")
                edges.append(Edge(**e))
            digest=hashlib.sha256(body.encode("utf-8")).hexdigest()
            self._records[key]=row
            self._nodes[key]=Node(tenant,revision,digest,row["sensitivity"],readers,current,tuple(edges),row["tombstoned"])
            self._index.setdefault(row["key"],set()).add(key)
            for token in wordset(body+" "+row["key"]):self._tokens.setdefault(token,set()).add(key)

    def _context(self, context, now):
        ctx=context_shape(context)
        if type(now) is not int or not 0<=now<=9007199254740991 or now>=ctx["expires_at"]:raise ValueError("EXPIRED_CONTEXT")
        return ctx

    def _allowed(self, key, ctx):
        return self._model.can_read(key,self._nodes,tenant=ctx["tenant"],principal=ctx["principal"],clearance=ctx["clearance"])

    def search(self, query, context, now, *, evidence_key=None, limit=8):
        ctx=self._context(context,now);text(query,4096)
        if type(limit) is not int or not 1<=limit<=64:raise ValueError("INVALID_LIMIT")
        if evidence_key is not None:text(evidence_key)
        tokens=wordset(query)
        ids=set(self._index.get(evidence_key,())) if evidence_key is not None else set().union(*(self._tokens.get(t,()) for t in tokens))
        # Visibility closes over the complete graph before ranking or truncation.
        visible=[key for key in ids if self._allowed(key,ctx)]
        ranked=sorted(visible,key=lambda key:(-len(tokens&wordset(self._records[key]["body"]+" "+self._records[key]["key"])),key))[:limit]
        result=[{"id":key,"revision":self._nodes[key].revision,"content_sha":self._nodes[key].content_sha} for key in ranked]
        self._probe.record("search",returned=len(result),mode="key" if evidence_key is not None else "text")
        return copy.deepcopy(result)

    def get(self, locator, context, now):
        ctx=self._context(context,now)
        if type(locator) is not dict or set(locator)!={"id","revision","content_sha"}:raise ValueError("INVALID_LOCATOR")
        text(locator["id"]);integer(locator["revision"])
        if type(locator["content_sha"]) is not str or re.fullmatch("[0-9a-f]{64}",locator["content_sha"]) is None:raise ValueError("INVALID_LOCATOR")
        key=locator["id"];n=self._nodes.get(key)
        if n is None or not self._allowed(key,ctx) or n.revision!=locator["revision"] or n.content_sha!=locator["content_sha"]:
            self._probe.record("get",matched=False,bytes=0);return None
        row=copy.deepcopy(self._records[key])
        if hashlib.sha256(row["body"].encode("utf-8")).hexdigest()!=n.content_sha:
            self._probe.record("get",matched=False,bytes=0);return None
        self._probe.record("get",matched=True,bytes=len(row["body"].encode("utf-8")))
        row["locator"]=copy.deepcopy(locator)
        return row
