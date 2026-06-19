"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import os
import re

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for.
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive substring (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts sorted by relevance (best match first).
        Returns [] if nothing matches — does NOT raise an exception.
    """
    listings = load_listings()

    # Apply hard filters first
    if max_price is not None:
        listings = [item for item in listings if item["price"] <= max_price]

    if size is not None:
        size_lower = size.lower()
        listings = [
            item for item in listings
            if size_lower in item["size"].lower()
        ]

    # Score each remaining listing by keyword overlap with description
    tokens = set(re.findall(r"\w+", description.lower()))

    def _score(item: dict) -> int:
        # Build a single searchable text blob from relevant fields
        parts = [
            item["title"],
            item["description"],
            " ".join(item["style_tags"]),
            item["category"],
            " ".join(item["colors"]),
            item["brand"] or "",
        ]
        corpus = " ".join(parts).lower()
        return sum(1 for token in tokens if token in corpus)

    scored = [(item, _score(item)) for item in listings]
    # Drop items with zero keyword overlap
    scored = [(item, score) for item, score in scored if score > 0]
    # Sort best match first
    scored.sort(key=lambda x: x[1], reverse=True)

    return [item for item, _ in scored]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key. May be empty.

    Returns:
        A non-empty string with outfit suggestions or general styling advice.
    """
    try:
        client = _get_groq_client()

        item_summary = (
            f"{new_item['title']} — {', '.join(new_item['colors'])} "
            f"({new_item['category']}, {', '.join(new_item['style_tags'][:3])})"
        )

        if not wardrobe.get("items"):
            # Empty wardrobe: give general styling advice
            prompt = (
                f"A user just found this secondhand item: {item_summary}.\n\n"
                "They haven't told me what's already in their closet. "
                "Give them 1–2 general outfit ideas for this piece — describe what categories "
                "of clothing pair well with it, what vibe or aesthetic it fits, and one "
                "specific styling tip (e.g., how to tuck it, what shoe silhouette works). "
                "Keep it conversational, 3–5 sentences total."
            )
        else:
            wardrobe_lines = []
            for w in wardrobe["items"]:
                note = f" ({w['notes']})" if w.get("notes") else ""
                wardrobe_lines.append(
                    f"- {w['name']}{note} [{', '.join(w['colors'])}] [{w['category']}]"
                )
            wardrobe_text = "\n".join(wardrobe_lines)

            prompt = (
                f"A user is considering buying this secondhand item: {item_summary}.\n\n"
                f"Here's what's already in their wardrobe:\n{wardrobe_text}\n\n"
                "Suggest 1–2 complete outfit combinations using the new item and specific "
                "named pieces from their wardrobe. For each outfit, describe the overall vibe "
                "and include one concrete styling tip (e.g., tuck, roll, layer). "
                "Reference wardrobe items by their exact names. Keep it conversational and "
                "under 120 words total."
            )

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=300,
        )
        return response.choices[0].message.content.strip()

    except Exception:
        return (
            "Couldn't generate outfit ideas right now. "
            "Try pairing this with basics in a similar color palette."
        )


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence Instagram/TikTok-style caption string.
        Returns an error string (not an exception) if outfit is empty.
    """
    if not outfit or not outfit.strip():
        return "Error: no outfit description provided — run suggest_outfit first."

    try:
        client = _get_groq_client()

        price = new_item.get("price", "?")
        platform = new_item.get("platform", "a thrift app")
        title = new_item.get("title", "this find")
        tags = ", ".join(new_item.get("style_tags", [])[:3])

        prompt = (
            f"Write a 2–4 sentence Instagram caption for this thrifted outfit.\n\n"
            f"Item: {title}\n"
            f"Price: ${price}\n"
            f"Platform: {platform}\n"
            f"Vibe/tags: {tags}\n"
            f"Outfit: {outfit}\n\n"
            "Rules:\n"
            "- Sound like a real person posting an OOTD, not a product description\n"
            "- Mention the item name, price, and platform exactly once each\n"
            "- Use lowercase, casual phrasing — contractions are fine\n"
            "- Capture the specific vibe of the outfit (name the aesthetic)\n"
            "- 2–4 sentences max, no hashtags\n"
            "Output the caption only — no intro, no explanation."
        )

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=1.0,
            max_tokens=150,
        )
        return response.choices[0].message.content.strip()

    except Exception:
        return "Couldn't generate a fit card right now."
