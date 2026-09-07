# Morning review

[Morning review](../GLOSSARY.md#morning-review) uses `GET /morning/cards` to return prioritized module suggestions for the authenticated CHW to review at the start of their shift.

Route details: [Morning](../api-reference/morning.md).

**Before you start:** SPICE auth must bind the caller to a CHW (`SHASTIYA_KORMI` or `PO`).

> **Local Development Note:** When `SPICE_AUTH_ENABLED=false`, this route returns an empty card list (`items: [], total_points: 0`) because there is no authenticated CHW principal on `request.state.spice_user`. To test morning suggestions, run unit/integration tests using the mock auth fixtures in `tests/helpers/` or set `SPICE_AUTH_ENABLED=true` with a valid mock token.

## Fetch the morning list

1. Call `GET /morning/cards`.
2. Render modules in the returned order.

**Result:** The endpoint returns `MorningCardsResponse`:
- `items[]`: Up to 5 prioritized suggestion items. Each item carries `module_id`, `module_family_id`, `source` (`gap` | `quiz` | `fallback`), and optional `behavioural_gap_id` or `quiz_id`.
- `total_points`: Cumulative learning points earned by the CHW.

### Recommendation logic

The server prioritizes modules in this order:
1. **Gap-driven:** Modules bound to the CHW's active, high-severity [behavioural gaps](../GLOSSARY.md#behavioural-gap) (`source="gap"`).
2. **Quiz-driven:** Modules where the CHW has recent failed quiz attempts (`source="quiz"`).
3. **Fallback:** Recent published modules in the tenant to ensure new content is surfaced (`source="fallback"`).

The device evaluates assessment-due predicates locally after `GET /sync/triggers` and merges that result with this server list. See [Gaps and assessment triggers](gaps-and-triggers.md).

## Next step

[Send telemetry](send-telemetry.md)
