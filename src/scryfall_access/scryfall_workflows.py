# file: src/scryfall_access/scryfall_workflows.py

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .scryfall_client import ScryfallClient, ScryfallAPIError


def _extract_primary_image_uris(card: Dict[str, Any]) -> Dict[str, str]:
    """
    Get a dict of image URIs for a card, handling both normal and multi-faced cards.

    - For most cards, image_uris is on the root card object.
    - For double-faced / split layouts, image_uris lives on card_faces[0].
    """
    # Simple case: single-faced card
    if "image_uris" in card and card["image_uris"]:
        return card["image_uris"]

    # Multi-faced cards: the images are usually on each card_face
    faces = card.get("card_faces") or []
    if faces and isinstance(faces[0], dict):
        return faces[0].get("image_uris") or {}

    return {}


def _has_any_price(card: Dict[str, Any]) -> bool:
    """
    Return True if the card has any non-null price field.

    prices is a dict like:
      {"usd": "3.68", "usd_foil": "29.99", "eur": "5.65", ...}
    Values can be strings or null.
    """
    prices = card.get("prices") or {}
    for v in prices.values():
        if v not in (None, "", 0):
            return True
    return False


def _is_paper(card: Dict[str, Any]) -> bool:
    """True if the card is available in paper (game:paper)."""
    games = card.get("games") or []
    return "paper" in games


def _score_candidate(card: Dict[str, Any]) -> int:
    """
    Score a candidate print for selection.

    Higher is better. Heuristics:
      - Prefer prints that:
        - have any prices
        - are available in paper
        - are not digital-only
        - are not promos
    """
    score = 0

    if _has_any_price(card):
        score += 8
    if _is_paper(card):
        score += 4
    if not card.get("digital", False):
        score += 2
    if not card.get("promo", False):
        score += 1

    return score


