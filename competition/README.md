# Palletizing competition portal — local research preview

Source-owned competition service, independently runnable from the repository.
It does not import or expose the legacy bytecode backend, its default accounts,
its upload/admin endpoints, or the prebuilt React application. It reuses the
white-background Three.js viewer. Researcher code runs on their own machines;
only placement JSON is accepted by the server.

## Implemented

- Frozen benchmark documents, item masters, canonical instance IDs and SHA-256 hashes.
- Google OIDC authorization-code sign-in with state, nonce, PKCE, signature,
  issuer, audience and verified-email checks.
- SMTP sign-in links: ten-minute expiry, one use, bound to the requesting browser.
- Seven-day opaque HttpOnly browser sessions; same-origin checks on mutations.
- Per-researcher strategies, private drafts, batch uploads, owner-only changes.
- Immutable publication and parent revisions that inherit a snapshot of packs.
- Server-derived dimensions, weights, counts, heights, LVE and support validation.
- Fixed benchmark denominators and revision-level leaderboard/comparison.
- Expiring, revocable, hashed API tokens with separate submit/publish scopes.
- A standard stdio MCP connector using the same HTTP API as the website.
- A separate SQLite database with transactions, foreign keys, rate limits and audit events.

## Run locally (Python 3.11+)

From the repository root, using a dedicated virtual environment:

```sh
python -m venv .venv-competition
# Activate it, then:
python -m pip install -r competition/requirements.lock
python -m pip install --no-deps -e .
python -m competition import-dataset
python -m competition serve
```

The local default is `http://127.0.0.1:8769`. Data is stored in
`.competition/portal.sqlite`, not `backend/palletizer.db`. Import reads the
shipped master database in SQLite read-only mode. Startup never creates default
accounts or imports/publishes benchmark results. Google/email buttons remain
disabled until their provider configuration is complete.

For an explicitly local admin preview in PowerShell:

```powershell
$env:LOCAL_ADMIN_LOGIN='1'
$env:PUBLIC_ORIGIN='http://127.0.0.1:8769'
$env:BIND_HOST='127.0.0.1'
python -m competition serve
```

Open **Sign in → Local preview admin** and use `admin` / `admin`. This skips
external identity providers, not ownership checks or pack validation. It permits
submitting and publishing the local account's own revisions and creating local
MCP tokens; it cannot edit other researchers' data. The switch defaults off,
rejects a non-loopback origin/bind address, and rejects forwarded/non-loopback
requests. Local-account sessions and tokens are rejected when the switch is off,
including if the database is later copied to production. Do not expose this
development server through a tunnel or proxy. Restart without the switch to disable.

For a small, explicitly labelled preview with the two available local orders:

```sh
python -m competition import-dataset --preview --id preview-2-v1 --name "Local preview - 2 published orders"
python -m competition import-baselines preview-2-v1
```

`import-baselines` is an explicit operator publication into this LOCAL database.
It imports only files actually present, verifies dimensions/mass before mapping
legacy IDs to canonical SKU-instance IDs, and revalidates every pack. It never
claims an original checkpoint/code revision that was not recorded. These
preview scores are not the official 1,000-order competition leaderboard.

## Production configuration

Intended origin: `https://palletizing-benchmark.org`.
Set the variables documented in `.env.example` in the deployment environment or
secret manager. The server does not silently load `.env` files.

Google setup:

1. Create a Google OAuth **web application** client in the owner's Cloud project.
2. Register the exact redirect URI:
   `https://palletizing-benchmark.org/api/auth/google/callback`.
3. Set `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`. Only `openid email profile`
   is requested; no Gmail/mailbox permissions.
4. Configure the Google consent screen and test actual account sign-in on staging.

Email setup:

1. Use an authenticated SMTP provider with STARTTLS and a verified sending domain.
2. Set `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `MAIL_FROM`.
3. Verify delivery, SPF/DKIM/DMARC and inbox placement with real test accounts.
4. Users must open a link in the same browser that requested it. Tokens are in
   URL fragments (not server query/access logs) and require an explicit sign-in click.

Google and email identities are not automatically merged by matching email.
Use the same provider each time; account linking would require an explicit
verified linking workflow. No Google client secret or SMTP credential is bundled.
Signing in grants researcher permissions, never operator/database administration.

Keep the legacy service off the public deployment. Use the source-owned
`python -m competition serve` entrypoint, with `BIND_HOST=0.0.0.0`, `PORT` from
the host, `PUBLIC_ORIGIN=https://palletizing-benchmark.org` and a durable
`COMPETITION_DB` path. Put TLS and connection/request time limits at the reverse
proxy. A production launch also needs persistent volume/backups, monitoring,
abuse protection and staging verification; this task does not deploy to the domain.

## Submission and revision contract

Download `/api/benchmarks/{id}` for the full frozen dataset, or use the bounded
manifest/order endpoints. Each order supplies canonical box IDs and the SKU
master supplies dimensions and mass. A pack is:

```json
{
  "order_id": "ORDER-ID-FROM-DATASET",
  "boxes": [
    {"id": "SKU-ID:0000", "sku_id": "SKU-ID", "position": {"x": 0.1, "y": 0.1, "z": 0.1}, "rotation": 0}
  ]
}
```

This is a schema illustration, not a valid entry for the real dataset.
Positions are box **centres in metres**, with z up. Only 0°/90° yaw is allowed;
boxes cannot be laid on another face. Dimensions, masses, container sizes and
client-supplied scores are not accepted in uploads. No uploaded code, pickle,
archives or remote artifact URLs are executed/fetched.

REST workflow (also available in the UI and MCP):

1. `POST /api/strategies` with a name/description.
2. `POST /api/strategies/{id}/revisions` with benchmark ID, notes, code/model
   references, configuration and optional published parent revision ID.
