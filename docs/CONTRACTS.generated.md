# 核心契约（生成文件）

由 spec/core.json 完整生成；请改真源，不手改本文件。参考模型不等于运行时。

规格版本：0.2.0；完整摘要：7a35d4bb0b676349b4663f65dab47d1fc2e54746daffcfbfeb2fdc960938b989

~~~json
{
  "application_contracts": [
    "Write",
    "Read",
    "Govern",
    "SelfCheck"
  ],
  "bitemporal": {
    "axes": [
      "observed",
      "effective"
    ],
    "bounds": [
      "instant",
      "unbounded",
      "unknown"
    ],
    "defer_blocks_output": true,
    "interval": "half_open",
    "no_axis_fallback": true,
    "precision": "utc_second",
    "query_requires_explicit_axis": true,
    "unknown_is_unbounded": false
  },
  "conditions": {
    "attributes_type": "string_map",
    "contradiction_precedence": true,
    "missing_equals_satisfied": false,
    "slot_states": [
      "declared",
      "unknown"
    ],
    "slots": [
      "carrier",
      "method",
      "existence"
    ],
    "unknown_equals_match": false,
    "verdicts": [
      "MATCH",
      "NO_MATCH",
      "DEFER"
    ]
  },
  "edges": {
    "bind_target": [
      "node_id",
      "revision",
      "content_sha"
    ],
    "correction": "new_revision",
    "cross_tenant": "reject",
    "cycles": "reject",
    "mutation": "reject",
    "policy_tightening": "immediate",
    "policy_widening": "bounded_by_creation",
    "relations": [
      "derived",
      "corroborating",
      "contradicting",
      "unknown"
    ],
    "scope_composition": "intersection"
  },
  "formation": {
    "false_result": "direct",
    "quantifier": "any",
    "relation": "derived",
    "true_result": "derived"
  },
  "idempotency": {
    "different_fingerprint": "reject",
    "forget_releases_token": false,
    "incomplete_history": "unknown_block_retry",
    "same_fingerprint": "return_original",
    "scope": [
      "tenant",
      "principal",
      "operation",
      "token"
    ]
  },
  "recovery": {
    "absent_requires": "authoritative_preaccept_rejection_or_durable_cancellation_without_conflict",
    "empty_after_restart": "unknown",
    "power_claim_requires": "platform_evidence",
    "process_power_loss": "arbitrary_subset",
    "receipt_is": "historical_commit_not_current_visibility",
    "states": [
      "committed",
      "absent",
      "unknown"
    ]
  },
  "runtime_released": false,
  "schema_version": 1,
  "sensitivity": {
    "aggregate": "max",
    "clearance_operator": "gte",
    "dangling_relations": [
      "derived",
      "corroborating",
      "contradicting",
      "unknown"
    ],
    "inherit_relation": "derived",
    "invalid_to_quarantine": true,
    "levels": [
      0,
      1,
      2,
      3
    ],
    "max": 3,
    "unknown_to_max": true
  },
  "spec_version": "0.2.0",
  "status": "design-development",
  "verification": {
    "bind": [
      "subject_revision",
      "subject_content_sha",
      "scope",
      "method",
      "credential",
      "verified_at"
    ],
    "content_change": "invalidate",
    "independence_without_evidence": "unassessed",
    "source_identity_operands": [
      "verifier_id",
      "source_id"
    ],
    "source_identity_operator": "ne",
    "truth_assurance": "not_claimed"
  }
}
~~~
