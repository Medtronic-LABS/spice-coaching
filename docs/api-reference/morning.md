# Morning

## GET /morning/cards

Returns up to 5 prioritized module recommendations for [morning review](../GLOSSARY.md#morning-review) for the authenticated CHW.

**How to use:** [Morning review](../device-coaching/morning-review.md).

**Auth required:** Yes when SPICE auth is on. Hierarchy role `SHASTIYA_KORMI` or `PO`.

**Local development:** When SPICE auth is off (`SPICE_AUTH_ENABLED=false`), returns `{"items": [], "total_points": 0}` because no CHW identity is bound.

**Response `200` (`MorningCardsResponse`)**

| Field | Type | Description |
|---|---|---|
| `items` | array | Prioritized module items (up to 5). Each item carries `module_id`, `module_family_id`, `source`, optional `behavioural_gap_id`, and optional `quiz_id`. |
| `items[].source` | enum | `gap` (active behavioural gap), `quiz` (recent failed quiz attempt), or `fallback` (recent published module). |
| `total_points` | int | Cumulative learning points earned by the authenticated CHW. |

**Example response `200`:**

```json
{
  "items": [
    {
      "module_id": "3f751ce8-c5fc-4a45-9bd2-6f7c4807e396",
      "module_family_id": "8a7b6c5d-1111-2222-3333-444455556666",
      "source": "gap",
      "behavioural_gap_id": "e4d3c2b1-9999-8888-7777-666655554444",
      "quiz_id": null
    },
    {
      "module_id": "7c8d9e0f-1a2b-3c4d-5e6f-7a8b9c0d1e2f",
      "module_family_id": "9b8a7c6d-2222-3333-4444-555566667777",
      "source": "quiz",
      "behavioural_gap_id": null,
      "quiz_id": "c1d2e3f4-5555-6666-7777-888899990000"
    }
  ],
  "total_points": 140
}
```

**Errors**

| Status | Meaning |
|---|---|
| `401` | Missing or invalid token (`not_authenticated`) |
| `403` | Missing grant (e.g. non-CHW or non-PO hierarchy role) |

## Next step

[Coaching](coaching.md)
