"""Tenant id used by DB-backed tests.

Tests run without ``SpiceAuthMiddleware``, so ``get_selected_tenant_id``
resolves to ``DEFAULT_SELECTED_TENANT_ID`` and repository create paths default
to ``DEFAULT_TENANT_ID`` — both ``0``, the documented "unresolved tenant"
sentinel. Seeded rows must use the same value or tenant-scoped reads filter
them out. Cross-tenant isolation tests seed a second, explicit tenant id.
"""

from platform_service.db.default_tenant import DEFAULT_TENANT_ID

TEST_TENANT_ID = DEFAULT_TENANT_ID
