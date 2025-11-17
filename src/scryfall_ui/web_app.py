# file: src/scryfall_ui/web_app.py

from __future__ import annotations

from pathlib import Path
from typing import Optional, Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from src.scryfall_access.scryfall_client import ScryfallClient, ScryfallAPIError
from src.scryfall_access.scryfall_workflows import (
    autocomplete_card_names,
    get_printings_for_card,
    get_rulings_for_card,
    get_set_detail,
    list_sets_for_ui,
    lookup_card_details_by_id,
    random_card_summary,
    search_cards_summaries,
    set_cards_summaries,
)

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title="Scryfall Card Browser")

# Reuse a single client instance (and underlying Session)
client = ScryfallClient(
    app_name="uai-scryfall-web-ui/0.1 (contact: you@example.com)"
)

PER_PAGE = 20


@app.get("/", response_class=HTMLResponse)
async def search_page(
    request: Request,
    q: Optional[str] = None,
    page: int = 1,
) -> HTMLResponse:
    """
    Search UI endpoint:

    - GET /                  -> search form (no results)
    - GET /?q=..&page=..     -> paginated search results
    """
    error: Optional[str] = None
    results = []
    has_next = False
    has_prev = False

    if q:
        try:
            if page < 1:
                page = 1

            search_result = search_cards_summaries(
                client,
                query=q,
                page=page,
                per_page=PER_PAGE,
            )
            results = search_result["results"]
            has_next = search_result["has_next"]
            has_prev = search_result["has_prev"]

            if not results:
                error = f"No cards found for query: {q!r}"
        except ScryfallAPIError as e:
            error = f"Scryfall API error: {e}"
        except Exception as e:
            error = f"Unexpected error: {e}"

    return templates.TemplateResponse(
        "search.html",
        {
            "request": request,
            "query": q or "",
            "results": results,
            "error": error,
            "page": page,
            "per_page": PER_PAGE,
            "has_next": has_next,
            "has_prev": has_prev,
        },
    )


@app.get("/card/{card_id}", response_class=HTMLResponse)
async def card_detail_page(
    request: Request,
    card_id: str,
    q: Optional[str] = None,
    page: int = 1,
) -> HTMLResponse:
    """
    Card detail page:

    - GET /card/{card_id}           -> card detail
    - Optional q + page are used only to render a "Back to results" link.
    """
    error: Optional[str] = None
    card = None
    rulings: list[dict[str, Any]] | list = []
    printings: list[dict[str, Any]] | list = []

    try:
        card = lookup_card_details_by_id(client, card_id)
        if card is None:
            error = f"No card found with id: {card_id!r}"
        else:
            try:
                rulings = get_rulings_for_card(client, card["id"])
            except ScryfallAPIError:
                rulings = []

            try:
                printings = get_printings_for_card(client, card, max_printings=24)
            except ScryfallAPIError:
                printings = []
    except ScryfallAPIError as e:
        error = f"Scryfall API error: {e}"
    except Exception as e:
        error = f"Unexpected error: {e}"

    return templates.TemplateResponse(
        "card_detail.html",
        {
            "request": request,
            "card": card,
            "rulings": rulings,
            "printings": printings,
            "error": error,
            "query": q or "",
            "page": page,
        },
    )


@app.get("/api/autocomplete")
async def autocomplete_endpoint(q: str) -> JSONResponse:
    """
    JSON autocomplete endpoint:

    - GET /api/autocomplete?q=...

    Returns: {"data": [...]} to be used by the search bar JS.
    """
    q = q.strip()
    if len(q) < 2:
        return JSONResponse({"data": []})

    try:
        names = autocomplete_card_names(client, q, include_extras=False, limit=20)
        return JSONResponse({"data": names})
    except ScryfallAPIError as e:
        return JSONResponse({"data": [], "error": str(e)}, status_code=502)
    except Exception as e:
        return JSONResponse({"data": [], "error": str(e)}, status_code=500)


@app.get("/random")
async def random_card_route(
    request: Request,
    q: Optional[str] = None,
) -> RedirectResponse:
    """
    Random card endpoint:

    - GET /random           -> random card from entire database
    - GET /random?q=...     -> random card matching Scryfall search query

    Redirects to /card/{id}, preserving q for "Back to results" behavior.
    """
    try:
        summary = random_card_summary(client, query=q)
        card_id = summary["id"]
    except ScryfallAPIError:
        return RedirectResponse(
            url=f"/?q={ (q or '') }",
            status_code=303,
        )
    except Exception:
        return RedirectResponse(
            url=f"/?q={ (q or '') }",
            status_code=303,
        )

    q_param = q or ""
    return RedirectResponse(
        url=f"/card/{card_id}?q={q_param}&page=1",
        status_code=303,
    )


@app.get("/sets", response_class=HTMLResponse)
async def sets_page(request: Request) -> HTMLResponse:
    """
    Sets index page:

    - GET /sets -> list of all sets, sorted by release date (newest first).
    """
    error: Optional[str] = None
    sets = []

    try:
        sets = list_sets_for_ui(client)
    except ScryfallAPIError as e:
        error = f"Scryfall API error: {e}"
    except Exception as e:
        error = f"Unexpected error: {e}"

    return templates.TemplateResponse(
        "sets.html",
        {
            "request": request,
            "sets": sets,
            "error": error,
        },
    )


@app.get("/sets/{set_code}", response_class=HTMLResponse)
async def set_detail_page(
    request: Request,
    set_code: str,
    page: int = 1,
) -> HTMLResponse:
    """
    Set detail page:

    - GET /sets/{set_code}        -> set metadata + cards in that set (paginated)
    """
    error: Optional[str] = None
    set_info = None
    cards = []
    has_next = False
    has_prev = False

    try:
        set_info = get_set_detail(client, set_code)
        if set_info is None:
            error = f"No set found with code: {set_code!r}"
        else:
            res = set_cards_summaries(
                client,
                set_code=set_code,
                page=page,
                per_page=PER_PAGE,
            )
            cards = res["results"]
            has_next = res["has_next"]
            has_prev = res["has_prev"]

            if not cards and error is None:
                error = "No cards found for this set."
    except ScryfallAPIError as e:
        error = f"Scryfall API error: {e}"
    except Exception as e:
        error = f"Unexpected error: {e}"

    return templates.TemplateResponse(
        "set_detail.html",
        {
            "request": request,
            "set": set_info,
            "cards": cards,
            "error": error,
            "page": page,
            "has_next": has_next,
            "has_prev": has_prev,
        },
    )
