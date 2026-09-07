# Manage attachments

Attachments live in `module_json`. File bytes upload separately. The module stores references only.

**Before you start:** Do not use ingest routes for editor attachments. Do not send `X-Admin-File-Token`.

## Upload and attach

1. Call `POST /admin/files` with the file bytes.
2. Read `object_name`, `storage_path`, and `content_type` from the `201` response.
3. Put a `kind: "file"` reference into module-level `attachments[]` or `cards[i].attachments[]`.
4. Send the full `module_json` on `PUT /admin/modules/{id}` with `expected_version`.
5. After save, use `response.id`. Do not send `presigned_url` on PUT.

Supported media kinds: image, PDF, audio, video. Default upload max is 100 MB. YouTube links use `kind: "youtube"` with no upload step.

Preview with `GET /admin/files/presigned-url?object_name=...`. Cache the URL in memory until expiry. Validation error codes: [Error catalogue](../appendix/error-catalogue.md).

## Next step

[Edit and publish modules](edit-and-publish.md)
