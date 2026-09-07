# PII boundary

Patient names and phone numbers must not reach the backend. Hash `patientId` to `patient_id_hash` before any backend call.

## What can cross into the SDK

| Field | Crosses into the SDK? |
|---|---|
| `chwId` | yes |
| `patientId` | yes. Hash before any backend call. |
| `encounterId` | yes |
| Age, gender, vital values, risk flags | yes, through a documented `assessmentData` allowlist |
| `village_id` | yes when known |
| `name` | no |
| `phoneNumber` | no |
| `nationalId` | no |
| `dateOfBirth` | no |
| Free-text address | no |

The SDK does not accept a household member object.

## Telemetry rule

Personal identifiers must not appear on any event. Use `patient_id_hash` (SHA-256 hex of SPICE `patientId`).

Geo mapping for Bangladesh-labelled fields:

| SPICE-generic | Bangladesh UI label | Telemetry field |
|---|---|---|
| Chiefdom | Upazila | `upazila_id` |
| Village | Union | `village_id` |

## Next step

[Detection rules](detection-rules.md)
