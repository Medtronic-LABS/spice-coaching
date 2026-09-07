# Review dual-path merges

When card draft finds a similar active [module](../concepts/modules-cards-families.md), [ingest](../GLOSSARY.md#ingest) writes a [dual-path merge](../GLOSSARY.md#dual-path-merge): two review-pending families instead of overwriting the published module.

**Before you start:** Poll the ingest batch until `card_draft` finishes for every run. Open the All or Needs review tab on the admin module list.

Merge routes: [Admin ingest](../api-reference/admin-ingest.md).

## Choose override or split

| Goal | Call | Result |
|---|---|---|
| Keep the LLM-merged cards | Override | Platform retires the primary and the matched published module. The secondary becomes `draft`. |
| Keep only the new-document cards | Split | The primary becomes `draft`. The secondary is retired. The matched published module is unchanged. |

Always pass the **primary** `module_id`.

## How the pair looks

- Primary: current-document cards. `lifecycle_status=review_pending`.
- Secondary: LLM-merged cards. `lifecycle_status=review_pending`.

Both rows link to each other and to the matched published module. The matched module stays active until override.

Default `GET /admin/modules` hides the `review_pending` secondary so the pair is one list row.

## Promote the merge (override)

Call `POST /admin/ingest/modules/{module_id}/override-merge` with the primary `module_id`.

**Result:** Platform retires the primary and the matched source module. The secondary becomes `draft` and is no longer hidden.

## Keep the new document only (split)

Call `POST /admin/ingest/modules/{module_id}/split-merge` with the primary `module_id`.

**Result:** The primary becomes `draft`. The secondary is retired. The matched published module is not changed.

## After an edit of the matched module

If an admin saves a new content version of the matched module, `review_pending` rows whose merge source pointed at the old row are retargeted to the new latest module row in that family.

When you delete a dual-path primary, the secondary is retired in the same operation.

## Next step

[Edit and publish modules](edit-and-publish.md)
