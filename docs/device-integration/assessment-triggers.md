# Assessment-due predicates

Devices evaluate `predicate_jsonb` after `GET /sync/triggers`. Triggers use `trigger_kind=workflow_event` and `trigger_code=wf:assessment_due:{topic}`.

**Before you start:** Load due follow-up rows from SPICE `POST /follow-up/list`. Fallback source is due patients from SPICE `POST /patient/list`.

## Predicate shape

```json
{
  "spice_event_code": "assessment_due",
  "filter_predicate": {
    "assessment_topic": "malaria",
    "match": {
      "encounter_type_any": ["MALARIA"],
      "reason_any": ["MALARIA"],
      "reason_display_any": ["Malaria", "Severe Malaria", "Uncomplicated Malaria"],
      "diagnosis_any": ["MALARIA", "SEVERE_MALARIA", "SEVEREMALARIA"],
      "patient_status_any": ["malaria"],
      "appointment_type_any": ["HH_VISIT", "REFERRED", "MEDICAL_REVIEW"],
      "encounter_program_any": ["ICCM"],
      "encounter_name_any": [],
      "is_pregnant": null,
      "max_age": null,
      "min_age": null
    }
  }
}
```

Canonical definitions live in `seed/assessment_due_triggers.json`.

A predicate matches when **any** contributing clause is true (OR across clauses). Empty lists and null demographic bounds do not contribute a clause.

## SPICE field mapping

| `match` evaluation | Follow-up row | Patient row | Platform snapshot |
|---|---|---|---|
| `encounter_type_any` | — | `type` | `encounter_type` |
| `encounter_program_any` | `encounterType` | — | `encounter_program` |
| `encounter_name_any` | `encounterName` | — | `encounter_name` |
| `appointment_type_any` | `type` | — | `appointment_type` |
| `reason_display_any` | `reason` | — | `reason` |
| `reason_any` | — | `reason` | `reason` |
| `diagnosis_any` | — | `diagnosisType[]` | `diagnosis_types` |
| `patient_status_any` | `patientStatus` | `patientStatus` | `patient_status` |
| `is_pregnant` | — | `isPregnant` | `is_pregnant` |
| `max_age` / `min_age` | `age` | `age` | `age` |

Token fields are compared case-insensitively after uppercasing and normalizing spaces to underscores. `reason_display_any` splits `reason` on commas and compares trimmed segments.

## Match semantics

A due patient or follow-up row matches when any contributing clause is true:

1. `encounter_type` is listed in `encounter_type_any`, or normalizes to `assessment_topic`.
2. Any comma-separated `reason` segment is listed in `reason_display_any`.
3. `reason` is listed in `reason_any`, or normalizes to `assessment_topic`.
4. Any diagnosis is listed in `diagnosis_any`, or normalizes to `assessment_topic`.
5. Normalized `patient_status` equals `assessment_topic`, or is listed in `patient_status_any`.
6. `encounter_name` is listed in `encounter_name_any`.
7. Program is listed in `encounter_program_any`.
8. `appointment_type` is listed in `appointment_type_any`.
9. `is_pregnant` is `true` and the patient is pregnant.
10. `max_age` is set and `age <= max_age`.
11. `min_age` is set and `age >= min_age`.

## Bindings

1. Call `GET /sync/triggers?since=...`.
2. Persist `predicate_jsonb` locally.
3. For each due follow-up row, evaluate predicates where `spice_event_code` is `assessment_due`.
4. Use `module_trigger_binding` rows to resolve coaching modules for fired trigger codes.

Bindings are module-level. Each binding references `module_id` for a specific published module content version.

Canonical seed JSON lives in `seed/assessment_due_triggers.json`.

## Next step

[Gaps and assessment triggers](../device-coaching/gaps-and-triggers.md)
