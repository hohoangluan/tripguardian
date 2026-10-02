"""One JSON GET for live sources: stdlib only, one timeout, no retries.

A failure is handed to the caller as Unavailable; deciding what a missing source means belongs to Planning.
"""

import http.client
import json
import urllib.error
import urllib.request


class Unavailable(RuntimeError):
    """A live source did not answer usably. Planning turns this into a flag, never into a made-up value."""


def get_json(url: str, user_agent: str, timeout_s: float):
    req = urllib.request.Request(url, headers={"User-Agent": user_agent, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as r:
            return json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, http.client.HTTPException, TimeoutError, OSError, ValueError) as e:
        raise Unavailable(f"{url.split('?', 1)[0]}: {e}") from e
