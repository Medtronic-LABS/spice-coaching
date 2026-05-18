# Gap Detection — Android SDK Guide

Audience: Charles (and anyone building the SDK-side gap-detection logic in `micro-coaching-android-sdk` or its integration into SPICE on `uhis-dev`).

Companion doc for the backend: [`GAP_DETECTION_BACKEND.md`](./GAP_DETECTION_BACKEND.md). Read both — they describe two sides of the same contract.

---

## 1. What the backend expects from you

Your job: at each SPICE workflow event, decide whether the action observed indicates a known behavioural gap. If yes, emit a telemetry event with the gap tagged. The backend just counts.

Contract for a tagged event sent to `POST /telemetry/events`:

```json
{
  "id": "<uuid>",
  "event_family": "clinical_observed",
  "event_type": "spice_action_observed",
  "session_id": "<uuid>",
  "patient_id_hash": "<sha256(patientId)>",
  "clinical_domain": "hypertension | diabetes | maternal_health | emergency | spice_digital",
  "trigger_type": "user_action",
  "outcome": "correct | incorrect | wrong | unknown",
  "timestamp_utc": "...",
  "payload_json": {
    "behavioural_gap_id": "<uuid — matches a row in the synced gaps bundle>",
    "spice_event_code": "<from AnalyticsDefinedParams, e.g. NCDAssessmentCreation>",
    "assessment_type": "NCD | RMNCH | ICCM | TB | CBS",
    "rule_type": "<the rule_type that fired — for debuggability>",
    "evidence": { ... small de-identified payload — see §5 ... }
  }
}
```

What the backend does with this:

| Field | Read by backend state machine? | Stored to ClickHouse? | Purpose |
|---|---|---|---|
| `behavioural_gap_id` | **Yes** | Yes | Bumps `chw_behavioural_gap_state.occurrence_count` for `(chw_id, behavioural_gap_id)` (`module_completion_worker` SPICE branch, commit `cd41f2a`). |
| `outcome` (top-level or in payload_json) | **Yes** | Yes | If `wrong` or `incorrect`, bumps `failed_attempts_count` and may trigger supervisor escalation. Other values are no-ops. |
| `spice_event_code` | No | Yes | Audit / debugging — which SPICE workflow triggered. |
| `assessment_type` | No | Yes | Audit / debugging — which pathway (NCD / RMNCH / etc.). |
| `rule_type` | No | Yes | QA replay — which rule fired. Useful when investigating false positives. |
| `evidence` | No | Yes | Audit — the de-identified inputs your rule saw. Keep small. |

The non-state fields ship to `coaching_events` ClickHouse table via the existing telemetry pipeline. They don't affect platform state but are essential for QA, observability, and post-deploy investigation. Do not skip them.

**Multiple gaps can fire on one SPICE event.** Emit one telemetry event per fired gap.

---

## 2. Verified SPICE 2.0 `uhis-dev` contract

All references against `origin/uhis-dev` at commit `5043a97a0602`. Verified directly from source by reading `git show origin/uhis-dev:<path>`.

### 2.1 The bridge: `REFERRAL_FACILITY_TYPE`

`Spice-SL/app/src/main/java/org/medtroniclabs/uhis/ui/assessment/AssessmentDefinedParams.kt`:

```
L503: const val REFERRAL_FACILITY_TYPE = "referralFacilityType"
L507: const val FACILITY_TYPE_UPAZILA = "Upazila Health Complex"
L509: const val FACILITY_TYPE_COMMUNITY_CLINIC = "Community Clinic"
L553: const val ID_CHILD_REFERRAL_FACILITY_TYPE = "childReferralFacilityType"
```

SPICE pre-computes the *expected* facility tier and writes it into the assessment map **before** the CHW selects a facility. See `ReferralResultGenerator.kt:631-683` — `computeReferralResultForBDNCD` writes `map[REFERRAL_FACILITY_TYPE] = "Upazila Health Complex" | "Community Clinic"` based on BP/BG severity. This key lands in `AssessmentEntity.assessmentDetails` (JSON String) when the form is persisted.

**This is the load-bearing fact for `wrong_facility_tier` detection.** Read `REFERRAL_FACILITY_TYPE` from the assessment map; compare against the CHW's actual selection.

### 2.2 Verified threshold constants

`Spice-SL/app/src/main/java/org/medtroniclabs/uhis/ui/assessment/AssessmentDefinedParams.kt`:

