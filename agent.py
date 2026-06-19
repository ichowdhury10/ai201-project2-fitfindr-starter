"""
agent.py

The FitFindr planning loop. Orchestrates the three tools in response to a
natural language user query, passing state between them via a session dict.

Usage:
    from agent import run_agent
    from utils.data_loader import get_example_wardrobe

    result = run_agent(
        query="vintage graphic tee under $30, size M",
        wardrobe=get_example_wardrobe(),
    )
    print(result["fit_card"])
    print(result["error"])   # None on success
"""

import re

from tools import search_listings, suggest_outfit, create_fit_card


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    """Initialize and return a fresh session dict for one user interaction."""
    return {
        "query": query,
        "parsed": {},
        "search_results": [],
        "selected_item": None,
        "wardrobe": wardrobe,
        "outfit_suggestion": None,
        "fit_card": None,
        "error": None,
    }


# ── query parser ──────────────────────────────────────────────────────────────

def _parse_query(query: str) -> dict:
    """
    Extract description, size, and max_price from a natural language query
    using regex patterns.

    Returns:
        dict with keys: description (str), size (str | None), max_price (float | None)
    """
    # Extract max_price: "under $30", "max $50", "below $40", "less than $25"
    price_match = re.search(
        r"(?:under|max|below|up\s+to|less\s+than|<)\s*\$?\s*(\d+(?:\.\d+)?)",
        query,
        re.IGNORECASE,
    )
    max_price = float(price_match.group(1)) if price_match else None

    # Extract size: "size M", "size: XL", "in size S/M"
    size_match = re.search(
        r"\bsize\s*:?\s*([A-Z0-9]{1,4}(?:/[A-Z0-9]{1,4})?)\b",
        query,
        re.IGNORECASE,
    )
    size = size_match.group(1).upper() if size_match else None

    # Build description by stripping price/size/filler from query
    desc = query
    desc = re.sub(
        r"(?:under|max|below|up\s+to|less\s+than|<)\s*\$?\s*\d+(?:\.\d+)?",
        "",
        desc,
        flags=re.IGNORECASE,
    )
    desc = re.sub(r"\bin\s+size\s+[A-Z0-9/]+", "", desc, flags=re.IGNORECASE)
    desc = re.sub(r"\bsize\s*:?\s*[A-Z0-9/]+", "", desc, flags=re.IGNORECASE)
    desc = re.sub(
        r"\bI'?m\s+looking\s+for\b|\bfind\s+me\b|\bI\s+want\b|\bcan\s+you\s+find\b",
        "",
        desc,
        flags=re.IGNORECASE,
    )
    desc = re.sub(r"\s+", " ", desc).strip(" .,?!")

    return {"description": desc, "size": size, "max_price": max_price}


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop and returns
    the completed session dict.

    The loop is conditional:
    - If search_listings returns nothing, session["error"] is set and the
      function returns early — suggest_outfit and create_fit_card are never called.
    - Otherwise all three tools run in sequence, each reading from and writing
      to the session dict.

    Args:
        query:    Natural language user request.
        wardrobe: User's wardrobe dict with an 'items' key.

    Returns:
        Session dict. Check session["error"] first — if not None, only
        session["query"] and session["parsed"] are populated.
    """
    # Step 1: initialize session
    session = _new_session(query, wardrobe)

    # Step 2: parse the query
    session["parsed"] = _parse_query(query)
    parsed = session["parsed"]

    # Step 3: search listings
    results = search_listings(
        description=parsed["description"],
        size=parsed.get("size"),
        max_price=parsed.get("max_price"),
    )
    session["search_results"] = results

    # Branch: no results → set error and return early
    if not results:
        session["error"] = (
            "No listings matched your search. "
            "Try a broader description, a different size, or a higher price limit."
        )
        return session

    # Step 4: select top result
    session["selected_item"] = results[0]

    # Step 5: suggest outfit
    session["outfit_suggestion"] = suggest_outfit(
        new_item=session["selected_item"],
        wardrobe=session["wardrobe"],
    )

    # Step 6: create fit card
    session["fit_card"] = create_fit_card(
        outfit=session["outfit_suggestion"],
        new_item=session["selected_item"],
    )

    # Step 7: return session
    return session


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

    print("=== Happy path: graphic tee ===\n")
    session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session["error"]:
        print(f"Error: {session['error']}")
    else:
        print(f"Found: {session['selected_item']['title']}")
        print(f"\nOutfit: {session['outfit_suggestion']}")
        print(f"\nFit card: {session['fit_card']}")

    print("\n\n=== No-results path ===\n")
    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Error message: {session2['error']}")
