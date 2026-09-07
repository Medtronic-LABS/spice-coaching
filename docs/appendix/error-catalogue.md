# Error catalogue

HTTP errors from platform-api and ai-runtime use RFC 7807 Problem Details.

The `type` field is `docs/error-codes.json#{code}`. Clients map `code` to user-facing text. That path is a client contract: update `docs/error-codes.json` in the same change when you add, remove, or rename a server error code.

Auth and Problem Details shape: [Authentication and errors](../api-reference/authentication-and-errors.md).
