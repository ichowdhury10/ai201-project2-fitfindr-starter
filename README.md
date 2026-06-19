# FitFindr

A multi-tool AI agent that helps you find secondhand clothing and figure out how to wear it. Describe what you're looking for, and FitFindr searches mock thrift listings, suggests outfit combinations from your wardrobe, and generates a shareable fit card — all in one step.

---

## Setup

```bash
git clone <your-fork-url>
cd fitfindr
python -m venv .venv
source .venv/bin/activate      # Mac/Linux
pip install -r requirements.txt
```

Create a `.env` file in the project root:

```
GROQ_API_KEY=your_key_here
```

Run the app:

```bash
python app.py
```

Open the URL printed in your terminal (usually `http://localhost:7860`).

---

## Tool Inventory

### `search_listings(description, size, max_price)`

| | |
|---|---|
| **Purpose** | Searches the 40-item mock listings dataset and returns matches sorted by relevance. |
| **Inputs** | `description` (str) — keywords for what you want; `size` (str \| None) — size filter, case-insensitive substring match; `max_price` (float \| None) — price ceiling, inclusive |
| **Output** | `list[dict]` — matching listing dicts, sorted best-first. Each dict has: `id`, `title`, `description`, `category`, `style_tags` (list), `size`, `condition`, `price` (float), `colors` (list), `brand`, `platform`. Returns `[]` if nothing matches — never raises. |
| **Failure mode** | Returns `[]`. Agent sets an error message and returns early — no further tools are called. |

### `suggest_outfit(new_item, wardrobe)`

| | |
|---|---|
| **Purpose** | Uses the Groq LLM to suggest 1–2 outfit combinations using the thrifted item and the user's existing wardrobe. Falls back to general styling advice for new users with no wardrobe. |
| **Inputs** | `new_item` (dict) — listing dict from `search_listings`; `wardrobe` (dict) — wardrobe dict with an `items` key (may be empty) |
| **Output** | `str` — a non-empty outfit suggestion or general styling advice. |
| **Failure mode** | If wardrobe is empty: sends a general-styling prompt instead of a wardrobe-specific one, returns general advice without raising. If the LLM call fails: returns a fallback string. |

### `create_fit_card(outfit, new_item)`

| | |
|---|---|
| **Purpose** | Calls the Groq LLM at temperature 1.0 to produce a casual, OOTD-style Instagram caption for the outfit. |
| **Inputs** | `outfit` (str) — outfit suggestion from `suggest_outfit`; `new_item` (dict) — the listing dict |
| **Output** | `str` — a 2–4 sentence caption mentioning the item name, price, and platform once each. |
| **Failure mode** | If `outfit` is empty or whitespace-only: returns `"Error: no outfit description provided — run suggest_outfit first."` without calling the LLM. If the LLM call fails: returns `"Couldn't generate a fit card right now."` |

---

## How the Planning Loop Works

The loop is a **linear conditional pipeline** — each step only runs if the previous step succeeded. Here's the conditional logic:

1. **Parse the query** with regex to extract `description`, `size`, and `max_price`. Store in `session["parsed"]`.

2. **Call `search_listings`** with the parsed parameters. Store results in `session["search_results"]`.
   - **If results is empty → set `session["error"]` and return immediately.** `suggest_outfit` and `create_fit_card` are never called. This is the only early-exit branch.
   - **If results exist → set `session["selected_item"] = results[0]`** (top-scoring listing) and continue.

3. **Call `suggest_outfit`** with `session["selected_item"]` and `session["wardrobe"]`. Store result in `session["outfit_suggestion"]`. No early exit here — the tool handles the empty-wardrobe case internally.

4. **Call `create_fit_card`** with `session["outfit_suggestion"]` and `session["selected_item"]`. Store result in `session["fit_card"]`. No early exit — the tool guards against empty `outfit` input internally.

5. **Return session.**

The agent does not call all three tools unconditionally. The only conditional branch that matters is after `search_listings`: if nothing is found, the agent stops and tells the user what to try differently.

---

## State Management

All state lives in a single `session` dict, initialized by `_new_session()` at the start of each `run_agent()` call. Each tool writes its output to a named key:

