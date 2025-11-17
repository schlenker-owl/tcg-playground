"""
Simple Scryfall API client with:
- 100 ms delay between requests (global rate limit)
- List pagination (has_more + next_page)
- A few convenience methods for common endpoints.

Usage examples:

    from scryfall_access.scryfall_client import ScryfallClient

    client = ScryfallClient(app_name="uai-mtg-tool/0.1 (contact: you@example.com)")

    # Example 1: search all Lightning Bolt cards
    for card in client.search_cards("Lightning Bolt", unique="prints"):
        print(card["name"], card["set"], card["collector_number"])

    # Example 2: list all sets
    for s in client.all_sets():
        print(s["code"], "-", s["name"])

    # Example 3: fetch artifact type catalog
    artifacts = list(client.catalog_artifacts())
    print("Artifact types:", artifacts[:10])
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, Generator, Optional

import requests


SCRYFALL_BASE_URL = "https://api.scryfall.com"


@dataclass
class ScryfallAPIError(Exception):
    """Represents an error response from Scryfall's API."""

    status: int
    code: Optional[str] = None
    details: Optional[str] = None
    type: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        base = f"ScryfallAPIError(status={self.status}, code={self.code!r})"
        if self.details:
            base += f": {self.details}"
        return base


class ScryfallClient:
    """
    Minimal Scryfall API client.

    Features:
    - 100 ms minimum spacing between HTTP requests
    - Proper Accept + User-Agent headers (as Scryfall requests)
    - Automatic pagination for List objects (has_more + next_page)
    """

    def __init__(
        self,
        app_name: str,
        base_url: str = SCRYFALL_BASE_URL,
        min_interval_seconds: float = 0.1,  # 100 ms between calls
        timeout_seconds: float = 15.0,
        session: Optional[requests.Session] = None,
    ) -> None:
        """
        :param app_name: A descriptive User-Agent string for Scryfall, e.g.
                         "uai-mtg-tool/0.1 (contact: you@example.com)".
        :param base_url: Base URL for Scryfall API.
        :param min_interval_seconds: Minimum spacing between successive HTTP calls.
        :param timeout_seconds: Per-request timeout in seconds.
        :param session: Optional existing requests.Session.
        """
        if not app_name:
            raise ValueError("app_name (User-Agent) is required to be a good API citizen.")

        self.base_url = base_url.rstrip("/")
        self.min_interval = float(min_interval_seconds)
        self.timeout = float(timeout_seconds)
        self.session = session or requests.Session()

        self._user_agent = app_name
        self._last_request_time = 0.0

    # ------------------------------------------------------------------
    # Low-level HTTP helpers
    # ------------------------------------------------------------------

    def _sleep_for_rate_limit(self) -> None:
        """
        Enforce a minimum delay between successive HTTP requests.

        Scryfall asks for ~50–100 ms delay between requests. We default to 100 ms.
        """
        now = time.monotonic()
        elapsed = now - self._last_request_time
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)

    def _request(
        self,
        method: str,
        path_or_url: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Perform an HTTP request and return the parsed JSON.

        Handles:
        - Building full URL from relative paths
        - Rate limiting (sleep)
        - Scryfall error objects -> ScryfallAPIError
        """
        # Resolve URL
        if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
            url = path_or_url
        else:
            if not path_or_url.startswith("/"):
                path_or_url = "/" + path_or_url
            url = self.base_url + path_or_url

        # Rate limit
        self._sleep_for_rate_limit()

        headers = {
            "Accept": "application/json;q=0.9,*/*;q=0.8",
            "User-Agent": self._user_agent,
        }

        resp = self.session.request(
            method=method.upper(),
            url=url,
            headers=headers,
            params=params,
            json=json,
            timeout=self.timeout,
        )

        self._last_request_time = time.monotonic()

        # Handle error statuses
        if resp.status_code >= 400:
            try:
                err = resp.json()
            except ValueError:
                resp.raise_for_status()  # Not JSON, just raise
            raise ScryfallAPIError(
                status=resp.status_code,
                code=err.get("code"),
                details=err.get("details"),
                type=err.get("type"),
                raw=err,
            )

        try:
            return resp.json()
        except ValueError as e:
            raise RuntimeError(f"Failed to parse JSON from Scryfall: {e}") from e

    def _get(
        self,
        path_or_url: str,
        *,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return self._request("GET", path_or_url, params=params)

    # ------------------------------------------------------------------
    # List pagination
    # ------------------------------------------------------------------

    def _paginate_list(
        self,
        path_or_url: str,
        *,
        params: Optional[Dict[str, Any]] = None,
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Generic paginator for Scryfall List objects.

        Yields individual items from the List's `data` array, following
        `has_more` and `next_page` if present.

        List shape:
        {
          "object": "list",
          "data": [...],
          "has_more": true/false,
          "next_page": "https://api.scryfall.com/...",
          "total_cards": 123,      # only on card lists
          "warnings": ["..."]      # optional
        }
        """
        url: Optional[str] = path_or_url
        local_params = dict(params) if params else None

        while url is not None:
            page = self._get(url, params=local_params)

            if page.get("object") != "list":
                raise RuntimeError(
                    f"Expected a List object from Scryfall, got: {page.get('object')!r}"
                )

            data = page.get("data") or []
            for item in data:
                yield item

            # Prepare for next page (if any)
            if page.get("has_more"):
                url = page.get("next_page")
                # Next-page URLs already include query params
                local_params = None
            else:
                url = None

    # ------------------------------------------------------------------
    # High-level convenience methods
    # ------------------------------------------------------------------

    # --- Cards ---

    def search_cards(
        self,
        q: str,
        *,
        unique: Optional[str] = None,
        order: Optional[str] = None,
        direction: Optional[str] = None,
        include_extras: Optional[bool] = None,
        include_multilingual: Optional[bool] = None,
        include_variations: Optional[bool] = None,
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Search for cards using Scryfall's fulltext search engine.

        This yields individual card objects across all pages.

        Common parameters:
          - unique: "cards", "art", or "prints"
          - order: "name", "set", "released", "usd", etc.
          - direction: "asc" or "desc"
        """
        params: Dict[str, Any] = {"q": q}
        if unique is not None:
            params["unique"] = unique
        if order is not None:
            params["order"] = order
        if direction is not None:
            params["dir"] = direction
        if include_extras is not None:
            params["include_extras"] = str(include_extras).lower()
        if include_multilingual is not None:
            params["include_multilingual"] = str(include_multilingual).lower()
        if include_variations is not None:
            params["include_variations"] = str(include_variations).lower()

        return self._paginate_list("/cards/search", params=params)

    def card_by_id(self, card_id: str) -> Dict[str, Any]:
        """
        Fetch a single card by its Scryfall UUID.
        Endpoint: GET /cards/{id}
        """
        return self._get(f"/cards/{card_id}")

    def card_by_name(
        self,
        name: str,
        *,
        fuzzy: bool = True,
        set_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Fetch a single card by name using the /cards/named endpoint.

        - fuzzy=True uses 'fuzzy' matching, fuzzy=False uses 'exact'.
        - set_code optionally narrows to a specific set.
        """
        params: Dict[str, Any] = {}
        if fuzzy:
            params["fuzzy"] = name
        else:
            params["exact"] = name
        if set_code:
            params["set"] = set_code

        return self._get("/cards/named", params=params)

    # --- Sets ---

    def all_sets(self) -> Generator[Dict[str, Any], None, None]:
        """
        Iterate over all Set objects.
        Endpoint: GET /sets (returns a List of sets).
        """
        return self._paginate_list("/sets")

    def set_by_code(self, code: str) -> Dict[str, Any]:
        """
        Fetch a single Set object by set code.
        Endpoint: GET /sets/{code}
        """
        return self._get(f"/sets/{code}")

    # --- Catalogs (simple list-of-strings lists) ---

    def catalog_artifacts(self) -> Generator[str, None, None]:
        """
        Example Catalog endpoint: artifact types.

        Endpoint: GET /catalog/artifact-types
        Returns:
        {
          "object": "catalog",
          "uri": "...",
          "total_values": 42,
          "data": ["Arcane", "Aura", ...]  # array of strings
        }
        """
        obj = self._get("/catalog/artifact-types")
        if obj.get("object") != "catalog":
            raise RuntimeError(f"Expected a catalog, got {obj.get('object')!r}")
        for value in obj.get("data") or []:
            yield value

    def catalog_creatures(self) -> Generator[str, None, None]:
        """Retrieve all creature types. Endpoint: /catalog/creature-types"""
        obj = self._get("/catalog/creature-types")
        if obj.get("object") != "catalog":
            raise RuntimeError(f"Expected a catalog, got {obj.get('object')!r}")
        for value in obj.get("data") or []:
            yield value

    # --- Bulk Data (for big offline jobs) ---

    def bulk_data_index(self) -> Generator[Dict[str, Any], None, None]:
        """
        List all bulk data items (each describes a downloadable JSON of many cards).

        Endpoint: GET /bulk-data
        Response is a List of bulk_data objects.
        """
        return self._paginate_list("/bulk-data")

    def bulk_data_by_type(self, type_: str) -> Optional[Dict[str, Any]]:
        """
        Find a bulk data entry by its 'type' field, e.g. 'default_cards', 'oracle_cards',
        'all_printings', etc.

        Returns the first matching bulk_data object or None.
        """
        for item in self.bulk_data_index():
            if item.get("type") == type_:
                return item
        return None
