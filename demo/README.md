# TerraCycle Proof — read-only demonstration page

A single page that displays the **verified** demonstration snapshot produced by the
real-evidence run (`data/demo/latest_proof.json`). It is plain HTML, CSS and vanilla
JavaScript — no framework, no build step.

The page is **read-only**: it performs no blockchain transaction, contacts no external
service and never queries a running chain. It shows the snapshot that was verified when
the demonstration ran.

## Run it

From the **repository root**:

```bash
python scripts/serve_demo.py
```

Then open **http://127.0.0.1:8090/** in a browser.

- Server: `scripts/serve_demo.py` (Python standard library only)
- Bind address: `127.0.0.1` (localhost), port `8090` — use `--port` to change it
- Stop it with `Ctrl+C` in the terminal

The server exposes only four things:

| Route | Content |
|---|---|
| `/` | `demo/index.html` |
| `/styles.css` | `demo/styles.css` |
| `/app.js` | `demo/app.js` |
| `/api/proof` | `data/demo/latest_proof.json` |

Every other path returns `404`: the repository (`.env`, `.git`, backend code, ML data) is
never exposed. If the demonstration document is missing the endpoint answers `503` with an
error, and if it is malformed it answers `500` — the page then shows an explicit error
state instead of placeholder values.

## What you should see

1. **Header** — “TerraCycle Proof”, the subtitle and the “Local Blockchain Demonstration” badge,
   plus the generation timestamp of the snapshot.
2. **01 Parcel & satellite evidence** — parcel, season, provider, dataset, method, source file,
   observation counts.
3. **02 Scientific verification** — the verdict with its colour (green `conform`, oxblood
   `nonconform`, amber `inconclusive`), the verdict code, the reason and the frozen policy.
4. **03 Canonical evidence** — commitment id, evidence id, evidence hash (and the hash recomputed
   from the canonical bytes), canonical size and schema version. Hashes are copyable.
5. **04 Blockchain proof** — chain id, registry address, transaction hashes, receipt status,
   the emitted event and the on-chain read-back comparison. Marked as local Anvil.
6. **05 Limitations** — what the result does **not** claim.
7. **06 Integrity checks at generation time** — the five verification flags of the run.

## Regenerating the document

The page always shows the current `data/demo/latest_proof.json`. To regenerate it, run the
real-evidence demonstration (TASK-003A workflow):

```bash
cd contracts
forge build                                  # once, for the deployment bytecode
anvil --host 127.0.0.1 --port 8545 --chain-id 31337      # terminal 1
```

```bash
cd contracts
export ANVIL_RPC_URL=http://127.0.0.1:8545
export ANVIL_PRIVATE_KEY=<a development key Anvil prints at startup>
python smoke_test_real_evidence.py            # writes data/demo/latest_proof.json
```

The demonstration writes the document only after every integrity check passed, and it removes
a stale document when a run fails. Reload the page afterwards.

## Notes

- The page must be served over HTTP (it loads the JSON with `fetch`); opening
  `demo/index.html` directly from the filesystem will not work.
- Design tokens follow `DESIGN_OANA.md`: paper background, navy surfaces, 1 px borders,
  IBM Plex Sans / Newsreader with local fallbacks. Verdict colours are reserved — green is
  used only for `conform`.