| Constant | Value | Meaning |
|---|---|---|
| `UpperLimitSystolic` (L96) | **140** | Triggers referral (Community Clinic tier) |
| `UpperLimitDiastolic` (L97) | **90** | Triggers referral (Community Clinic tier) |
| `UPAZILA_UPPER_LIMIT_SYSTOLIC` (L526) | **160** | Escalates to Upazila tier |
| `UPAZILA_UPPER_LIMIT_DIASTOLIC` (L527) | **100** | Escalates to Upazila tier |
| `UPAZILA_FBS_RBS_MAXIMUM_VALUE_BD` (L524) | **15** mmol/L | Glucose → Upazila tier |

Use these constants directly. Do **not** hardcode numbers in SDK code — import from `AssessmentDefinedParams` so any SPICE update flows through.

### 2.3 Assessment payload structure

`AssessmentEntity.kt`:

```kotlin
@Entity(tableName = ASSESSMENT)
data class AssessmentEntity(
    val assessmentType: String,        // "NCD" | "RMNCH" | "ICCM" | "TB" | "CBS"
    var assessmentDetails: String,     // JSON blob — keys vary per assessmentType
    var isReferred: Boolean = false,
    val referralStatus: ReferralStatus,// Referred | OnTreatment | Recovered | Died
    val referredReason: ArrayList<String>?,
    ...
)
```

**Single JSON-string column, per-pathway key set.** No schema enforcement. Keys you can rely on for NCD assessments (confirmed via `AssessmentRepository.kt:70` + `CVDRiskCalculator.kt:30-37`):

- `bpLog` (nested map with `avgSystolic`, `avgDiastolic`, `bmi`, `isRegularSmoker`)
- `cvdRiskScore` (Int)
- `cvdRiskLevel` (String — "Low" / "Moderate" / "High")
- `cvdRiskScoreDisplay` (String)
- `fbsBloodGlucose` / `rbsBloodGlucose`
- `phq4Score`
- `REFERRAL_FACILITY_TYPE` (String — populated by `ReferralResultGenerator`)

For RMNCH/PNC/ICCM/TB: **keys are not constant-listed anywhere.** This is open question C-SDK-1 below.

### 2.4 Analytics events catalog

`Spice-SL/analytics/.../AnalyticsDefinedParams.kt` — 45+ event names. Key clinical events you'll watch:

| Workflow | Event constants |
|---|---|
| Assessment (the main trigger) | `NCDAssessmentCreation`, `RMNCHAssessment`, `PNCMOTHERASSESSMENT`, `RMNCHNeonateAssessment`, `RMNCHCHILDASSESSMENT` |
| Vitals | `NCDBloodPressureCreation`, `NCDBloodGlucoseCreation` |
| Counselling | `NCDLifestyleManagementCreation`, `NCDCounselorCreation` |
| Diagnosis | `NCDConfirmDiagnosisCreation`, `NCDPatientHistoryCreationFor{NCD,MaternalHealth,MentalHealth}` |
| Schedule / follow-up | `NCDScheduleCreation`, `NCDCallInitialed`, `NCDCallResult` |
| Pregnancy | `NCDUpdatePregnancyRisk` |

**Critical caveat:** the analytics `parameter` JSON (per-event payload as stored in the `analytics` Room table) does **not** carry clinical content — only `StartTime`, `EndTime`, `IsCompleted`, `ExitReason`, `ApiId`, `ReferenceId`, `UserJourney`. To get clinical data (BP value, glucose value, selected facility), you must read the underlying clinical record referenced by `ReferenceId` (e.g., the `AssessmentEntity` row).

This is the right design: SPICE's analytics layer doesn't carry PII. Your SDK code runs in-process and can read the assessment map directly *before* SPICE persists it — that's the integration point.

---

## 3. Sync contract — receiving rules from the backend

Endpoint: as already defined in `sync_service.get_gaps_bundle()`. Wire type: `BehaviouralGapSyncPayload` (`mc_contracts.sync`):

```python
class BehaviouralGapSyncPayload(BaseModel):
    id: UUID
    gap_code: str
    description: str
    domain: str
    severity_default: str
    detection_rule_jsonb: dict[str, Any]   # ← the rule
    updated_at: datetime
```

The `detection_rule_jsonb` envelope (defined in [`GAP_DETECTION_BACKEND.md` §4.1](./GAP_DETECTION_BACKEND.md)):

