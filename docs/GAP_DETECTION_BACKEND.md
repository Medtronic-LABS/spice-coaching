# Gap Detection — Backend Guide

Audience: Deepak (and anyone touching the gap-detection backend on the `telemetry` branch).

Companion doc for the Android SDK: [`GAP_DETECTION_SDK.md`](./GAP_DETECTION_SDK.md). Read both — they describe two sides of the same contract.

---

## 1. Where we are

Already landed on `telemetry` branch:

| Commit | What |
|---|---|
| `cd41f2a` feat(telemetry) | `SPICE_ACTION_OBSERVED` handler in `module_completion_worker.process_module_event_job`. Reads `payload_json.behavioural_gap_id`, calls `GapStateService.record_observation`; if `outcome ∈ {wrong, incorrect}` also calls `record_failed_attempt`. |
| `2eb11ff` feat(module-suggestion) | `ModuleSuggestionService.suggest_for_chw` — reads `chw_behavioural_gap_state` ordered by severity → occurrence_count → recency, joins to modules via `module.primary_gap_id`, falls back to most-recent-per-family. |
| `385941f` feat(morning-module) | Morning cards API surface. |
| `8392a77` feat(sync) | Sync endpoints; `sync_service.get_gaps_bundle()` ships `behavioural_gap` rows including `detection_rule_jsonb` to the SDK (`packages/contracts/src/mc_contracts/sync.py:96-103` — `BehaviouralGapSyncPayload`). |
| `04b592d` refactor | ClickHouse telemetry UUIDs. |

What this means: the server-side scaffolding for the chosen architecture is **complete**. The pieces that remain are content (rule definitions) and validation, not new infrastructure.

---

## 2. The chosen architecture (one diagram, the whole picture)

```
┌─────────────────────────┐                ┌────────────────────────┐
│ Admin dashboard /       │                │ Android SDK            │
│ reviewer (future)       │                │ (in-process with SPICE)│
│                         │                │                        │
│ writes behavioural_gap. │                │ • Receives gaps bundle │
│ detection_rule_jsonb    │                │   on sync              │
└──────────┬──────────────┘                │ • At each SPICE event, │
           │                               │   evaluates rules      │
           ▼                               │ • Emits                │
┌─────────────────────────┐   sync_service │   SPICE_ACTION_OBSERVED│
│ Platform DB             ├───────────────►│   with tagged          │
│                         │                │   behavioural_gap_id   │
│ behavioural_gap         │                │   + outcome            │
│ (rule storage)          │                └──────────┬─────────────┘
└─────────────────────────┘                           │
           ▲                                          │ telemetry
           │                                          ▼
           │                          ┌───────────────────────────────┐
           │                          │ POST /telemetry/events        │
           │ updates                  │  → process_module_event_task  │
           │                          │  → module_completion_worker   │
┌──────────┴──────────────┐           │      .process_module_event_job│
│ chw_behavioural_gap_    │◄──────────┤                               │
│ state                   │  record_  │  record_observation (count)   │
│ (per-CHW gap counters)  │  observ.  │  record_failed_attempt        │
└──────────┬──────────────┘           │   (if outcome=wrong/incorrect)│
           │                          └───────────────────────────────┘
           │ read
           ▼
┌─────────────────────────┐
│ ModuleSuggestionService │
│ .suggest_for_chw        │
│ (morning-cards API)     │
└─────────────────────────┘
```

The server is a **counter and a rule store**, not an evaluator. Rule evaluation happens on the device. This is the *hybrid trigger evaluation* the data-model docstring (`db/models/behavioural_gap.py:8-9`) references.

---

## 3. Schema decision — keep `detection_rule_jsonb`

Earlier draft proposed dropping the column. That was wrong. Verified reasons to keep:

1. `sync_service.get_gaps_bundle()` already ships it (`services/platform/src/platform_service/services/sync_service.py:218`).
2. The wire contract `BehaviouralGapSyncPayload.detection_rule_jsonb: dict[str, Any]` is already in `mc_contracts`.
3. The SDK evaluation path needs *some* server-stored representation of the mapping. Without this, every rule change requires an SDK release. With it, rule changes ship via sync.

**Keep. Finalize the shape (Section 4). Populate the seed (Section 5).**

### 3.1 What the backend actually reads vs. what the SDK ships

The implemented handler (`module_completion_worker.py` SPICE branch from commit `cd41f2a`, around L86-129) reads **only two values** from a `SPICE_ACTION_OBSERVED` event:

