# Detection rules

Devices evaluate `behavioural_gap.detection_rule_jsonb` after `GET /sync/gaps`. Referral gaps use evaluator `spice_referral_compliance`.

A gap fires only when the rule engine recommended one action and the CHW did a different action.

## Rule object

```json
{
  "schema_version": 1,
  "evaluator": "spice_referral_compliance",
  "when": { "op": "and", "conditions": [] },
  "metadata": {}
}
```

| Field | Required | Description |
|---|---|---|
| `schema_version` | yes | Must be `1` |
| `evaluator` | yes | Must be `spice_referral_compliance` |
| `when` | yes | Root predicate |
| `metadata` | no | Reviewer hints. The evaluator ignores this field. |

## Build visit state first

| Branch | Source | Keys |
|---|---|---|
| `recommended` | Rule engine at screening or assessment complete | `isReferred`, `referralStatus`, `referredReason`, `referralUrgency`, `referralFacilityType`, nested `assessmentDetails.*` |
| `actual` | CHW referral submission | `didRefer`, `isUrgent`, `referralReasons`, `destinationTier`, `referredSiteId`, `referralFacilityType` |

Path prefix selects the branch. Example: `recommended.referredReason`.

The gap fires when `when` is true. Matching recommendation plus matching CHW choice does not fire the gap.

## Logical combinators

| `op` | Fields | True when |
|---|---|---|
| `and` | `conditions` | All children true |
| `or` | `conditions` | Any child true |
| `not` | `condition` | Child false |

## Recommendation operators

| `op` | Fields | True when |
|---|---|---|
| `eq` | `path`, `value` | Resolved value equals `value` |
| `neq` | `path`, `value` | Resolved value differs from `value` |
| `exists` | `path` | Non-null, non-empty |
| `contains_any` | `path`, `values` | List at `path` intersects `values` |
| `contains_all` | `path`, `values` | List contains every value |
| `array_nonempty` | `path` | List length greater than 0 |
| `map_key_nonempty` | `path`, `key` | Map at `path` has a non-empty list at `key` |
| `array_contains_substring` | `path`, `value` | Any list element contains the substring |

## Mismatch operators

| `op` | Fields | True when |
|---|---|---|
| `missed_referral` | — | `recommended.isReferred` is true and `actual.didRefer` is false |
| `mismatch_eq` | `recommended_path`, `actual_path` | Values differ, including one null |
| `mismatch_contains_any` | `recommended_path`, `actual_path`, `values` | Recommended list intersects `values`, actual list does not |
| `mismatch_urgency` | `recommended_urgency`, `actual_path` | Rule-engine urgency does not match `actual.isUrgent` |

`URGENT` maps to `actual.isUrgent == true`. `NON_URGENT` maps to `actual.isUrgent == false`.

## Typical gap pattern

This fires when the rule engine recommended pneumonia or cough referral and the CHW did not refer, or referred with reasons that omit that cluster.

```json
{
  "schema_version": 1,
  "evaluator": "spice_referral_compliance",
  "when": {
    "op": "or",
    "conditions": [
      {
        "op": "and",
        "conditions": [
          {
            "op": "contains_any",
            "path": "recommended.referredReason",
            "values": ["Pneumonia", "Cough"]
          },
          { "op": "missed_referral" }
        ]
      },
      {
        "op": "mismatch_contains_any",
        "recommended_path": "recommended.referredReason",
        "actual_path": "actual.referralReasons",
        "values": ["Pneumonia", "Cough"]
      }
    ]
  }
}
```

## Seed data

Canonical rows live in `seed/behavioural_gaps_referral.json`. Alembic loads these rows on `alembic upgrade head`.

## Next step

[Assessment-due predicates](assessment-triggers.md)
