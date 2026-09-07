# Device integration

The device must implement host hooks with [SPICE](../GLOSSARY.md#spice), authentication, the PII boundary, detection rules, and assessment-due predicates.

The SDK talks only to platform-api. The SDK does not call ai-runtime.

In this section:

* [SPICE host app contract](spice-host-app.md)
* [Authentication](authentication.md)
* [PII boundary](pii-boundary.md)
* [Detection rules](detection-rules.md)
* [Assessment-due predicates](assessment-triggers.md)

## See also

* [Device coaching](../device-coaching/README.md) — platform-api calls after these contracts
* [Roles and access](../concepts/roles-and-access.md) — hierarchy role grants for device routes
