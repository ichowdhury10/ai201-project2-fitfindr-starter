# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## Tools

List every tool your agent will use. For each tool, fill in all four fields.
You must have at least 3 tools. The three required tools are listed — add any additional tools below them.

### Tool 1: search_listings

**What it does:**
Loads all mock listings from `data/listings.json`, applies optional size and price filters, scores each remaining listing by keyword overlap with the user's description, and returns matches sorted by relevance (best match first). Returns an empty list when nothing matches — never raises an exception.

**Input parameters:**
- `description` (str): Keywords describing what the user is looking for (e.g., "vintage graphic tee"). Used to score relevance against a listing's title, description, style_tags, category, colors, and brand fields.
- `size` (str | None): A size string such as "M", "S/M", or "W30". Matched case-insensitively as a substring of a listing's `size` field. Pass `None` to skip size filtering.
- `max_price` (float | None): Maximum price in dollars, inclusive. Pass `None` to skip price filtering.

**What it returns:**
A `list[dict]` of matching listing dictionaries, sorted by relevance score (highest first). Each dict contains: `id` (str), `title` (str), `description` (str), `category` (str), `style_tags` (list[str]), `size` (str), `condition` (str), `price` (float), `colors` (list[str]), `brand` (str | None), `platform` (str). Returns `[]` if no listings match.

**What happens if it fails or returns nothing:**
The function always returns a list (never raises). In `run_agent`, after calling `search_listings`, the agent checks whether the result is empty. If it is, `session["error"]` is set to: `"No listings matched your search. Try a broader description, a different size, or a higher price limit."` The agent returns early — `suggest_outfit` and `create_fit_card` are never called with empty input.

---

### Tool 2: suggest_outfit

**What it does:**
Takes a listing dict (the item the user is considering) and a wardrobe dict, then calls the Groq LLM to suggest 1–2 complete outfit combinations. When the wardrobe is empty, it falls back to general styling advice for the item instead of crashing.

**Input parameters:**
- `new_item` (dict): A listing dict returned by `search_listings`. Used fields: `title`, `category`, `style_tags`, `colors`, `condition`, `price`, `platform`.
- `wardrobe` (dict): A wardrobe dict with an `items` key containing a list of wardrobe item dicts. Each wardrobe item has: `name` (str), `category` (str), `colors` (list[str]), `style_tags` (list[str]), `notes` (str | None). May be empty — `wardrobe["items"]` can be `[]`.

**What it returns:**
A non-empty `str` with 1–2 outfit suggestions. Each suggestion names specific wardrobe pieces by name (when available) and describes the overall vibe or styling approach. If the wardrobe is empty, the string instead describes general styling advice (what category of pieces pair well, what aesthetics the item suits).

**What happens if it fails or returns nothing:**
If `wardrobe["items"]` is empty the function does NOT raise — it sends a general-styling prompt to the LLM and returns its response. If the LLM call itself raises (e.g., network error or invalid key), the exception is caught and the function returns a fallback string: `"Couldn't generate outfit ideas right now. Try pairing this with basics in a similar color palette."`.

---

### Tool 3: create_fit_card

**What it does:**
Generates a 2–4 sentence Instagram/TikTok-style caption for the outfit, calling the Groq LLM with a higher temperature to produce varied output for different inputs. Guards against an empty or whitespace-only `outfit` string.

**Input parameters:**
- `outfit` (str): The outfit suggestion string returned by `suggest_outfit`. Must be non-empty. If it is empty or whitespace-only, the function returns an error string instead of calling the LLM.
- `new_item` (dict): The listing dict for the thrifted item. Used fields: `title`, `price`, `platform`, `style_tags`, `colors`.

**What it returns:**
A `str` of 2–4 sentences that reads like a real OOTD caption: casual tone, mentions the item name, price, and platform once each, captures the outfit vibe in specific terms (not generic product-description language). Outputs differ across calls for different inputs due to `temperature=1.0`.

**What happens if it fails or returns nothing:**
If `outfit` is empty or whitespace-only, returns: `"Error: no outfit description provided — run suggest_outfit first."`. If the LLM call raises, catches the exception and returns: `"Couldn't generate a fit card right now."`.

---

### Additional Tools (if any)

None for the base implementation.

---

## Planning Loop

**How does your agent decide which tool to call next?**

