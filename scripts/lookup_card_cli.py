# file: scripts/lookup_card_cli.py

from __future__ import annotations

import sys
from typing import Any, Dict

from src.scryfall_access.scryfall_client import ScryfallClient, ScryfallAPIError
from src.scryfall_access.scryfall_workflows import lookup_card_details_by_name


def _format_price(value: Any) -> str:
    if value in (None, "", 0):
        return "—"
    return str(value)


def _print_dict_section(title: str, data: Dict[str, Any]) -> None:
    print(f"=== {title} ===")
    if not data:
        print("  (none)")
        print()
        return
    for key, value in data.items():
        print(f"  {key}: {value}")
    print()


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m scripts.lookup_card_cli \"Card Name\"")
        sys.exit(1)

    card_name = " ".join(sys.argv[1:])

    client = ScryfallClient(
        app_name="uai-scryfall-workflows/0.1 (contact: you@example.com)"
    )

    try:
        details = lookup_card_details_by_name(client, card_name)
    except ScryfallAPIError as e:
        print("Scryfall API error:", e)
        sys.exit(1)

    if details is None:
        print(f"No cards found for query: {card_name!r}")
        sys.exit(0)

    card = details["raw_card"]

    # --- Core identity ---
    print("=== Card ===")
    print("Name:        ", details["name"])
    print("Oracle ID:   ", details["oracle_id"])
    print("Scryfall ID: ", details["id"])
    print("Lang:        ", details["lang"])
    print("Released at: ", details["released_at"])
    print("Set:         ", f"{details['set']} - {details['set_name']} ({details['set_type']})")
    print("Collector #: ", details["collector_number"])
    print("Rarity:      ", details["rarity"])
    print("Layout:      ", details["layout"])
    print("Games:       ", ", ".join(details["games"] or []))
    print("Reserved:    ", details["reserved"])
    print("Digital:     ", details["digital"])
    print("Promo:       ", details["promo"])
    print("Reprint:     ", details["reprint"])
    print("Finishes:    ", ", ".join(details["finishes"] or []))
    print()

    # --- Rules & stats ---
    print("=== Rules & Stats ===")
    print("Mana cost:   ", details["mana_cost"])
    print("CMC:         ", details["cmc"])
    print("Type line:   ", details["type_line"])
    print("Oracle text:\n", details["oracle_text"])
    print("Power/Tough:", f"{details['power']}/{details['toughness']}")
    print("Loyalty:     ", details["loyalty"])
    print("Defense:     ", details["defense"])
    print("Colors:      ", details["colors"])
    print("Color ID:    ", details["color_identity"])
    print("Keywords:    ", ", ".join(details["keywords"] or []))
    print("Produced mana:", details["produced_mana"])
    print("EDHREC rank: ", details["edhrec_rank"])
    print()

    # --- Legalities ---
    legalities = details["legalities"] or {}
    if legalities:
        print("=== Legalities ===")
        # Only print interesting statuses
        for fmt, status in legalities.items():
            if status not in ("not_legal", None):
                print(f"  {fmt}: {status}")
        print()

    # --- Images ---
    print("=== Images (image_uris) ===")
    image_uris = details["image_uris"] or {}
    if not image_uris:
        print("  (no images)")
    else:
        for size, url in image_uris.items():
            print(f"  {size}: {url}")
    print()

    # --- Prices ---
    print("=== Prices (prices) ===")
    prices = details["prices"] or {}
    if not prices:
        print("  (no price data)")
    else:
        # Common keys: usd, usd_foil, usd_etched, eur, eur_foil, eur_etched, tix
        for k in sorted(prices.keys()):
            print(f"  {k}: {_format_price(prices[k])}")
    print()

    # --- URIs ---
    print("=== URIs ===")
    print("Scryfall URI:      ", details["scryfall_uri"])
    print("API URI:           ", details["uri"])
    print("Prints search URI: ", details["prints_search_uri"])
    print("Rulings URI:       ", details["rulings_uri"])
    print("Set URI:           ", details["set_uri"])
    print("Set search URI:    ", details["set_search_uri"])
    print()

    # --- Related & purchase links ---
    related_uris = details["related_uris"] or {}
    purchase_uris = details["purchase_uris"] or {}

    _print_dict_section("Related URIs", related_uris)
    _print_dict_section("Purchase URIs", purchase_uris)

    print("Done ✅")


if __name__ == "__main__":
    main()