- `payload_json.behavioural_gap_id` (UUID) → drives `record_observation`.
- `outcome` (top-level or under `payload_json`) → if `"wrong"` or `"incorrect"`, also drives `record_failed_attempt`.

The SDK doc spec also requires the SDK to ship `spice_event_code`, `assessment_type`, `rule_type`, and an `evidence` block in `payload_json`. **These are observability fields only** — they land in ClickHouse via the existing telemetry pipeline (`api/telemetry.py` writes `json.dumps(e.payload_json)` to the `coaching_events` table) for audit, debugging, and QA replay. The platform state machine ignores them.

This is the intended boundary: the backend doesn't re-derive clinical correctness, and it doesn't depend on SDK rule-evaluator implementation details. The SDK is trusted to tag correctly; the backend trusts the tag.

### 3.2 Rule update lifecycle (cache-until-sync)

`detection_rule_jsonb` changes are **not retroactive**. Sequence:

1. Admin edits a rule on the server.
2. SDK syncs (next periodic refresh or app foreground).
3. New rule is cached in the SDK's local Room DB; old rule is replaced.
4. Until step 2-3 happens, the device fires off the old rule.

For pilot, this is the right trade-off — push critical rule changes through a staging environment first, validate on a test device, then deploy. Don't design retroactive rule replay; the engineering cost is too high relative to the value at pilot scale.

---

## 4. Rule shape — typed `rule_type` enum

**Decision:** typed enum, not generic predicate DSL.

Rationale: 16 pilot gaps map to ~6-8 rule types. A generic predicate evaluator on the SDK side is a Kotlin code base unto itself. Typed enums give us a `when(rule_type)` dispatcher with one small function per type. Adding a new rule type requires code on both server (validator) and SDK (evaluator), but that's true for any non-trivial shape change to a generic DSL too.

### 4.1 Top-level shape

```json
{
  "schema_version": 1,
  "rule_type": "wrong_facility_tier",
  "params": { ... rule-type-specific ... },
  "match": {
    "spice_event_codes": ["NCDAssessmentCreation", "RMNCHAssessment"],
    "assessment_types": ["NCD", "RMNCH"]
  }
}
```

- `schema_version`: integer. Bumps when the envelope shape changes. The SDK must check and skip rules with a higher schema_version than it understands.
- `rule_type`: enum string. The SDK dispatches on this.
- `params`: rule-type-specific. Each `rule_type` has its own param schema, validated server-side before write.
- `match`: filters which SPICE events the rule even applies to. Optional but recommended — avoids the SDK evaluating every rule on every event.

### 4.2 Rule types for the pilot (the 4 we need)

| `rule_type` | What it observes | `params` shape |
|---|---|---|
| `wrong_facility_tier` | CHW selected a referral facility tier different from SPICE's computed expected tier (`REFERRAL_FACILITY_TYPE`) | `{}` (no params needed; logic is fixed: compare expected vs actual) |
| `bp_above_threshold_no_referral` | BP ≥ thresholds AND CHW didn't refer | `{"systolic_threshold": 140, "diastolic_threshold": 90}` |
| `glucose_above_threshold_no_referral` | Glucose ≥ threshold AND CHW didn't refer | `{"threshold_mmol_l": 15.0}` |
| `missing_danger_signs_record` | Assessment submitted without danger-signs field populated | `{}` |

All four are **immediate-fire** rules — they evaluate on a single SPICE event and decide synchronously. No local timers, no Room-backed pending state, no cross-event correlation.

**Deferred to post-pilot:** absence-pattern rule types (`missing_paired_action`, `missing_followup_visit`) that watch for the *absence* of an expected event within a window. They require SDK-side timer infrastructure (new Room table, restart-recovery on app kill, rule-update propagation to in-flight timers, age-bucket derivation from DOB without shipping raw DOB). The design space is real but underspec'd today, and the immediate-fire rules already deliver the complete pilot loop (CHW picks wrong tier → corrective module surfaces tomorrow). See [§8 Out of scope](#8-out-of-scope-on-this-branch-dont-redo).

### 4.3 Server-side validator (new file)

Mirror the existing pattern at `services/platform/src/platform_service/services/prompts/trigger_predicate_schemas.py`. Hand-rolled, one schema per `rule_type`, validators return a clear error on the offending field. Do **not** pull in `jsonschema`.

New file: `services/platform/src/platform_service/services/detection_rule_schemas.py`

