"""The only place where feedback talks to the batches service, over HTTP.

Every call has a timeout (BATCHES_TIMEOUT_S). Anything other than a clear answer
(connection refused, timeout, 5xx, a body that is not JSON) raises
BatchesUnavailable, and the caller decides how to degrade. Standard library only.
"""
import json
import urllib.error
import urllib.parse
import urllib.request


class BatchesUnavailable(Exception):
    """The batches service did not give a usable answer in time."""


def _get(base_url, path, timeout_s):
    url = base_url.rstrip("/") + path
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            return json.load(response)
    except urllib.error.HTTPError as err:
        if err.code == 404:
            return None
        raise BatchesUnavailable(f"GET {path} returned {err.code}") from None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as err:
        # URLError: refused / DNS; TimeoutError: no answer within timeout_s;
        # ValueError: the body was not JSON (e.g. a proxy's HTML error page).
        raise BatchesUnavailable(f"GET {path} failed: {err}") from None


def get_batch(base_url, batch_code, timeout_s):
    """GET /batches/{code}: the batch as a dict, or None if batches says 404."""
    code = urllib.parse.quote(batch_code.strip().upper(), safe="")
    return _get(base_url, f"/batches/{code}", timeout_s)


def list_batches(base_url, timeout_s):
    """GET /batches: every batch, as {batch_code: batch}. One call for a whole list."""
    batches = _get(base_url, "/batches", timeout_s)
    if not isinstance(batches, list):
        raise BatchesUnavailable("GET /batches did not return a list")
    return {b["batch_code"]: b for b in batches}


def batch_details(batch):
    """The fields feedback shows next to a summary: what the product is and if it is in date."""
    if batch is None:
        return None
    return {key: batch[key] for key in ("product", "expires_on", "status")}
