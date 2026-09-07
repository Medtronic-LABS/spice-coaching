# SPICE host app contract

The MicroCoaching Android SDK is a standalone library. The SPICE app embeds it. The SDK runs in-process with SPICE.

The SDK owns its UI, its data, its decisions, its telemetry, and its on-device inference. SPICE does not hand business logic or rule-engine output as a shared database. SPICE hands identifiers through lifecycle hooks. SPICE places SDK UI into containers it provides.

## Repositories

| Repository | Role |
|---|---|
| `spice-coaching` (this repo) | Backend. Content pipeline, sync API, telemetry ingest, admin API. |
| MicroCoaching Android SDK | Android library. Sync cache, UI, telemetry, on-device inference. |
| SPICE Android | Host app. Adds the SDK as a Gradle dependency. |

## What SPICE must do

1. Add the Gradle dependency.
2. Call the SDK builder once in `Application.onCreate()`.
3. Place SDK UI components into chosen layout containers.
4. Call lifecycle hooks at known points.
5. Pass a SPICE JWT with `client: mob`.

SPICE hands identifiers through lifecycle hooks rather than shared analytics-database reads.

## Typical lifecycle hooks

- `onHomeScreenShown(chwId)`
- `onPatientSelected(patientId)`
- `onAssessmentSubmitted(encounterId, patientId, assessmentData)`
- `onScreeningCompleted(encounterId, patientId, outcome)`
- `onReferralSubmitted(encounterId, patientId, referralContext)`
- `onVitalThresholdCrossed(vital, value, threshold)`
- `onConnectivityRestored()`

Confirm exact key allowlists with the SPICE Android team before go-live.

## Data streams

| Need | Source | How |
|---|---|---|
| Module content | platform-api `/sync/*` | SDK WorkManager pull |
| Telemetry sink | platform-api `POST /telemetry/events` | SDK outbound flush |
| Patient context | SPICE lifecycle hooks | Identifiers and allowlisted assessment keys |
| Auth | SPICE JWT | `Authorization: Bearer` with `client: mob` |

The SDK talks only to platform-api. The SDK does not call ai-runtime.

Until the first successful sync, the SDK cannot render coaching cards from local cache. Card rendering, telemetry capture, lifecycle hooks, and Morning review selection do not need the on-device generation model. Telemetry flush and content sync need network. EDGE mode chat needs the on-device generation model.

## Next step

[Authentication](authentication.md)
