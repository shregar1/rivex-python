"""``rivex.utilities.request`` — request-data manipulation utilities.

Each utility class operates on the ``request_data`` dict that flows
through Rivex's middleware pipeline (and is the same dict the
:func:`Request._from_raw` factory consumes before a route handler
runs).

All methods are ``@staticmethod`` so the classes can be used as
namespaces without instantiation::

    from rivex.utilities.request import RequestStateUtility, RequestHeaderUtility

    RequestStateUtility.set_request_state(request_data, "urn", "urn:rivex:abc")
    user_agent = RequestHeaderUtility.get_request_header(request_data, "user-agent")
"""

from __future__ import annotations

from rivex.utilities.request.body import RequestBodyUtility
from rivex.utilities.request.form import RequestFormUtility
from rivex.utilities.request.header import RequestHeaderUtility
from rivex.utilities.request.param import RequestParamUtility
from rivex.utilities.request.state import RequestStateUtility

__all__ = [
    "RequestBodyUtility",
    "RequestFormUtility",
    "RequestHeaderUtility",
    "RequestParamUtility",
    "RequestStateUtility",
]
