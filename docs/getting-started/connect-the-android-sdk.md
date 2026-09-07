# Connect the Android SDK

The MicroCoaching Android SDK is a standalone library. The SPICE app embeds it. The SDK talks only to platform-api.

**Before you start:** Read [Authentication](../device-integration/authentication.md) and [PII boundary](../device-integration/pii-boundary.md). The SPICE host app must add the SDK Gradle dependency and call the SDK builder once in `Application.onCreate()`. Confirm exact lifecycle hook names with the SPICE Android team. See [SPICE host app contract](../device-integration/spice-host-app.md).

## Send auth headers

On every device call, send:

1. `Authorization: Bearer <jwt>`
2. `client: mob`

Platform forwards these headers to SPICE `POST /authenticate` when `SPICE_AUTH_ENABLED=true`.

When `SPICE_AUTH_ENABLED=false` (local Compose), you can call device routes without a JWT.

## First successful sync

1. Call `GET /sync/config`. Cache `locales.primary`.
2. Call `GET /sync/modules?since=<ISO-8601>`. Use a far-past timestamp on first pull.
3. Call the remaining sync routes your build needs (card embeddings for EDGE mode, documents, triggers, gaps, FAQs, badges). See [Sync content for offline use](../device-coaching/sync-content.md).

**Result:** The device can render published modules offline. Do not call ai-runtime. Devices must not call `/internal/*` routes.

## Next step

[Sync content for offline use](../device-coaching/sync-content.md)
