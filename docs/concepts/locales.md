# Locales

The schema is language-agnostic. Content is stored as [locale-keyed content](../GLOSSARY.md#locale-keyed-content) maps, for example `{"bn": "..."}`.

Each deployment sets one CHW-facing **primary locale**. The default is `bn`.

- Store every CHW-facing string under the primary locale key.
- Resolve display text with `content[locales.primary]` from `GET /sync/config`.
- Do not read a suffix field such as `title_bn`.

Module titles, quiz questions, and card `title` / `body` fields are locale maps.

## Next step

[Language and locales](../administration/language-and-locales.md)

## See also

* [Sync content for offline use](../device-coaching/sync-content.md) — `locales` from `GET /sync/config`
* [Ask the coaching chatbot](../device-coaching/coaching-chat.md) — `response_language` for chat
