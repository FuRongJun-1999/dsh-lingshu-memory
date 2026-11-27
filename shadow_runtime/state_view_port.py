"""在显式合成状态存储上读取单槽租约视图。"""
from framework.security import integer
from framework.state_lease import lease_view
from shadow_runtime.state_event_port import StateEventStore


def file_state_view(store, *, subject, slot, context, now, allowed, ttl_seconds):
    """调用方负责给同一时钟、读权限与 TTL；不推断身份或默认租约。"""
    if type(store) is not StateEventStore:
        raise ValueError('SYNTHETIC_SLOT_STORE_REQUIRED')
    if not integer(ttl_seconds) or ttl_seconds == 0:
        raise ValueError('INVALID_LEASE_TIME')
    snapshot = store.inspect(subject=subject,slot=slot,context=context,now=now,allowed=allowed)
    return lease_view(snapshot,now=now,ttl_seconds=ttl_seconds)