def _choose_best_candidate(candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Choose the "best" candidate from a list of card objects using _score_candidate.

    Ties are broken by keeping the first candidate with that score.
    """
    if not candidates:
        raise ValueError("No candidates to choose from.")

    best = candidates[0]
    best_score = _score_candidate(best)

    for card in candidates[1:]:
        score = _score_candidate(card)
        if score > best_score:
            best = card
            best_score = score

    return best


def _summarize_card(card: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build a rich but convenient summary of a full Scryfall card object.

    The full raw card is also returned under 'raw_card'.
    """
    image_uris = _extract_primary_image_uris(card)
    prices = card.get("prices") or {}

    return {
        # Identifiers
        "id": card.get("id"),
        "oracle_id": card.get("oracle_id"),
        "name": card.get("name"),
        "lang": card.get("lang"),
        "released_at": card.get("released_at"),
        "set": card.get("set"),
        "set_name": card.get("set_name"),
        "set_type": card.get("set_type"),
        "collector_number": card.get("collector_number"),
        "rarity": card.get("rarity"),
        "layout": card.get("layout"),

        # Rules & stats
        "mana_cost": card.get("mana_cost"),
        "cmc": card.get("cmc"),
        "type_line": card.get("type_line"),
        "oracle_text": card.get("oracle_text"),
        "power": card.get("power"),
        "toughness": card.get("toughness"),
        "loyalty": card.get("loyalty"),
        "defense": card.get("defense"),
        "colors": card.get("colors"),
        "color_identity": card.get("color_identity"),
        "keywords": card.get("keywords"),
        "produced_mana": card.get("produced_mana"),

        # Flags & meta
        "games": card.get("games"),
        "reserved": card.get("reserved"),
        "digital": card.get("digital"),
        "promo": card.get("promo"),
        "reprint": card.get("reprint"),
        "finishes": card.get("finishes"),
        "full_art": card.get("full_art"),
        "textless": card.get("textless"),
        "booster": card.get("booster"),
        "edhrec_rank": card.get("edhrec_rank"),

        # Legalities
        "legalities": card.get("legalities"),

        # Imagery
        "image_uris": image_uris,

        # Pricing & links
        "prices": prices,
        "scryfall_uri": card.get("scryfall_uri"),
        "uri": card.get("uri"),
        "prints_search_uri": card.get("prints_search_uri"),
        "rulings_uri": card.get("rulings_uri"),
        "set_uri": card.get("set_uri"),
        "set_search_uri": card.get("set_search_uri"),
        "related_uris": card.get("related_uris") or {},
        "purchase_uris": card.get("purchase_uris") or {},

        # Full raw card object for anything else
        "raw_card": card,
    }


# ------------------------------------------------------------------------------
# High-level workflows: single-card and search
# ------------------------------------------------------------------------------

def lookup_card_details_by_name(
    client: ScryfallClient,
    name: str,
    *,
    max_candidates: int = 50,
    unique: str = "prints",
    order: str = "released",
    direction: str = "desc",
) -> Optional[Dict[str, Any]]:
    """
    High-level workflow:

    1) Search for `name` via /cards/search (using Scryfall's fulltext search).
    2) Collect up to `max_candidates` matching prints.
    3) Choose the "best" print (paper, priced, non-digital, non-promo).
    4) Use its Scryfall `id` with /cards/{id} to fetch full details.
    5) Return a rich summary dict (plus the raw card under 'raw_card').

    Returns None if no search results found.
    """
    search_iter = client.search_cards(
        name,
        unique=unique,
        order=order,
        direction=direction,
    )

    candidates: List[Dict[str, Any]] = []
    for i, card in enumerate(search_iter):
        candidates.append(card)
        if i + 1 >= max_candidates:
            break

    if not candidates:
        return None

    best = _choose_best_candidate(candidates)

    # Optional second fetch by id (keeps workflow explicit / future-proof).
    full_card = client.card_by_id(best["id"])

    return _summarize_card(full_card)


def lookup_card_details_by_id(
    client: ScryfallClient,
    card_id: str,
) -> Optional[Dict[str, Any]]:
    """
    Fetch a card by its Scryfall UUID and return the rich summary.
    """
    card = client.card_by_id(card_id)
    if not card:
        return None
    return _summarize_card(card)


def search_cards_summaries(
    client: ScryfallClient,
    *,
    query: str,
    page: int = 1,
    per_page: int = 20,
    unique: str = "prints",
    order: str = "released",
    direction: str = "desc",
) -> Dict[str, Any]:
    """
    Paginated search workflow for UI:

    1) Use client.search_cards(...) to iterate over all matching prints.
    2) Skip (page-1) * per_page results.
    3) Collect up to per_page summary dicts.
    4) Peek one extra item (if present) to determine has_next.

    We intentionally do not compute a total count (would require consuming
    the whole generator). Instead we expose has_prev/has_next for navigation.
    """
    if page < 1:
        page = 1
    per_page = max(1, per_page)

    start_index = (page - 1) * per_page
    results: List[Dict[str, Any]] = []

    gen = client.search_cards(
        query,
        unique=unique,
        order=order,
        direction=direction,
    )

    total_seen = 0

    for card in gen:
        if total_seen >= start_index and len(results) < per_page:
            results.append(_summarize_card(card))

        total_seen += 1

        if len(results) >= per_page and total_seen >= start_index + per_page:
            break

    # Determine if there is a next page by peeking one extra item
    has_next = False
    if len(results) == per_page:
        try:
            _ = next(gen)
        except StopIteration:
            has_next = False
        else:
            has_next = True

    has_prev = page > 1

    return {
        "query": query,
        "results": results,
        "page": page,
        "per_page": per_page,
        "has_next": has_next,
        "has_prev": has_prev,
    }


# ------------------------------------------------------------------------------
# Additional workflows: autocomplete / random / rulings / printings
# ------------------------------------------------------------------------------

def autocomplete_card_names(
    client: ScryfallClient,
    query: str,
    *,
    include_extras: bool = False,
    limit: int = 20,
) -> List[str]:
    """
    Wrapper around Scryfall's /cards/autocomplete endpoint.

    Returns a list of possible card name completions for the given query.
    The underlying API returns up to 20 names; this helper can further trim.
    """
    names = client.autocomplete_names(query, include_extras=include_extras)
    if limit is not None:
        return names[:limit]
    return names


def random_card_summary(
    client: ScryfallClient,
    query: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Fetch a random card (optionally restricted by a Scryfall search query)
    and return the rich summary.
    """
    card = client.random_card(q=query)
    return _summarize_card(card)


def get_rulings_for_card(
    client: ScryfallClient,
    card_id: str,
) -> List[Dict[str, Any]]:
    """
    Fetch and normalize rulings for a card (sorted by published_at ascending).
    """
    rulings = client.card_rulings(card_id)

    def sort_key(r: Dict[str, Any]) -> str:
        return r.get("published_at") or ""

    rulings_sorted = sorted(rulings, key=sort_key)
    return rulings_sorted


def get_printings_for_card(
    client: ScryfallClient,
    card_summary: Dict[str, Any],
    *,
    max_printings: int = 24,
) -> List[Dict[str, Any]]:
    """
    Fetch summaries for other printings of the same card (based on oracle_id).

    Uses a search query oracleid:... with unique=prints so each printing appears
    once. Filters out the current card's id from the results.
    """
    oracle_id = card_summary.get("oracle_id")
    current_id = card_summary.get("id")
    if not oracle_id:
        return []

    query = f"oracleid:{oracle_id}"
    gen = client.search_cards(
        query,
        unique="prints",
        order="released",
        direction="asc",
    )

    printings: List[Dict[str, Any]] = []
    for card in gen:
        if card.get("id") == current_id:
            # Skip the printing we are already viewing
            continue
        printings.append(_summarize_card(card))
        if len(printings) >= max_printings:
            break

    return printings


# ------------------------------------------------------------------------------
# Set workflows: list sets, set detail, and set card browsing
# ------------------------------------------------------------------------------

def list_sets_for_ui(client: ScryfallClient) -> List[Dict[str, Any]]:
    """
    Retrieve all sets and sort them by release date (newest first), then by name.

    The Set objects include fields like:
      - code, name, set_type, released_at, card_count, digital, foil_only, icon_svg_uri, etc.
    """
    sets = list(client.all_sets())

    def sort_key(s: Dict[str, Any]) -> tuple[str, str]:
        released = s.get("released_at") or ""
        name = s.get("name") or ""
        return (released, name)

    sets_sorted = sorted(sets, key=sort_key)
    sets_sorted.reverse()  # newest first
    return sets_sorted


def get_set_detail(client: ScryfallClient, code: str) -> Optional[Dict[str, Any]]:
    """
    Fetch a single set by its Scryfall set code.
    """
    try:
        return client.set_by_code(code)
    except ScryfallAPIError:
        return None


def set_cards_summaries(
    client: ScryfallClient,
    set_code: str,
    *,
    page: int = 1,
    per_page: int = 20,
) -> Dict[str, Any]:
    """
    Convenience wrapper around search_cards_summaries for browsing a set.

    Uses query e:{set_code} which is Scryfall shorthand for "in this set".
    """
    query = f"e:{set_code}"
    return search_cards_summaries(
        client,
        query=query,
        page=page,
        per_page=per_page,
        unique="prints",
        order="released",
        direction="asc",
    )
