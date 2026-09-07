# Coaching

Device chatbot routes. Both share response model `CoachingRagResponse`.

**How to use:** [Ask the coaching chatbot](../device-coaching/coaching-chat.md).

**Auth required:** Yes when SPICE auth is on. Hierarchy role `SHASTIYA_KORMI` or `PO`.

**Rate limit:** 30 requests per minute per IP.

## POST /coaching/rag-query

Cloud retrieval-augmented chat over published modules.

**Request**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `question` | string | Yes | 3 to 4000 characters |
| `response_language` | string | No | Empty uses the deployment primary locale. Other codes must be in `DEPLOYMENT_ADDITIONAL_LOCALES`. |
| `include_generation_context` | bool | No | When true, echo retrieval context in `generation_context`. For eval. Default false. |
| `use_local` | bool | No | When true, use local embed and generate, and retrieve on `module.local_embedding`. Default false. |

**Example request:**

```json
{
  "question": "What are the danger signs during the third trimester of pregnancy?",
  "response_language": "bn",
  "include_generation_context": false
}
```

**Response `200`**

| Field | Type | Description |
|---|---|---|
| `answer` | string | Grounded answer. Unicode `• ` bullets when the model returns multiple points. |
| `retrieved_modules` | array | Hits with `module_id`, locale-keyed `title`, `domain`, `cosine_distance` |
| `source_documents` | array | Attribution with optional `presigned_url` and page or timecode refs |
| `model` | string | Generator id |
| `cited_module_ids` | UUID[] | Modules cited in the answer |
| `suggested_questions` | string[] | Follow-up questions in `response_language` |
| `generation_context` | string or null | Set only when requested |

**Example response `200`:**

```json
{
  "answer": "গর্ভাবস্থার তৃতীয় ত্রৈমাসিকে বিপজ্জনক লক্ষণসমূহ:\n• তীব্র মাথাব্যথা বা দৃষ্টি ঝাপসা হওয়া\n• হাত ও মুখে অতিরিক্ত ফোলাভাব\n• যোনিপথে রক্তপাত\n• তীব্র পেটে ব্যথা বা খিঁচুনি",
  "retrieved_modules": [
    {
      "module_id": "3f751ce8-c5fc-4a45-9bd2-6f7c4807e396",
      "title": { "bn": "গর্ভকালীন জটিলতা ও সতর্কতা" },
      "domain": "anc",
      "cosine_distance": 0.182
    }
  ],
  "source_documents": [
    {
      "source_document_id": "a1b2c3d4-0000-0000-0000-000000000001",
      "title": "ANC Guidelines 2024",
      "page_number": 14,
      "presigned_url": "https://storage.local/bucket/anc_p14.pdf?token=..."
    }
  ],
  "model": "gemini-1.5-flash",
  "cited_module_ids": ["3f751ce8-c5fc-4a45-9bd2-6f7c4807e396"],
  "suggested_questions": [
    "কখন গর্ভবতী মাকে অবিলম্বে হাসপাতালে পাঠাতে হবে?",
    "উচ্চ রক্তচাপের প্রাথমিক লক্ষণ কী?"
  ],
  "generation_context": null
}
```

Greeting or crisis-looking messages return a short reply with empty retrieval fields.

**Errors**

| Status | Meaning |
|---|---|
| `401` | Missing or invalid token (`not_authenticated`) |
| `403` | Missing grant |
| `422` | Validation failure (e.g. question shorter than 3 characters) |
| `429` | Rate limit exceeded (30/min) |
| `502` / `503` | `coaching_rag_error`, `ai_runtime_unreachable` |

## POST /coaching/local-rag-query

Server-side local model parity endpoint. Generates answers using local GGUF/llama-cpp models and card-level embeddings. Used by contributors and the RAG evaluation harness to evaluate local model parity on the server. Devices in true offline EDGE mode do not call this HTTP endpoint; they execute inference in-process within the Android SDK.

**Request**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `question` | string | Yes | 3 to 4000 characters |
| `response_language` | string | No | Same rule as cloud RAG |
| `include_generation_context` | bool | No | Same rule as cloud RAG |

`retrieved_modules` lists parent modules of matched cards. Returns the same `CoachingRagResponse` structure.

## Next step

[Sync](sync.md)
