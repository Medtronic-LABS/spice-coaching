# Known limitations

Index of current product limits.

| Area | Limit | Where documented |
|---|---|---|
| Sync | Sync list routes do not paginate. `/sync/*` routes do not apply rate limiting (unlike `/telemetry/events` and `/coaching/*`). | [Sync content](../device-coaching/sync-content.md) |
| Morning review | Auth off returns an empty card list. Morning assessment-due cards are not implemented on the server. | [Morning review](../device-coaching/morning-review.md) |
| Telemetry | No stored compliance outcome joining `module_delivered` to later `spice_action_observed`. | [Team activity](../supervision/team-activity.md) |
| Hierarchy | Parent-to-child SPICE organization expansion is not implemented. | [Tenant and hierarchy](../concepts/tenant-and-hierarchy.md) |
| Admin config | Broader configuration-management flows beyond `/admin/configs` and `GET /sync/config` are not complete. | [Configuration](../administration/configuration.md) |

## Next step

[Morning review](../device-coaching/morning-review.md)