```json
{
  "schema_version": 1,
  "rule_type": "<one of: wrong_facility_tier | bp_above_threshold_no_referral | glucose_above_threshold_no_referral | missing_danger_signs_record | missing_paired_action | missing_followup_visit>",
  "params": { ... rule-type-specific ... },
  "match": {
    "spice_event_codes": [...],
    "assessment_types": [...]
  }
}
```

**Forward-compat rule:** if `schema_version > 1`, skip this rule and log a warning. Don't crash. The server will roll new schema versions when it needs to.

Rules with empty `detection_rule_jsonb` (i.e., `{}`) are quiz-only — ignore them on the action-derivation path. They get fed from the backend's `module_completion_worker._handle_quiz_attempt`, not from you.

---

## 4. Per-`rule_type` evaluation logic

One Kotlin function per `rule_type`. Dispatch with a `when`. Each function returns `Boolean` (does this rule fire on this event?) plus the `outcome` value to send.

**Pilot scope: 4 immediate-fire rule types.** Absence-pattern rules (timers / pending state) are deferred to post-pilot — see §8.

### 4.1 `wrong_facility_tier`

**Trigger:** SPICE event matches `match.spice_event_codes`.

**Read:**
- `assessmentDetails[REFERRAL_FACILITY_TYPE]` — the *expected* tier ("Upazila Health Complex" / "Community Clinic")
- The CHW's selected facility ID from `ReferPatientResult.referredSiteId`
- Look up that facility's tier from the synced facility list (admin-web ships facility records with a `type` String per the survey of `spice-2.0-admin-web@uhis-dev` — `services/healthFacilityAPI.ts:108`)

**Fire when:** expected tier non-null AND selected facility tier != expected. `outcome = "incorrect"`.

**Evidence to ship:** `{"expected_tier": "...", "actual_tier": "...", "facility_id_hash": "sha256(referredSiteId)"}`. Note: hash the facility id; it's not strictly PII but treat as such to keep the boundary tight.

### 4.2 `bp_above_threshold_no_referral`

**Trigger:** SPICE event matches.

**Read:**
- `assessmentDetails["bpLog"]["avgSystolic"]` and `avgDiastolic`
- `AssessmentEntity.isReferred`

**Fire when:** systolic ≥ `params.systolic_threshold` OR diastolic ≥ `params.diastolic_threshold`, AND `isReferred == false`. `outcome = "incorrect"`.

**Evidence:** `{"avg_systolic": 162, "avg_diastolic": 98, "is_referred": false}`.

### 4.3 `glucose_above_threshold_no_referral`

**Trigger:** SPICE event matches.

**Read:** `assessmentDetails["rbsBloodGlucose"]` (or `fbsBloodGlucose` — confirm with C-SDK-1), `isReferred`.

**Fire when:** glucose value ≥ `params.threshold_mmol_l` AND `isReferred == false`. Beware unit conversion if SPICE stores in mg/dL on some forms.

### 4.4 `missing_danger_signs_record`

**Trigger:** SPICE event matches.

**Read:** `assessmentDetails["dangerSigns"]` (or whichever key SPICE uses — open question C-SDK-2).

**Fire when:** field is null, missing, or empty array. `outcome = "incorrect"` (low severity — documentation skip, not a clinical decision).

---

## 5. PII boundary

This is the load-bearing trust contract. W12 §"PII boundary is easier to audit at the SPICE call-site" — verified to be SDK-enforced, not SPICE-enforced. Get it right.

### 5.1 Always hash before sending

- `patientId` → SHA-256 → `patient_id_hash`
- `referredSiteId` (facility identifier) → SHA-256 → `facility_id_hash`
- `householdId`, `memberId` → if you need to send them, hash. If you don't need them, don't send them.

### 5.2 Never send

