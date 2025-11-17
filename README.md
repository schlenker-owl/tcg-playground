# tcg-playground

A small but powerful **Python + FastAPI + Docker** playground for exploring the **Scryfall** API and Magic: The Gathering card data.

The repo currently provides:

- A robust, rate-limited **Python client** for the Scryfall HTTP API  
- A small library of **workflows** (search, “best printing” selection, random card, rulings, other printings)  
- A **web UI**:

  - Full-text card search (using Scryfall’s query syntax)  
  - Name autocomplete in the search bar  
  - “Random card” button (optionally filtered by the current query)  
  - Card detail page with images, rules text, prices, rulings, and other printings  

- **Dockerized** FastAPI server with `docker-compose` support  

Everything is wired to respect Scryfall’s guidelines (e.g., minimum 100 ms delay between requests).   

---

## Project goals

This repo is designed as a **hands-on playground** for:

- Learning and experimenting with the Scryfall API
- Building a local MTG card browser with prices and rules context
- Providing a clean foundation for future features (deck analysis, set browsing, bulk data ingestion, etc.)

The `src/scryfall_access/__init__.py` file describes it succinctly as:

> `"scryfall-repo: hands-on scripts for scryfall api functionality"` :contentReference[oaicite:1]{index=1}  

---

## Repository structure

At a high level:

```text
tcg-playground/
  Dockerfile
  docker-compose.yml
  requirements.txt
  src/
    scryfall_access/
      __init__.py
      scryfall_client.py
      scryfall_workflows.py
      test_scryfall_client.py
    scryfall_ui/
      __init__.py
      web_app.py
      templates/
        search.html
        card_detail.html
  ...
````

### `src/scryfall_access/` – API client & workflows

* `scryfall_client.py`
  Core HTTP client that talks to `https://api.scryfall.com` and implements:

  * **Rate limiting**: global 100 ms delay between requests (Scryfall asks for ~50–100 ms).
  * **Error handling** via `ScryfallAPIError` when Scryfall returns non-2xx responses. 
  * **List pagination** for Scryfall’s `List` objects (follows `has_more` and `next_page` transparently). 

  Key methods:

  * `search_cards(q, ...)` – wraps `GET /cards/search` with full Scryfall search support. 
  * `card_by_id(card_id)` – `GET /cards/{id}`. 
  * `card_by_name(name, fuzzy=True, set_code=None)` – `GET /cards/named` (exact or fuzzy). 
  * `autocomplete_names(q, ...)` – `GET /cards/autocomplete`, returns candidate card names. 
  * `random_card(q=None)` – `GET /cards/random`, optionally filtered by a Scryfall query. 
  * `card_rulings(card_id)` – `GET /cards/{id}/rulings`.
  * `all_sets()` / `set_by_code(code)` – `GET /sets` and `GET /sets/{code}` (not yet used in the UI, but wired).
  * `catalog_artifacts()`, `catalog_creatures()` – examples of catalog endpoints.
  * `bulk_data_index()`, `bulk_data_by_type(type_)` – wrappers for bulk data endpoints. 

* `scryfall_workflows.py`
  Higher-level logic that builds on `ScryfallClient`:

  * `_summarize_card(card)`
    Produces a rich, normalized card dict with:

    * IDs: `id`, `oracle_id`, `set`, `set_name`, `collector_number`, `rarity`, `layout`
    * Stats: `mana_cost`, `cmc`, `type_line`, `oracle_text`, `power`, `toughness`, `colors`, `color_identity`, `keywords`, etc. 
    * Meta: `games`, `reserved`, `digital`, `promo`, `reprint`, finishes, `edhrec_rank`
    * Legalities: Scryfall’s full legality map
    * Imagery: `image_uris` (handles both single- and multi-faced cards)
    * Pricing & URIs: Scryfall / API links, prints search URI, rulings URI, set URIs, related & purchase URIs
    * `raw_card`: the full original JSON for anything not explicitly exposed

  * **Best-printing selection**:

    * `_score_candidate(card)` – favors cards that are:

      * priced,
      * available in paper,
      * not digital-only,
      * not promos. 
    * `_choose_best_candidate(cards)` – picks the highest-scoring printing.

  * `lookup_card_details_by_name(client, name, ...)`

    * Uses `/cards/search` to gather candidates
    * Selects the “best” printing
    * Fetches that printing by id
    * Returns the summarized card.

  * `lookup_card_details_by_id(client, card_id)` – one-shot “fetch & summarize”.

  * `search_cards_summaries(client, query, page, per_page, ...)`

    * Provides a **paginated view** over `search_cards`.
    * Skips `(page-1)*per_page` items, returns up to `per_page` summaries, and peeks ahead to set `has_next`. 

  * Autocomplete / random / rulings / printings helpers:

    * `autocomplete_card_names(client, query, ...)` – restricts autocomplete to top `limit` results. 
    * `random_card_summary(client, query=None)` – `random_card` + `_summarize_card`. 
    * `get_rulings_for_card(client, card_id)` – pulls rulings and sorts them by `published_at`. 
    * `get_printings_for_card(client, card_summary, max_printings)` – uses `oracleid:` search to gather other printings (excluding the current one), returns summaries for each. 

