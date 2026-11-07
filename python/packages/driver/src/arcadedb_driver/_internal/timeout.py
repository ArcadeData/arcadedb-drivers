"""The per-call `timeout` argument shared by the facades.

`USE_CLIENT_DEFAULT` is httpx's own sentinel: passing it to a request keeps the timeout of the
client the request goes through, which is exactly what a call that never mentions `timeout` did
before the argument existed. A `float`, an `httpx.Timeout` or `None` replaces the client's timeout
for that one call (`None` meaning no timeout, as everywhere in httpx).

httpx does not export the sentinel's class, so the type is imported from its private module for the
type checker only and rebuilt from the sentinel at run time.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from httpx._client import UseClientDefault
else:
    UseClientDefault = type(httpx.USE_CLIENT_DEFAULT)

USE_CLIENT_DEFAULT = httpx.USE_CLIENT_DEFAULT

CallTimeout = float | httpx.Timeout | None | UseClientDefault
