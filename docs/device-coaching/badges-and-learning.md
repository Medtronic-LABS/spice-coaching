# Badges and learning points

CHWs earn badges when they complete linked modules. Learning points accumulate from selected telemetry events.

**Before you start:** Admins must create badges with `module_ids` that reference published modules. See [Edit and publish modules](../content-administration/edit-and-publish.md).

## Sync badges

1. Call `GET /sync/badges`.
2. Show `available_badges` and `earned_badges`.

**Result:** Earned rows include `earned_at`. Image fields include optional presigned URLs.

Awards occur when telemetry processing newly completes a linked module version. Awards are not revoked later.

## Learning points

These event types insert learning-point rows:

- `module_delivered`
- `module_card_viewed`
- `module_quiz_attempted`
- `spice_action_observed`

The CHW total is the sum of points for that `chw_id`. `module_requested` does not award learning points. Idempotency uses `event_id` as primary key.

`GET /sync/gaps` and `GET /morning/cards` also return `total_points`.

## Next step

[Send telemetry](send-telemetry.md)
