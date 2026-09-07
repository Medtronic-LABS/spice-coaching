# Language and locales

The schema is language-agnostic. Content is stored as locale-keyed maps. Each deployment sets one CHW-facing primary locale. The deployment primary locale is required for all CHW-facing content.

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `DEPLOYMENT_PRIMARY_LOCALE` | `bn` | CHW-facing locale. Use an ISO 639-1 short code. |
| `DEPLOYMENT_REGION_CONTEXT` | rural Bangladesh | Geographic context injected into LLM prompts. |
| `DEPLOYMENT_ADDITIONAL_LOCALES` | empty | Extra codes allowed for chatbot `response_language`. This does not expand synced content keys. Codes must exist in `LOCALE_REGISTRY`. |

Hindi deployment example:

```bash
DEPLOYMENT_PRIMARY_LOCALE=hi
DEPLOYMENT_REGION_CONTEXT=rural India
```

Bangla primary with English RAG answers:

```bash
DEPLOYMENT_PRIMARY_LOCALE=bn
DEPLOYMENT_ADDITIONAL_LOCALES=en
```

To add a deployment locale, register it in the locale registry in `packages/foundation` before go-live. Module review attestation uses `primary_language_content`. Validators check primary-locale script integrity.

## Content maps

| Table | Field | Shape |
|---|---|---|
| `module` | `title_localized`, `description_localized` | locale map |
| `module_quiz_question` | `question_localized`, `case_setup_localized`, `options_localized`, `explanation_localized` | locale map |
| `chat_frequent_question` | `question_localized` | locale map |

Each translatable card field is a locale map with the deployment primary key, for example `"title": {"bn": "..."}`.

Post-publish search metadata stores `keywords`, `search_phrases`, `topic_tags`, `synonyms`, and `clinical_conditions` under the primary locale key. Clients resolve list fields with `metadata.keywords[locales.primary]`.

## Device resolution

1. Fetch `locales` from `GET /sync/config` at startup.
2. Cache the value for offline use.
3. Resolve display text with `content[locales.primary]`.

Android clients must use `module.title[config.locales.primary]`. Do not read a suffix field such as `title_bn`.

## Change the primary locale

When `DEPLOYMENT_PRIMARY_LOCALE` changes, stored maps keep the old keys until you regenerate them.

1. Run `uv run python bin/backfill_localized_content.py`.
2. Re-run post-publish workers for each published module.
3. Run `uv run python bin/regenerate_module_embeddings.py`.

Telemetry geo field names stay Bangladesh-labelled until a non-BD deployment needs a rename. Font and TTS rendering is client-side.

## Next step

[Configuration](configuration.md)