* `test_scryfall_client.py`
  A simple CLI script showing how to:

  * Fetch a card by name
  * Run a search and print first few results
  * List a few sets
  * Fetch catalog data (creature types) 

  It’s primarily for sanity-testing the client.

### `src/scryfall_ui/` – FastAPI server & HTML UI

* `web_app.py` – mounts all the HTTP routes.

  Key endpoints:

  * `GET /` – **Search page**

    * If no `q` → shows the search form only.
    * If `q` is present:

      * Uses `search_cards_summaries(...)` to fetch a page of results.
      * Passes `results`, `page`, `has_next`, `has_prev` into the template.

  * `GET /card/{card_id}` – **Card detail page**

    * Uses `lookup_card_details_by_id(...)` to get the main card summary.
    * Fetches rulings via `get_rulings_for_card(...)`.
    * Fetches other printings via `get_printings_for_card(...)`.
    * Includes `q` and `page` query params so the template can render a “Back to results” link.

  * `GET /api/autocomplete` – **Autocomplete API**

    * Takes `?q=...`, delegates to `autocomplete_card_names(...)`.
    * Returns JSON `{ "data": [names], "error": optional }`.

  * `GET /random` – **Random card redirect**

    * If `q` is present, uses it as a Scryfall search filter for `random_card_summary(...)`.
    * Redirects to `/card/{id}?q=...&page=1`.

* Templates (Jinja2):

  * `templates/search.html` – main search UI.

    Features:

    * Search form bound to `GET /?q=...`

    * **Autocomplete**:

      * A JS snippet calls `/api/autocomplete?q=<input>` when you type.
      * Shows a dropdown under the search box with name suggestions; clicking a suggestion fills the input and submits.

    * **Random button**:

      * Links to `/random` (or `/random?q=<current-query>`).

    * **Results grid**:

      * For each card summary:

        * Thumbnail image (small or normal)
        * Card name, set code + set name + collector number
        * Type line, mana cost, rarity
        * Layout pill (e.g., “normal”, “split”, …) 

      * Each card links to `/card/{card_id}?q=<query>&page=<page>`.

    * Pagination controls using `has_prev` and `has_next`.

  * `templates/card_detail.html` – card detail UI.

    Features:

    * **Top**: card name, set info, rarity, layout pill

    * **Primary image**: chooses normal → large → small image URI

    * **Rules section**:

      * Mana cost and type line
      * Oracle text
      * Colors, color identity, games, power/toughness, and specialized stats like loyalty/defense and EDHREC rank.

    * **Prices**:

      * Tabular display of Scryfall `prices` (usd, usd_foil, eur, tix, etc.).

    * **Links**:

      * Scryfall page, purchase URIs (TCGplayer, Cardmarket, Cardhoarder, etc.), related URIs.

    * **Rulings**:

      * List with `published_at` and `source` (WotC vs Scryfall) plus the text of each ruling.

    * **Other Printings**:

      * Gallery of other printings of the same card (based on `oracle_id`), with thumbnail, set, collector number, rarity, layout, and USD price where available.

---

## Docker & environment