```python
RULE_TYPES: frozenset[str] = frozenset({
    "wrong_facility_tier",
    "bp_above_threshold_no_referral",
    "glucose_above_threshold_no_referral",
    "missing_danger_signs_record",
})

def validate_detection_rule(payload: dict[str, Any]) -> None:
    """Raises DetectionRuleValidationError on invalid input.

    For 4 rule types, an inline if/elif dispatcher (~30 lines total) is
    clearer than a per-type schema dict. Each branch validates its 1-2
    params.
    """
```

Wire this into:
- `bin/seed_behavioural_gaps.py` — validate each rule before upsert (fail fast on seed load).
- Any future admin endpoint that edits `detection_rule_jsonb`.

**Pilot scope note:** for a hand-reviewed 16-row seed, the validator is a guardrail, not a blocker. See task B1 in §6 — it's marked optional.

### 4.4 One worked example (the flagship case)

`incorrect_referral_destination` gap, rule:

```json
{
  "schema_version": 1,
  "rule_type": "wrong_facility_tier",
  "params": {},
  "match": {
    "spice_event_codes": [
      "NCDAssessmentCreation",
      "RMNCHAssessment",
      "PNCMOTHERASSESSMENT"
    ]
  }
}
```

SDK behaviour for this rule: read `assessmentDetails` JSON's `REFERRAL_FACILITY_TYPE` key, look up the tier of the facility the CHW selected (from synced facility-list), compare. If they differ, emit `SPICE_ACTION_OBSERVED` with `payload_json.behavioural_gap_id = <this gap's UUID>` and `outcome = "incorrect"`.

---

## 5. Seed file — populate the pilot rules

File: `seed/behavioural_gaps_pilot.json`.

Currently every entry has `detection_rule_jsonb` omitted (loader defaults to `{}`). Update with the verified mapping table:

| gap_code | rule_type | Status | Notes |
|---|---|---|---|
| `incorrect_referral_destination` | `wrong_facility_tier` | **Pilot** | Flagship. Ready after C-SDK-6 (hook timing). |
| `missed_hypertension_referral_threshold` | `bp_above_threshold_no_referral` | **Pilot** | Params: 140/90. Open: drop "with symptoms" / "in pregnancy" qualifiers (C1). |
| `diabetes_referral_threshold_missed` | `glucose_above_threshold_no_referral` | **Pilot** | Threshold pending C2 (seed=11.1 vs SPICE=15). |
| `neonatal_danger_signs_missed` | `missing_danger_signs_record` | **Pilot** | Scope: `RMNCHNeonateAssessment` only. Pending C3 (key name). |
| `danger_signs_documentation_skipped` | `missing_danger_signs_record` | **Pilot** | Broad scope across all assessment types. Pending C3. |
| `incorrect_bp_measurement_protocol` | (empty — quiz-only) | **Pilot** | SPICE captures `avgSystolic`, not protocol adherence. Fed via quiz path. |
| `incorrect_iycf_counselling` | (empty — quiz-only) | **Pilot** | Counselling content audit not in SPICE payload. Quiz path. |
| `family_planning_method_mismatch` | (empty — quiz-only) | **Pilot** | No FP event in SPICE catalog. Quiz path. |
| `tb_symptom_screening_missed` | (empty — quiz-only) | **Pilot** | No TB event in SPICE catalog. Quiz path. |
| `incorrect_ors_zinc_protocol` | (empty — quiz-only) | **Pilot** | ICCM payload not surveyed. Quiz path. |
| `missed_referral_for_danger_signs` | TBD | **Deferred** | Needs new rule type combining danger-sign + no-referral. Re-evaluate post-pilot. |
| `missed_anc_visit_followup` | `missing_followup_visit` | **Deferred** | Absence-pattern; post-pilot. |
| `anc_danger_signs_education_gap` | `missing_paired_action` | **Deferred** | Absence-pattern; post-pilot. |
| `incomplete_immunisation_schedule` | `missing_paired_action` | **Deferred** | Absence-pattern; post-pilot. |
| `missed_pnc_first_24h_visit` | `missing_followup_visit` | **Deferred** | Absence-pattern; post-pilot. |
| `missed_diabetes_screening` | `missing_paired_action` | **Deferred** | Absence-pattern; post-pilot. |

**Pilot coverage:** 5 SDK-derivable rules (`wrong_facility_tier`, `bp_above_threshold_no_referral`, `glucose_above_threshold_no_referral`, two `missing_danger_signs_record` scoped variants) + 5 quiz-only gaps = **10 gaps live in pilot**. 6 gaps deferred to post-pilot (require absence-pattern infrastructure or new rule types).

Quiz-only gaps don't need `detection_rule_jsonb` populated — they're fed via `module_completion_worker._handle_quiz_attempt` which already reads `module.primary_gap_id`. Leave their rule empty.

**Deferred gaps** stay in the seed (so they're queryable and bindable to modules via `module.primary_gap_id`) — they just don't fire from SPICE events. The module-suggestion path still works for them through the quiz route if a quiz module is bound.

---

## 6. Backend tasks remaining

| # | Task | File | Effort | Priority |
|---|---|---|---|---|
| B1 | Update `seed/behavioural_gaps_pilot.json` with the 5 action-derivable rules (Section 5) | edit | half day after Phase-0 confirmations | **Required** |
| B2 | Integration test: synthetic `SPICE_ACTION_OBSERVED` → state increment → `ModuleSuggestionService` surfaces correct module | `tests/integration/test_spice_observation_end_to_end.py` (new) | 1 day | **Required** |
| B3 | Fix stale `_comment` field in `seed/behavioural_gaps_pilot.json` — currently references Stage C gap-list context which Architecture Reset removed | edit | <15 min | **Required** |
| B4 | Author `detection_rule_schemas.py` validator (Section 4.3) | new | half day | **Optional** — defer unless seed-load surfaces a bug, or until a future admin-edit endpoint lands |
| B5 | Admin endpoint `POST /admin/v3/gaps/:id/detection-rule/validate` (dry-run a candidate rule) | new endpoint | 1 day | **Post-pilot** |

**Do NOT** add (each has a verified reason):

- **Server-side predicate evaluator.** The SDK does that.
- **A separate gap-detection worker.** The existing handler in `module_completion_worker.py` is the gap-detection worker.
- **Drop of `detection_rule_jsonb`.** Already wired through `sync_service`; keep it.
- **Worker-level event-id idempotency / `last_processed_event_id` migration.** Redis SET-NX dedup in `services/telemetry_dedup.py` (24h TTL) filters retries *before* Celery enqueue (`api/telemetry.py:168`). The existing test `test_spice_action_observed_second_event_increments_occurrence_count` confirms behaviour. Worker-level dedup is solving a non-problem.

---

## 7. Open questions (resolve before B1)

These need answers from clinical lead and SPICE Android lead. Block on these *only* for the rules whose params depend on them — others can proceed in parallel.

| ID | Question | Owner | Blocks |
|---|---|---|---|
| C1 | `missed_hypertension_referral_threshold`: drop "with symptoms" qualifier (SPICE has no such gate)? Drop "in pregnancy" qualifier (SPICE uses same 160/100 for everyone)? | Clinical lead | B1 (1 rule) |
| C2 | `diabetes_referral_threshold_missed`: seed=11.1 (WHO diagnostic), SPICE escalates at 15. Which is the gap's intent? | Clinical lead | B1 (1 rule) |
| C3 | Danger-signs key — is it `dangerSigns` in `assessmentDetails`? Same key across NCD/RMNCH/PNC? | SPICE Android lead | B1 (2 rules) |

Other questions in the SDK doc (C-SDK-1 through C-SDK-6) belong to the SDK side — they don't block backend seed population, though they do block end-to-end testing.

---

## 8. Out of scope on this branch (don't redo)

Already done on `telemetry` branch:

- The handler in `module_completion_worker` SPICE branch — done in `cd41f2a`.
- `ModuleSuggestionService` ranking — done in `2eb11ff`.
- ClickHouse UUID refactor — done in `04b592d`.
- Sync API for gaps bundle — done in `8392a77`.
- The gap-state machine itself (`GapStateService`) — done in W-8.

**Deferred to post-pilot** (do not build now):

- **Absence-pattern rule types** (`missing_paired_action`, `missing_followup_visit`). They require SDK-side timer infrastructure (new Room table, app-kill recovery, sync-time rule-change semantics for in-flight timers, age-bucket derivation). Re-evaluate after pilot ships with the 5 immediate-fire rules. The 6 deferred gaps in §5 land here.
- **Server-side rule validator** (B4) — only needed when admin-edit endpoints land.
- **Admin dry-run endpoint** (B5).
- **Rule-type collapse refactor**: `bp_above_threshold_no_referral` and `glucose_above_threshold_no_referral` differ only in field name + unit. A future `vital_above_threshold_no_referral` with a `vital_type` param would collapse them. Not blocking pilot.

The remaining required work is **B1 (seed population), B2 (integration test), B3 (seed comment fix)**. Everything else is bookkeeping or post-pilot.
