# Keystone showcase — prototype shell

A self-contained, static showcase for the Keystone platform. Open `index.html` in any
browser — no server, no build step, no dependencies. Precomputed runs only (Reading A):
**you** run the agents locally on a curated set of names, and the showcase displays the
outputs. No visitor ever triggers a live agent run.

## What's here

- `index.html` — the whole showcase: hero + triple-reuse spine diagram, per-agent selection,
  and per-agent detail renderers. Charts are drawn as inline SVG (no chart library).
- All data is read from a single **manifest** object. In this prototype the manifest is
  *embedded* in `index.html` (so it opens offline) and every number in it is an illustrative
  placeholder.

## Per-agent selection (by design, not one global ticker picker)

- **Agent 1** — select by **company** (`ASML.AS`, `SIE.DE`, `ALO.PA` …). Single-ticker.
- **Agent 2** — select by **monitoring scenario** (a covenant watchlist, not a company).
- **Agent 3** — select by **event-study peer group** (a group *contains* companies). Cross-ticker.
- **Agent 4** — shown as planned/designed (disabled) until built.

## Wiring in your real runs

1. Externalise the manifest. In `index.html`, in `init()`, replace:
   ```js
   MANIFEST = EMBEDDED_MANIFEST;
   ```
   with:
   ```js
   MANIFEST = await fetch('manifest.json').then(r => r.json());
   ```
   and move the object into a `manifest.json` file next to `index.html`.
   (Serve over http — GitHub Pages, or `python -m http.server` locally — so `fetch` works.)

2. Write a small **collector** (`collect.py`) that runs each agent on your curated names and
   emits `manifest.json`. It reads what the agents already produce:
   - Agent 1: pull `verdict`, the `model.json` numbers (snapshot, DCF ranges, peer values,
     price/index series), and the note text.
   - Agent 2: the per-cycle metric series, threshold, the flagged/breach cycle indices, the
     classification per cycle, and the exception text.
   - Agent 3: the CAAR + placebo arrays, N, the significance verdict, pinned peers (with any
     dropped ones), the validation-gate statuses, and the scenario (or the honest null).

   Re-running the collector after adding a name = the only step to grow the showcase.

## Manifest schema (illustrative)

```
{
  "agent1": { "label": "Company", "runs": [ {
      "id","company","exchange","verdict","vclass",
      "snapshot":[["k","v"],...], "px":[...], "idx":[...],
      "peers":{"axis","self","others":[...]},
      "dcf":[{"lab","lo","hi"},...], "price",
      "note":{"view","evidence","triggers"}, "consensus"
  } ] },
  "agent2": { "label": "Monitoring scenario", "runs": [ {
      "id","name","metric","threshold","unit","series":[...],
      "flaggedCycle","breachCycle","classes":["STABLE"|"WIDEN"|"BREACH"...],
      "lead","exception"
  } ] },
  "agent3": { "label": "Event-study group", "runs": [ {
      "id","group","peers":[["TICKER",1|0],...],
      "window":[...],"caar":[...],"placebo":[...],"n",
      "sig":{"t","p","sign","verdict"}, "sverdict",
      "gate":[["Confound","pass"|"flag"|"na"],...],
      "scenario": {"p25","median","p75","pPos","ci","null":false} | {"null":true,"msg"}
  } ] }
}
```

`vclass` / `sverdict` use `b-pos` (favourable), `b-neg` (adverse), `b-warn` (null/caution),
`b-info` (neutral). Colour is used only where it carries meaning.

## Curation rule

Show your best runs, but never hide a caveat *inside* a shown run — an honest null, an
excluded peer, or a confidence flag stays visible. That honesty is the credibility.

## Hosting

Static files → GitHub Pages (or Netlify/any static host). Point Pages at the folder; done.
This shell is the foundation the full hosted site grows from — Agent 4 becomes a fourth tile
when it's built, and a single rate-limited "live" endpoint can be added later if wanted.