The agent uses a linear conditional pipeline — each step only runs if the previous step succeeded. The specific branches are:

1. **Parse query** → extract `description`, `size`, `max_price` using regex patterns. Store in `session["parsed"]`.

2. **Call `search_listings`** with parsed parameters → store result in `session["search_results"]`.
   - **Branch: empty results** → set `session["error"] = "No listings matched..."` and **return early**. `suggest_outfit` is never called.
   - **Branch: results exist** → set `session["selected_item"] = results[0]` (top-scoring listing). Continue.

3. **Call `suggest_outfit`** with `session["selected_item"]` and `session["wardrobe"]` → store result in `session["outfit_suggestion"]`.
   - No early-exit here: `suggest_outfit` handles the empty-wardrobe case internally and always returns a non-empty string.

4. **Call `create_fit_card`** with `session["outfit_suggestion"]` and `session["selected_item"]` → store result in `session["fit_card"]`.
   - No early-exit: `create_fit_card` handles the empty-outfit guard internally.

5. **Return session** — the caller checks `session["error"]` first; if `None`, all three output fields are populated.

The loop does NOT call all tools unconditionally — it halts after step 2 if search returns nothing.

---

## State Management

**How does information from one tool get passed to the next?**

All state lives in a single `session` dict initialized by `_new_session()` at the start of each `run_agent()` call. The dict is mutated in place as each step completes:

| Key | Set by | Used by |
|---|---|---|
| `session["query"]` | `_new_session()` | query parsing |
| `session["parsed"]` | query parser | `search_listings` call |
| `session["search_results"]` | `search_listings` | item selection |
| `session["selected_item"]` | item selection (results[0]) | `suggest_outfit`, `create_fit_card` |
| `session["wardrobe"]` | `_new_session()` (passed in) | `suggest_outfit` |
| `session["outfit_suggestion"]` | `suggest_outfit` | `create_fit_card` |
| `session["fit_card"]` | `create_fit_card` | returned to UI |
| `session["error"]` | early-exit branch | UI / caller checks this first |

No tool receives anything directly from another tool — they all read from and write to `session`. This means the full interaction history is inspectable at any point, which makes debugging straightforward.

---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No listings match description/size/price filters | Returns `[]`. Agent sets `session["error"] = "No listings matched your search. Try a broader description, a different size, or a higher price limit."` and returns early — no further tools are called. |
| suggest_outfit | `wardrobe["items"]` is empty (new user) | Sends a general-styling prompt to the LLM (not a wardrobe-specific one) and returns general advice. No exception raised. Example: "This vintage graphic tee works well with wide-leg jeans and chunky sneakers for a 90s streetwear look." |
| create_fit_card | `outfit` string is empty or whitespace-only | Returns the string `"Error: no outfit description provided — run suggest_outfit first."` without calling the LLM. |

---

## Architecture

```
User query (natural language)
        │
        ▼
 ┌──────────────────────────────────────────────────────────────┐
 │                      run_agent()                             │
 │                                                              │
 │  Step 1: _new_session(query, wardrobe)                       │
 │     → session dict initialized                               │
 │                                                              │
 │  Step 2: _parse_query(query)                                 │
 │     → session["parsed"] = {description, size, max_price}    │
 │                                                              │
 │  Step 3: search_listings(description, size, max_price)       │
 │     → session["search_results"] = [...]                      │
 │          │                                                   │
 │          ├─ results == [] ──► session["error"] = "No match"  │
 │          │                   return session  ◄─── early exit │
 │          │                                                   │
 │          └─ results exist ──► session["selected_item"] =     │
 │                               results[0]                     │
 │                                                              │
 │  Step 4: suggest_outfit(selected_item, wardrobe)             │
 │     → session["outfit_suggestion"] = "..."                   │
 │          │                                                   │
 │          └─ wardrobe empty? ──► general styling advice       │
 │             (handled inside tool, no early exit)             │
 │                                                              │
 │  Step 5: create_fit_card(outfit_suggestion, selected_item)   │
 │     → session["fit_card"] = "..."                            │
 │          │                                                   │
 │          └─ outfit empty? ──► error string                   │
 │             (handled inside tool, no early exit)             │
 │                                                              │
 │  Step 6: return session                                      │
 └──────────────────────────────────────────────────────────────┘
        │
        ▼
 handle_query() in app.py
   → maps session fields to Gradio output panels
   → if session["error"]: show error in panel 1, blank panels 2 & 3
   → else: listing_text, outfit_suggestion, fit_card → three panels
```