3. `PUT /api/revisions/{id}/packs` with `{"packs": [...]}`; up to 25 orders and
   8 MiB per request, up to 1,000 placements per pack. Re-upload replaces those
   orders in the owner's draft. Batch shape/order errors roll back the batch;
   geometric invalidity is saved as an invalid result for diagnosis.
4. `GET /api/revisions/{id}` to inspect the server's reports.
5. `POST /api/revisions/{id}/publish` to make an immutable public snapshot.
   Repeated publication is idempotent. Missing/invalid orders are allowed but
   remain visible and unranked. No edits to a published revision are accepted.
6. Create a child revision to improve packs. No automatic per-order best-of-run
   mixing occurs; inheritance and changed orders are explicitly recorded.

Published metadata must not contain secrets or confidential configuration.
The revision checksum covers benchmark, evaluator version, strategy, parent,
notes, code/model references, configuration and every normalized artifact hash.
It uses Python's documented sorted-key, compact JSON serializer (see
`evaluator.canonical`), not a claim of RFC 8785 canonicalization.

## Evaluation and fairness

`rigid-static-v1.0.0` is a proposed versioned research rule set, not a certified
physical safety model. It checks identity, quantities, allowed yaw, bounds,
non-overlap and gravity support. At every positive-area face contact it creates
four nonnegative vertical reaction forces. A single linear program enforces
vertical force and both horizontal moment balances for every box. Forces on
both sides of an interface have equal-and-opposite signs. Bridges and shared
support paths are included without copying a supported mass down each branch.

Assumptions: rigid boxes, uniform internal density, horizontal face contacts,
gravity only and 1e-6 m geometric tolerance. It does **not** estimate continuous
tipping angle, sliding/friction, dynamic acceleration, deformation, real crush
strength, robot feasibility or whether every intermediate placement was feasible.
A solver timeout/indeterminate result fails closed as `evaluation-limit` and
must be retried/reviewed, not described as proof of physical instability.
Do not use this equilibrium gate to claim that all previous stability research
work is complete. That requires separate model validation and physical testing.

Weight classes are derived from the unweighted mean SKU mass and labelled as a
proxy. They affect admission only when a NEW benchmark is explicitly imported
with `--stacking-rule heavy-not-on-light`; existing benchmark rules never change.
The default imported track has `stacking_rule: none`.

Leaderboard rules:

- All orders in the frozen benchmark remain in the denominator.
- Invalid packs contribute zero accepted boxes; missing orders are visible.
- Only revisions completing **every** order receive a compactness rank.
- LVE = pallet footprint × actual top height / placed item volume, lower tighter.
  Its mean is taken over completed orders. Partial-run LVE is descriptive only.
- Pairwise comparisons use only the common completed orders and report their count.
- Runtime is not ranked because external hardware/time claims are unverified.
- Results are for a public fixed-instance challenge, not proof of generalization
  to held-out customer orders. All historical baseline models are labelled honestly.

Important preview finding: `ORD-19412545` in the saved EP baseline is reported
infeasible by this new static-equilibrium model. Other sampled packs pass. Keep
it flagged, and investigate/agree on the evaluator assumptions before making
this the official competition rule set. Do not silently waive it to improve scores.

## MCP onboarding

Install the project in the researcher's environment (`pip install .` installs
the MCP client dependencies; the server uses the separate locked environment).
Sign in on the portal, open **MCP access**, and create an expiring token. By
default it can submit drafts but not publish. Grant `publish` only intentionally.

```json
{
  "mcpServers": {
    "palletizing": {
      "command": "palletizing-mcp",
      "env": {
        "PALLETIZING_API_URL": "https://palletizing-benchmark.org",
        "PALLETIZING_API_TOKEN": "SET_IN_YOUR_CLIENT_SECRET_SETTINGS"
      }
    }
  }
}
```

Use an absolute executable path if the client cannot find `palletizing-mcp`.
Thirteen tools cover benchmark manifests, paged orders, individual orders,
schema, owned strategies, draft creation, upload, inspection, comparison,
publication and leaderboard. `publish_revision` additionally requires
`confirm=true`; its description requires researcher approval. All ownership
and token-scope checks are enforced on the API server regardless of the client.

This is **stdio MCP**, with a local connector making HTTPS calls to the portal.
It is not a hosted `/mcp` OAuth endpoint. A future remote MCP endpoint would need
the protocol's OAuth discovery/resource-audience flow rather than reusing a
Google ID token as an API bearer token. Never paste API tokens into chat or Git.

## Tests

```sh
python -m pytest competition/tests -q
node --test tests/order-panel.test.cjs tests/portal.test.cjs
node --check competition/static/portal.js
```

Tests include global bridge/column equilibrium, lower-interface failure,
identity and geometry gates, fixed denominators, owner isolation, publication
immutability, inherited revisions, transaction rollback, token revocation,
CSRF, email delivery mocked at the SMTP boundary, locally signed Google tokens
(including invalid signature/issuer/audience/nonce), and a real stdio MCP client
round trip through an HTTP server and SQLite. Real Google/SMTP delivery and
production deployment remain configuration-dependent staging checks.

## Licensing / launch status

New code under `competition/` is MIT, copyright 2026 Brandon Coats, per LICENSE.
That grant does not relicense third-party viewer libraries, the pre-existing
bytecode/compiled site, dataset or researchers' algorithms/submissions. Preserve
upstream notices and confirm any needed permissions before redistributing them.
The dataset currently says `Not specified`: choose and document its reuse terms,
then import a new benchmark version with `--license` before a public launch.
Participants also need explicit submission/publication terms. Competitors are
not required by this code's MIT license to open-source their own algorithms.
