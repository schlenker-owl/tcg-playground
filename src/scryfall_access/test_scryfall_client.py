# file: test_scryfall_client.py

from scryfall_client import ScryfallClient, ScryfallAPIError


def main() -> None:
    # Be a good citizen: descriptive app name + contact
    client = ScryfallClient(
        app_name="uai-scryfall-test/0.1 (contact: you@example.com)"
    )

    print("=== 1) card_by_name: 'Black Lotus' (fuzzy) ===")
    try:
        card = client.card_by_name("black lotus")
        print("Name:        ", card.get("name"))
        print("Set:         ", card.get("set"))
        print("Collector #: ", card.get("collector_number"))
        print("Mana cost:   ", card.get("mana_cost"))
        print("Type line:   ", card.get("type_line"))
        print("Oracle text: ", card.get("oracle_text"))
        print()
    except ScryfallAPIError as e:
        print("Error fetching card by name:", e)
        return

    print("=== 2) search_cards: 'Lightning Bolt' (first 5 prints) ===")
    try:
        for i, c in enumerate(client.search_cards("Lightning Bolt", unique="prints")):
            print(
                f"{i+1:2d}. {c.get('name')} "
                f"({c.get('set')}/{c.get('collector_number')})"
            )
            if i >= 4:  # only first 5
                break
        print()
    except ScryfallAPIError as e:
        print("Error searching cards:", e)
        return

    print("=== 3) all_sets: first 5 sets ===")
    try:
        for i, s in enumerate(client.all_sets()):
            print(f"{i+1:2d}. {s.get('code')} - {s.get('name')}")
            if i >= 4:  # only first 5
                break
        print()
    except ScryfallAPIError as e:
        print("Error listing sets:", e)
        return

    print("=== 4) catalog_creatures: count + first 10 types ===")
    try:
        creature_types = list(client.catalog_creatures())
        print(f"Total creature types: {len(creature_types)}")
        print("First 10 creature types:")
        for t in creature_types[:10]:
            print(" -", t)
        print()
    except ScryfallAPIError as e:
        print("Error fetching creature catalog:", e)
        return

    print("All Scryfall client tests completed successfully ✅")


if __name__ == "__main__":
    main()