* `Dockerfile` – builds a minimal Python 3.12 image, installs dependencies, and runs Uvicorn on port **9000**.

  * Exposes `9000` and starts:

    ```bash
    uvicorn src.scryfall_ui.web_app:app --host 0.0.0.0 --port 9000
    ```

* `docker-compose.yml` – defines a `web` service for local development: 

  * Builds from `.`
  * Maps `9000:9000` (host → container)
  * Mounts the repo into `/app` for live code reload
  * Runs Uvicorn with `--reload`

* `requirements.txt` – pinned versions of FastAPI, Uvicorn, Jinja2, Requests, and dependencies. 

---

## How to run the app (without Docker)

### 1. Prerequisites

* Python **3.12** (or compatible with the pinned deps)
* `pip`
* (Optional but recommended) `virtualenv` or `python -m venv`

### 2. Clone and setup

```bash
git clone https://github.com/schlenker-owl/tcg-playground.git
cd tcg-playground

# Create and activate a virtualenv
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Run the FastAPI server with Uvicorn

From the repo root:

```bash
uvicorn src.scryfall_ui.web_app:app --reload --host 0.0.0.0 --port 9000
```

Then open:

* [http://localhost:9000/](http://localhost:9000/)

You should see:

* The **Search** page at `/`

  * Type a partial name (e.g., “ligh”) and watch autocomplete fill `Lightning Bolt`, etc.
  * Hit **Search** to see a paginated grid of cards.
  * Hit **Random** to jump to a random card (optionally constrained by the current search query).

* Click a card to see its **Card Detail** page at `/card/{id}`, including prices, rulings, and other printings.

---

## How to run the app with Docker

### 1. Build the image

From the repo root:

```bash
docker build -t tcg-playground .
```

### 2. Run the container directly

```bash
docker run --rm -p 9000:9000 tcg-playground
```

Then browse to [http://localhost:9000/](http://localhost:9000/).

### 3. Or use docker-compose (nice for dev)

```bash
docker-compose up --build
```

This:

* Builds the image
* Runs the `web` service with `--reload` and a volume mount so code changes are picked up automatically.

---

## Running the client test script

The client test script lives at `src/scryfall_access/test_scryfall_client.py`. 

Because it imports `ScryfallClient` as `from scryfall_client import ScryfallClient, ScryfallAPIError`, it’s easiest to run from inside the `src/scryfall_access` directory so that `scryfall_client.py` is on the import path:

```bash
cd src/scryfall_access
python test_scryfall_client.py
```

This will:

* Fetch Black Lotus by name
* Search for “Lightning Bolt” and print the first few printings
* List the first few sets
* List creature types from the catalog

---

## Extending the project

The current design is intentionally modular:

* **Client layer** (`ScryfallClient`) – handles HTTP, rate limiting, and raw endpoints.

* **Workflow layer** (`scryfall_workflows`) – building blocks for:

  * “Best printing” logic
  * Search pagination
  * Rulings & other printings
  * Autocomplete & random-card utilities

* **Web layer** (`web_app.py` + templates) – user-facing HTTP + HTML.

This makes it straightforward to add:

* Set browser & set detail pages
* Decklist / collection workflows (using `/cards/collection`)
* Bulk data ingestion (using `bulk_data_index` and the `download_uri` fields)
* API endpoints that return JSON (for external tools) in addition to HTML

---

## Notes on Scryfall usage

* This repo is meant to be a **good API citizen**:

  * Enforces at least 100 ms between outgoing requests.
  * Uses a descriptive `User-Agent` string you can customize in `web_app.py` when constructing `ScryfallClient`.

* You should read Scryfall’s official API usage policies on their site if you deploy this anywhere public, especially around:

  * Request rates
  * Attribution
  * Caching & redistribution of data

For local exploration and personal tooling, this playground is a safe and convenient foundation.

---

## TL;DR

* Run with `uvicorn src.scryfall_ui.web_app:app --port 9000` or `docker-compose up`.
* Open `http://localhost:9000/`.
* Enjoy a **Scryfall-powered MTG card browser** with:

  * Full search, autocomplete, random card
  * Detailed card pages (prices, rulings, other printings)
  * Clean, extensible Python code ready for deeper features (sets, decks, analytics).