- Patient name, phone number, national ID, address
- GPS coordinates from `AssessmentEntity.latitude`, `longitude`
- CHW free-text fields (`ReferPatientResult.referredReason` — this is open free-text, drop it; the gap fires on the structured `REFERRAL_FACILITY_TYPE`, not the CHW's prose)

### 5.3 Send (de-identified)

- `chw_id` — your CHW identifier (already a UUID, not PII)
- `tenant_id`
- Enum codes: `assessmentType`, `spice_event_code`, `clinical_domain`, `outcome`
- Numeric clinical values: BP, glucose, age (bucketed to age group, not raw years)
- Boolean flags: `is_referred`, `is_pregnant`

### 5.4 Evidence payload size budget

Keep `payload_json.evidence` under 2 KB. Backend stores it but doesn't parse it. If you need more, ship a hash of the underlying SPICE record and rely on SPICE's own analytics for audit.

### 5.5 Where the boundary is enforced

PII enforcement is a **call-site responsibility**, not framework-enforced. The SDK telemetry serializer does **not** redact or validate `evidence`. Concrete expectations:

- Each rule evaluator that builds an `evidence` map MUST route any identifier through the SDK's hashing helper (e.g. `AnalyticsUtils.sha256(...)` or the equivalent coaching-SDK util) — never include raw `patientId` / `referredSiteId` / `householdId` / `memberId`.
- Code review on every new rule type checks the `evidence` map construction. Add a checklist item to the SDK's PR template.
- QA must spot-check generated telemetry events against the §5.2 "never send" list. If raw PII is found, treat as a security incident.

The reason for call-site enforcement (rather than a serializer-level allowlist): rule evaluators legitimately need *some* hashed identifiers (e.g. `facility_id_hash` for `wrong_facility_tier` audit) but the set varies per rule. A central allowlist would either be too permissive (defeats the point) or too restrictive (breaks evidence richness). The trust boundary is each rule evaluator's `buildEvidence()` function.

---

## 6. The 16 pilot gaps — mapping table

Three statuses per gap:
- **PILOT** — implement now. The SDK fires this rule on matching SPICE events.
- **SKIP (quiz-only)** — no SPICE telemetry signal; the backend handles via the quiz path. Nothing for you to build.
- **DEFER (post-pilot)** — absence-pattern or undefined rule type. Don't build until after pilot ships.

The `Unblocked?` column captures whether open questions block the rule from being coded.

| gap_code | Status | rule_type | Unblocked? | Notes |
|---|---|---|---|---|
| `incorrect_referral_destination` | **PILOT** | `wrong_facility_tier` | After C-SDK-6 | Flagship. Demos the whole loop. |
| `missed_hypertension_referral_threshold` | **PILOT** | `bp_above_threshold_no_referral` | Yes | Params 140/90 from backend |
| `diabetes_referral_threshold_missed` | **PILOT** | `glucose_above_threshold_no_referral` | After C-SDK-1 | Threshold pending clinical-lead C2 |
| `neonatal_danger_signs_missed` | **PILOT** | `missing_danger_signs_record` | After C-SDK-2 | Scope: `RMNCHNeonateAssessment` |
| `danger_signs_documentation_skipped` | **PILOT** | `missing_danger_signs_record` | After C-SDK-2 | Broad scope across assessment types |
| `incorrect_bp_measurement_protocol` | **SKIP** | quiz-only | n/a | SPICE doesn't capture protocol adherence |
| `incorrect_iycf_counselling` | **SKIP** | quiz-only | n/a | Counselling content audit not in SPICE payload |
| `family_planning_method_mismatch` | **SKIP** | quiz-only | n/a | No FP event in SPICE catalog (confirm C-SDK-4) |
| `tb_symptom_screening_missed` | **SKIP** | quiz-only | n/a | No TB event in SPICE catalog (confirm C-SDK-4) |
| `incorrect_ors_zinc_protocol` | **SKIP** | quiz-only | n/a | ICCM payload not surveyed; probably out of scope |
| `missed_referral_for_danger_signs` | **DEFER** | TBD | — | Needs new rule type; re-evaluate post-pilot |
| `missed_anc_visit_followup` | **DEFER** | `missing_followup_visit` | — | Absence-pattern; post-pilot |
| `anc_danger_signs_education_gap` | **DEFER** | `missing_paired_action` | — | Absence-pattern; post-pilot |
| `incomplete_immunisation_schedule` | **DEFER** | `missing_paired_action` | — | Absence-pattern; post-pilot |
| `missed_pnc_first_24h_visit` | **DEFER** | `missing_followup_visit` | — | Absence-pattern; post-pilot |
| `missed_diabetes_screening` | **DEFER** | `missing_paired_action` | — | Absence-pattern; post-pilot |

Result: **5 PILOT** (all immediate-fire), **5 SKIP** (quiz-only), **6 DEFER** (post-pilot). The 5 SKIP gaps still surface modules via the backend's quiz-fail path; you don't need to do anything for them.

**Build order for the 5 PILOT rules:**
1. `incorrect_referral_destination` (flagship — exercises the whole pipeline end-to-end)
2. `missed_hypertension_referral_threshold` (no blocking question)
3. `danger_signs_documentation_skipped` + `neonatal_danger_signs_missed` (paired — same rule type, two scopes)
4. `diabetes_referral_threshold_missed` (after threshold confirmed)

---

## 7. Open questions for SPICE Android lead

These must be confirmed before you can fully wire the pilot rules. Most are key-name confirmations from the SPICE codebase — quick to answer.

| ID | Question | Blocks |
|---|---|---|
| C-SDK-1 | What's the exact key for fasting vs random glucose? Are they both populated, or one or the other per workflow? | `glucose_above_threshold_no_referral` |
| C-SDK-2 | What key holds the danger-signs list in `assessmentDetails`? Same key across NCD / RMNCH / Neonate? | `missing_danger_signs_record` (2 scoped variants) |
| C-SDK-6 | The `onAssessmentSubmitted` lifecycle hook timing — does the SDK get called **before** SPICE persists the AssessmentEntity, or **after**? (Matters for whether you can compare `REFERRAL_FACILITY_TYPE` against `ReferPatientResult` in one pass.) | `wrong_facility_tier` integration timing |

W12 §C1 listed the `assessmentData` allowlist as TEAM-CONFIRM. C-SDK-1, -2, -6 close it for the pilot rules. The other questions from earlier drafts (immunisation event name, FP/TB events, age bucketing) are **deferred** — they relate to absence-pattern rules which are post-pilot.

---

## 8. Absence-pattern rules — deferred to post-pilot

Six of the 16 gaps (see §6 DEFER rows) need *absence* detection: an expected event didn't fire within a window (e.g., adult assessment without glucose check, delivery without PNC visit in 24h). The mental model is right; the build is not justified yet.

**Why deferred:**
- Underspec'd: timer storage keys, paired-event matching semantics (must patient IDs match?), age-bucket derivation (open question C-SDK-5) without shipping raw DOB, rule-update propagation to in-flight timers, app-kill / restart recovery — each needs a real design decision.
- Not on the critical pilot path: the 5 immediate-fire rules deliver the complete demo loop. Adding absence patterns roughly doubles SDK scope for diminishing pilot value.
- Better to design with concrete data: after pilot ships, we'll know which CHW workflows actually skip these paired actions, what the timeout distributions look like, and whether the value justifies the complexity.

**What this means for you now:** ignore rule entries with `rule_type ∈ {"missing_paired_action", "missing_followup_visit"}` in synced rules. They won't be present in the pilot seed — but if a future sync ships one, the safe behaviour is "log and skip" (same as a `schema_version > 1` rule).

**When we come back to this** (post-pilot iteration): design as a separate doc, with the storage schema, restart recovery, rule-update semantics, and the C-SDK-5 age-bucket resolution all settled before any code is written.

---

## 9. Out of scope on the SDK side

- Server-side rule evaluation. Backend just counts.
- PII de-identification on the backend. You enforce the boundary at the call site.
- Module selection / surfacing. The backend's `ModuleSuggestionService` does that; you just consume the suggestions via the existing morning-cards API.
- Quiz-derived gap state. Quiz events flow through the existing `MODULE_QUIZ_ATTEMPTED` path; you don't need to special-case them.

---

## 10. Phase ordering — what to build first

1. **Sync consumer.** Wire `BehaviouralGapSyncPayload` parsing and local Room persistence. Skip rules with `schema_version > 1`, empty `detection_rule_jsonb`, or unknown `rule_type` (including the deferred absence-pattern types). Log skips so QA can audit coverage.
2. **`wrong_facility_tier`.** Flagship rule. Verifies the whole pipeline end-to-end: read assessment map → compare → emit tagged event → backend counts → `ModuleSuggestionService` surfaces a corrective module. **Demo gate** — after this works on a test device, the pilot architecture is proven.
3. **`bp_above_threshold_no_referral` + `glucose_above_threshold_no_referral`.** Two more immediate-fire rules; same pattern. `bp` is unblocked; `glucose` waits on clinical-lead C2 + SPICE-lead C-SDK-1.
4. **`missing_danger_signs_record`** (two scoped variants: neonatal + cross-pathway). Once C-SDK-2 is answered.

After step 2 you should be able to demo: CHW picks wrong facility tier in a SPICE referral → app shows a "morning card" the next day correcting it. That's the whole loop. Absence patterns are explicitly post-pilot — see §8.