| Key | Written by | Read by |
|---|---|---|
| `session["parsed"]` | `_parse_query()` | `search_listings` call |
| `session["search_results"]` | `search_listings` result | item selection (`results[0]`) |
| `session["selected_item"]` | item selection | `suggest_outfit`, `create_fit_card` |
| `session["wardrobe"]` | `_new_session()` (caller-provided) | `suggest_outfit` |
| `session["outfit_suggestion"]` | `suggest_outfit` result | `create_fit_card` |
| `session["fit_card"]` | `create_fit_card` result | UI / caller |
| `session["error"]` | early-exit branch | UI / caller |

No tool receives anything directly from another tool's return value — they all read from `session`. This makes the full interaction inspectable at any point during a run.

---

## Error Handling Strategy

### `search_listings` — No results

When the query is too narrow (impossible size/price/description combination), `search_listings` returns `[]`. The agent checks `if not results:` immediately after the call, sets `session["error"]` to a human-readable message, and returns without calling the next two tools.

**Concrete example tested:**
```bash
python -c "from tools import search_listings; print(search_listings('designer ballgown', size='XXS', max_price=5))"
# Output: []
```
Running the full agent with this query produces:
```
No listings matched your search. Try a broader description, a different size, or a higher price limit.
```

### `suggest_outfit` — Empty wardrobe

When `wardrobe["items"]` is empty (new user), the function detects this with `if not wardrobe.get("items"):` and switches to a general-styling prompt instead of a wardrobe-specific one. The LLM returns general advice (what styles pair well, what vibe the item fits). No exception is raised and no empty string is returned.

**Concrete example tested:**
```bash
python -c "
from tools import search_listings, suggest_outfit
from utils.data_loader import get_empty_wardrobe
results = search_listings('vintage graphic tee', size=None, max_price=50)
print(suggest_outfit(results[0], get_empty_wardrobe()))
"
# Output: a non-empty string with general styling advice
```

### `create_fit_card` — Empty outfit string

When `outfit` is empty or whitespace-only, `create_fit_card` checks `if not outfit or not outfit.strip():` before calling the LLM and returns a descriptive error string.

**Concrete example tested:**
```bash
python -c "
from tools import search_listings, create_fit_card
results = search_listings('vintage graphic tee', size=None, max_price=50)
print(create_fit_card('', results[0]))
"
# Output: Error: no outfit description provided — run suggest_outfit first.
```

---

## Spec Reflection

**One way the spec helped:** Writing the planning loop as specific conditional logic ("if results is empty, set error and return — do NOT proceed to suggest_outfit with empty input") meant the implementation was essentially a translation, not a design decision. The branch was pre-decided on paper, so the code was straightforward to write and verify.

**One way implementation diverged from spec:** The query parser was spec'd to handle sizes like `W30 L30` and `One Size / Oversized`, but the regex pattern `[A-Z0-9]{1,4}(?:/[A-Z0-9]{1,4})?` only matches simple forms like `M`, `S/M`, `XL`. In practice this means size filtering works for standard letter/number sizes but not for waist-based sizes. I kept it as-is rather than making the regex more complex, since the spec's examples all used simple sizes ("M", "S/M").

---

## AI Usage

### Instance 1 — `search_listings` scoring logic

**What I gave Claude:** The Tool 1 spec block from `planning.md` (inputs, return value, scoring algorithm description, failure mode) and the `load_listings()` docstring.

**What it produced:** A working implementation using token-set overlap against a concatenated corpus of `title + description + style_tags + category + colors + brand`, returning `[]` for no matches.

**What I changed:** The original draft used `any(token in corpus)` instead of `sum(...)` to compute the score, which would have given every listing a binary match score of 0 or 1 rather than counting overlapping tokens. I revised it to count overlaps so that a listing matching 3 of 3 description tokens ranks above one matching 1 of 3.

### Instance 2 — Planning loop in `agent.py`

**What I gave Claude:** The Planning Loop section and the Architecture ASCII diagram from `planning.md`, along with the `_new_session()` dict structure.

**What it produced:** A `run_agent()` implementation that followed the 7-step sequence with the correct early-exit branch on empty results.

**What I changed:** The generated version passed `session["wardrobe"]["items"]` to `suggest_outfit` instead of `session["wardrobe"]` (the full dict). The `suggest_outfit` docstring expects the full wardrobe dict with its `items` key so the tool can check `wardrobe.get("items")` itself. I caught this by comparing the generated call signature against the docstring before running.
