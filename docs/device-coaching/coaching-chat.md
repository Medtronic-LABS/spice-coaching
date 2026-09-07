# Ask the coaching chatbot

The CHW asks a question. The coaching assistant returns a grounded answer with source links, or a short greeting/triage reply.

Request and response shapes: [Coaching](../api-reference/coaching.md).

MicroCoaching supports two distinct execution environments:
1. **Cloud RAG (`POST /coaching/rag-query`)**: Executed over HTTPS by `platform-api` and `ai-runtime` against cloud vector embeddings.
2. **On-device [EDGE mode](../GLOSSARY.md#edge-mode) (Offline)**: Executed entirely inside the Android SDK using local models and synced card embeddings without network access.
3. **Server-side Local RAG Parity (`POST /coaching/local-rag-query`)**: A backend endpoint on `platform-api` that emulates local model embedding and generation on the server for parity evaluation and testing.

## Cloud RAG (`POST /coaching/rag-query`)

Requires device network connectivity.

1. Send `question` (3 to 4000 characters).
2. Set `response_language` to an allowed locale (e.g. `bn`, `en`), or leave it empty to use the deployment primary locale.
3. Call `POST /coaching/rag-query`.

**Result:** The response returns `CoachingRagResponse` containing:
- `answer`: Grounded response text (uses `• ` bullet formatting for lists).
- `retrieved_modules`: Matching module objects with `title`, `domain`, and `cosine_distance`.
- `source_documents`: Source citations with optional presigned URLs and page references.
- `cited_module_ids`: UUIDs of published modules cited in the answer.
- `suggested_questions`: Suggested follow-up prompt chips in `response_language`.

Greeting, chit-chat, or crisis-looking messages return a direct reply with empty retrieval fields.

## On-device EDGE mode (Offline)

When the CHW has no internet connection, the Android SDK performs local inference:

1. **Prerequisites:** Complete initial sync (`GET /sync/card-embeddings`) from [Sync content for offline use](sync-content.md) and ensure the on-device generation model is downloaded.
2. **Local embedding:** The SDK embeds the user query using the on-device embedding model.
3. **Local retrieval:** The SDK searches its local SQLite vector table populated from `/sync/card-embeddings`.
4. **Local generation:** The SDK generates the grounded answer using its local SLM (e.g., GGUF or Gemini Nano).
5. **Telemetry:** When connectivity is restored, the SDK flushes a `digital_help_used` telemetry event with `inference_mode: "edge"`. See [Send telemetry](send-telemetry.md).

## Server Local RAG Parity (`POST /coaching/local-rag-query`)

For backend contributors and RAG evaluation harnesses:
- Calls `POST /coaching/local-rag-query` on `platform-api`.
- Tests the local model generation profile and card-level embeddings on the server without needing an Android device.
- Returns the identical `CoachingRagResponse` envelope as Cloud RAG.

## Language

Empty `response_language` defaults to the deployment primary locale (`locales.primary`). Extra languages must be registered in `DEPLOYMENT_ADDITIONAL_LOCALES`. See [Locales](../concepts/locales.md).

## Next step

[Morning review](morning-review.md)

## See also

* [Digital-help demand](../supervision/digital-help-demand.md) — dashboard metrics fed by chatbot use
* [Sync](../api-reference/sync.md) — card embeddings for EDGE mode
