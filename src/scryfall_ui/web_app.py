# file: src/scryfall_ui/web_app.py

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from src.scryfall_access.scryfall_client import ScryfallClient, ScryfallAPIError
from src.scryfall_access.scryfall_workflows import lookup_card_details_by_name


BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title="Scryfall Card Browser")

# Reuse a single client instance so we also reuse the underlying requests.Session
client = ScryfallClient(
    app_name="uai-scryfall-web-ui/0.1 (contact: you@example.com)"
)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request, q: Optional[str] = None) -> HTMLResponse:
    """
    Simple UI endpoint:

    - If no `q` query param -> just show the search form.
    - If `q` is set -> look up card details and render them.
    """
    card = None
    error = None

    if q:
        try:
            card = lookup_card_details_by_name(client, q)
            if card is None:
                error = f"No card found for query: {q!r}"
        except ScryfallAPIError as e:
            error = f"Scryfall API error: {e}"

    return templates.TemplateResponse(
        "search.html",
        {
            "request": request,
            "query": q or "",
            "card": card,
            "error": error,
        },
    )
