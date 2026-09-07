# Gaps and assessment triggers

The device evaluates [behavioural gaps](../GLOSSARY.md#behavioural-gap) and [assessment-due triggers](../GLOSSARY.md#assessment-due-trigger) after sync. Platform does not evaluate those predicates during a CHW visit.

**Before you start:** Complete `GET /sync/gaps` and `GET /sync/triggers` from [Sync content for offline use](sync-content.md). Keep SPICE patient and follow-up lists on the device. Read [Authentication](../device-integration/authentication.md) first.

## Device flow

1. Persist gap definitions and CHW gap state from `GET /sync/gaps`.
2. Persist assessment-due predicates from `GET /sync/triggers`.
3. Build visit state from SPICE lifecycle hooks and follow-up / patient lists.
4. Evaluate detection rules and assessment-due predicates locally.
5. Surface the bound published module when a rule fires.
6. Emit telemetry for delivery and SPICE actions. See [Send telemetry](send-telemetry.md).

Detection rule and assessment-due predicate shapes:

- [Detection rules](../device-integration/detection-rules.md)
- [Assessment-due predicates](../device-integration/assessment-triggers.md)

## Morning review vs local triggers

`GET /morning/cards` returns a server-prioritized list (`gap`, `quiz`, or `fallback`). Local assessment-due evaluation is separate. The SDK merges the morning list with modules fired by local predicates after `GET /sync/triggers`. See [Morning review](morning-review.md).

## Next step

[Detection rules](../device-integration/detection-rules.md)

## See also

* [Sync](../api-reference/sync.md) — gap and trigger sync routes
* [SPICE host app contract](../device-integration/spice-host-app.md) — visit and patient context for local evaluation
