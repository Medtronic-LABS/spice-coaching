"""Platform default tenant for greenfield create paths.

Selected tenant comes from authenticate ``userDetail.country.tenantId``
(middleware). When an integer tenant is not threaded from the request
(legacy call sites / auth disabled), create paths use ``DEFAULT_TENANT_ID``
(``0``, spice parity for unresolved).
"""

DEFAULT_TENANT_ID = 0