---

## AI Tool Plan

**Milestone 3 — Individual tool implementations:**

For **search_listings**: I gave Claude the Tool 1 spec block from this planning.md (inputs, return value, failure mode, scoring algorithm) and the `load_listings()` docstring from `utils/data_loader.py`, and asked it to implement the function. Before running it, I verified: (a) it filters by both `max_price` and `size` with case-insensitive matching, (b) it computes a token-overlap score against the correct fields (title, description, style_tags, category, colors, brand), (c) it drops score=0 items and sorts descending. Then I tested it with 3 queries: a query that should return results, one with a very low max_price that should return nothing, and one with no filters.

For **suggest_outfit**: I gave Claude the Tool 2 spec (including both branches: empty-wardrobe and populated-wardrobe) and asked it to implement using Groq's `llama-3.3-70b-versatile`. Before running I checked: (a) it checks `len(wardrobe["items"]) == 0` explicitly, (b) the populated-wardrobe prompt names specific items, (c) LLM errors are caught and return a fallback string.

For **create_fit_card**: I gave Claude the Tool 3 spec and asked for an Instagram-style caption prompt with `temperature=1.0`. Before running I checked: (a) the empty-outfit guard is first, (b) the prompt instructs casual tone and mentions item name/price/platform once, (c) it returns a string not a dict.

**Milestone 4 — Planning loop and state management:**

I gave Claude the Planning Loop section and the Architecture ASCII diagram from this planning.md and asked it to implement `run_agent()`. Before running I verified: (a) `search_results == []` triggers early return, (b) `selected_item` is set to `results[0]`, (c) `suggest_outfit` is only called if search succeeded, (d) all state is stored in the `session` dict, not in separate variables.

---

## A Complete Interaction (Step by Step)

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1:**
The agent calls `_parse_query()` on the query. Regex extracts `max_price = 30.0`, no size found, and `description = "vintage graphic tee"` (after stripping the price mention and filler phrases). Stores `session["parsed"] = {"description": "vintage graphic tee", "size": None, "max_price": 30.0}`.

**Step 2:**
The agent calls `search_listings("vintage graphic tee", size=None, max_price=30.0)`. All 40 listings are loaded. Price filter keeps items ≤ $30 — this includes listings like the `lst_006` Graphic Tee ($24), `lst_033` Vintage Band Tee ($19), `lst_015` Vintage Graphic Hoodie ($26), and others. Each is scored by how many tokens from "vintage graphic tee" appear in its searchable text. `lst_006` scores 3 (matches "vintage", "graphic", "tee" in its title/tags), `lst_033` scores 2, etc. Results are sorted by score, with `lst_006` at the top. `session["search_results"]` is set to the sorted list. Since it's non-empty, `session["selected_item"] = lst_006` (the Graphic Tee at $24 from depop).

**Step 3:**
The agent calls `suggest_outfit(new_item=lst_006, wardrobe=get_example_wardrobe())`. The wardrobe has 10 items. A prompt is built listing the wardrobe items and the new tee's details, asking the LLM for 1–2 specific outfit combinations. The LLM returns something like: "Pair this graphic tee with your baggy straight-leg jeans and chunky white sneakers for a classic 90s streetwear look. Roll the hem once or half-tuck it for shape. For a second option, layer it under your vintage black denim jacket with black combat boots for a grungier edge." This is stored in `session["outfit_suggestion"]`.

**Step 4:**
The agent calls `create_fit_card(outfit=session["outfit_suggestion"], new_item=lst_006)`. A prompt sends the item details (title, price, platform) and outfit description to the LLM, asking for a casual Instagram caption. The LLM returns something like: "thrifted this faded graphic tee off depop for $24 and it was literally made for my baggy jeans era 🖤 rolled the hem, threw on my chunky sneakers, full look incoming." This is stored in `session["fit_card"]`.

**Final output to user:**
The Gradio UI shows three panels:
- **Top listing found:** "Graphic Tee — 2003 Tour Bootleg Style | $24.00 | Size: L | Condition: good | Platform: depop | Depop"
- **Outfit idea:** The LLM's outfit suggestion with wardrobe-specific pairings.
- **Your fit card:** The Instagram-style caption ready to copy.
