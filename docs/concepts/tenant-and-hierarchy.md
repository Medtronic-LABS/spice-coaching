# Tenant and hierarchy

A [tenant](../GLOSSARY.md#tenant) within MicroCoaching is the SPICE country tenant. It is stored as `tenant_id` (`BIGINT`) on entities (Module, Document, and related rows).

## Geography

Geography in a tenant is Division → District → Upazila.

## Hierarchy users

People in a tenant follow this tree:

```
Area Manager → Program Organizer → CHW
```

The [CHW](../GLOSSARY.md#chw) hierarchy role is `SHASTIYA_KORMI`. Besides the above hierarchy, the [Super Admin](../GLOSSARY.md#super-admin) can also access the application and is defined to have higher precedence than the [Area Manager](../GLOSSARY.md#area-manager) for Assignment and Analytics view.

How MicroCoaching selects the tenant on a request, and how workers bind tenant for jobs: [Multi-tenancy](../administration/multi-tenancy.md).

## Next step

[Roles and access](roles-and-access.md)
