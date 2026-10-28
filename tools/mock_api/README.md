# Mock PyCon API: the contract

The private PyCon API (`/<year>/api/v1/`) as the app's client and our mock server both follow it (D-50, NEW-08,
API-12). Our only specification is the Ionic client, so every row below cites
[PyCon/pycon-us-mobile](https://github.com/PyCon/pycon-us-mobile) at `2aa6df8a86890df2d243f9e165905957614ae47e`:
`pycon-api.ts` means `src/app/providers/pycon-api.ts`, and other files are named from `src/app/`. The research
behind it is [`docs/research/ionic/staff-tools-auth.md`](../../docs/research/ionic/staff-tools-auth.md) §0.3, §0.4
and §12.

Three kinds of statement live here, and each says which it is:

- **Ionic:** what Ionic's code sends and reads, with its lines. This is fact about the client.
- **2019:** what the public 2019 server (`PyCon/pycon2019`, `pycon/pycon_api/`) did
  ([context-and-ecosystem](../../docs/research/context-and-ecosystem.md), the signed API row). It may have changed.
- **Mock:** a modelling choice of ours where the client code cannot tell us (see [Unknown](#unknown)). It is not a
  fact about the PSF's server.

## Boundaries (D-06, D-51)

- The mock never points at, proxies or copies a PSF host. Nothing here or in the app calls a private PSF endpoint;
  the app's client refuses any `/api/v1` request to a `*.pycon.org` host (architecture §10.1).
- Nothing test-only lives in the app. The seed data, the fake keys and secrets, the faults and the badge sheet all
  live in `tools/mock_api/` and `tests/fixtures/mock/`; the app only learns the mock's base URL from the Developer
  screen.

## Signing (D-52; `pycon-api.ts` 25-45)

Every call except `authenticate` carries three headers, built by `buildRequestAuthHeaders(method, url, body)`:

| Header | Value | Ionic |
|---|---|---|
| `X-API-Key` | the `key` from `authenticate` | 26, 39 |
| `X-API-Timestamp` | `String(Math.round(Date.now() / 1000))`: integer seconds, rounded half up | 29, 41 |
| `X-API-Signature` | lower-case hex SHA-1 (not HMAC) of the UTF-8 base string | 40 |

The base string is `[secret, timestamp, method, url, body].join("")` (30-36), with no separators:

- `method` is the upper-case verb (`GET`, `POST`, `PATCH`).
- `url` is the path with its query, from `/<year>/` on, with no scheme or host: exactly the string the request is
  sent with. Each endpoint builds its query its own way (the table below); the client must sign the bytes it sends.
- `body` is `''` for a GET and the exact `JSON.stringify(payload)` string for a POST or PATCH, the same string that is
  sent with `Content-Type: application/json`. Key order is insertion order, so it changes the signature.
- `Array.join` renders `null` and `undefined` as `''`, never as `"null"`.

Python's side is `core/signing.py` (architecture §10.3), shared by the client and the mock. Its test vectors come from
running Ionic's own `buildRequestAuthHeaders` under Node, committed in `tests/fixtures/ionic/signing.json` with their
provenance (#662; the capture is described in [`tools/capture_ionic_reference/`](../capture_ionic_reference/)).

**2019:** `APIAuth.verify_request` computed the same SHA-1 over `request.get_full_path()` and rejected timestamps more
than 600 s from the server's clock. **Mock:** it verifies the signature over the raw request target exactly as
received (no decoding or re-encoding) and the body bytes exactly as received, with `hmac.compare_digest`.

## Endpoints

All paths are under `/<year>/api/v1/`; Ionic hard-codes `/2026/`. The table lists every `buildRequestAuthHeaders`
call site in `pycon-api.ts` (the "Signs at" column), plus the unsigned `authenticate`.

| Name | Method and path | Query or body | Timeout | Signs at | Ionic lines |
|---|---|---|---|---|---|
| `authenticate` | POST `authenticate/` | `{"email", "password"}` (Angular serialises it) | 3 s | unsigned | `pages/login/login.ts` 21, 58-67 |
| `check_features` | GET `user/check_features/` | none | 2 s | 52 | 47-62 |
| `mobile_state` (read) | GET `user/mobile_state/` | none | 2 s | 69 | 64-78 |
| `mobile_state` (write) | PATCH `user/mobile_state/` | `{"favorites": [...]}` | 2 s | 86 | 80-101; payload `providers/user-data.ts` 134, 156, 173 |
| `redeemable` | GET `check_in/redeemable/` | none | 2 s | 108 | 103-117 |
| `attendees_by_product` | GET `check_in/attendees_by_product/<id>/` | none | 2 s | 124 | 119-133; **never called**, not ported (API-05) |
| `inventory` | GET `check_in/attendees_by_product_with_quantity/<id>/` | none | 20 s | 140 | 135-149; one call per product, `pages/door-check/door-check.page.ts` 388-390 |
| `fetch_products` (swag) | GET `check_in/fetch_products/?attendee_access_code=<code>&category_pk_list=<a,b>&mode=redemption_mode` | query **not encoded** | 10 s | 156 | 151-165 (URL 153); `pages/t-shirt-redemption/t-shirt-redemption.page.ts` 36-37, 254-256 |
| `fetch_products` (door) | GET `check_in/fetch_products/?attendee_access_code=<code>&product_pk_list=<a,b>&mode=door_check_mode` | query **not encoded** | 10 s | 172 | 167-181 (URL 169); `door-check.page.ts` 298 |
| `redeem` | POST `check_in/redeem_products/` | see [Redeem payloads](#redeem-payloads) | 10 s | 189 | 183-199 |
| `coc_attendees` | GET `mask_violations/attendees/` | none | 15 s | 206 | 201-216; `pages/mask-violation/mask-violation.page.ts` 86-89 |
| `coc_capture` (scan) | GET `mask_violations/capture/?attendee_access_code=<enc>` | `encodeURIComponent` | 5 s | 243 | 218-252 (URL 223-224); `mask-violation.page.ts` 206 |
| `coc_capture` (name search) | POST `mask_violations/capture/` (no query) | `{"attendee_access_code", "notes"?, "force"?: true}` | 5 s | 231 | 222, 226-230; `mask-violation.page.ts` 176-177 |
| `lead_sponsors` | GET `lead_retrieval/sponsors/` | none | 5 s | 258 | 254-263; `pages/map/map.ts` 367-419 |
| `lead_capture` | GET `lead_retrieval/capture/?attendee_access_code=<enc>&badge_validator=<enc>[&sponsor_id=<enc>]` | `encodeURIComponent` | 2 s | 304 | 273-335 (URL 298-301) |
| `lead_note` | POST `lead_retrieval/<code>/note/` | `{"accessCode", "note"[, "sponsor_id"]}` | 2 s | 353 | 337-371 (body 347, 350; path 349) |

Details a port gets wrong:

- **Badges** are QR codes `<access code>:<validator>`. Door and swag take the validator as `split(':')[1]`
  (`door-check.page.ts` 178-179, `t-shirt-redemption.page.ts` 153); the lead scanner takes the **last** segment
  (`pycon-api.ts` 292-294). Every page takes the access code as `split(':')[0]`.
- **`fetch_products`** joins the ids with `,` and interpolates the access code raw (153, 169), while CoC and lead
  capture encode every value with `encodeURIComponent` (224, 298-301). The client builds each query the Ionic way and
  never through `httpx`'s `params=` (API-06).
- **`coc_capture`** switches method on its options (222): a POST with a body when there are notes or `force`, else a
  GET with the query. The name-search page always sends `force: true` and adds `notes` only when non-empty (176-177,
  227-229).
- **`lead_capture`** adds `sponsor_id` only when a staff member scans on behalf of a sponsor (`storage`
  `staff-sponsor-id`, 297-301). A sponsor's own account sends none.
- **`lead_note`** puts the access code in the path unencoded (349) and sends the note composed by the note modal,
  e.g. `"Interest: hot\nFollow-up: Send info\nNotes: …"` (`lead-note-modal/lead-note-modal.component.ts` 69-86). The
  app encodes the code (API-11), so the mock decodes that one path segment to find the attendee, and still checks the
  signature over the raw target.
- **`mobile_state` PATCH** is fire-and-forget in Ionic (95-100); its reply is ignored. **Mock:** the list sent
  replaces the stored one (no merge) and the reply is `{"favorites": [...]}`, the list now stored. Ids are kept as
  strings (D-42): an integer id is stored as its decimal string, and any other item (a float, a boolean, `null`) is
  400, so no id depends on how a float prints (`1.0` from Python's `json.dumps`, `1` from `JSON.stringify`). A string
  UTF-8 can't encode (a lone surrogate such as `"\ud800"`) is 400 too, and the stored list stays as it was.

### Redeem payloads

Both pages send insertion-ordered keys: the three fixed keys, then one pair per product.

| Page | Payload | Ionic |
|---|---|---|
| Door check | `{"attendee_access_code", "badge_validator", "scanned_at", "product-redeem-<id>": <id>, "product-<id>-quantity": <qty>, ...}`; a badge without `:` gives an `undefined` validator, which `JSON.stringify` **omits** | `door-check.page.ts` 177-188 |
| Swag pickup | the same keys; a missing validator is sent as `""`, `scanned_at` defaults to now, and the `<id>` keys come from `Object.entries`, so the value of `product-redeem-<id>` is the id as a **string** | `t-shirt-redemption.page.ts` 153-165; ids from `redemption-modal/redemption-modal.component.ts` 29, 50 |

`scanned_at` is an ISO 8601 string from `Date.toISOString()` (UTC, milliseconds, `Z`).

## Replies

Ionic reads most replies **bare**, at the top level, and only the CoC and lead-capture replies inside a `data` member.
The 2019 server wrapped every reply as `{"code", "data"}` and every error as `{"code", "error"}`; Ionic's reads show
the 2026 server keeps that envelope only for those endpoints, or Ionic would find no flags, favourites or products.
**Mock:** it replies exactly in the shape Ionic reads, per endpoint.

| Name | Reply (fields Ionic reads) | Shape | Ionic reads at |
|---|---|---|---|
| `authenticate` | `nickname`, `email`, `key`, `secret`, `features.{lead_retrieval, door_check_in, mask_violation, is_speaker}` | bare | `providers/user-data.ts` 182-192; `login.ts` 46 |
| `check_features` | `features.{lead_retrieval, door_check_in, mask_violation}` (an absent flag is `undefined`: treat as false) | bare | `user-data.ts` 61-66 |
| `mobile_state` (read) | `favorites`: a list of session ids | bare | `user-data.ts` 76-85 |
| `redeemable` | `redeemable_categories: [{id, name}]`, `redeemable_products: [{id, name, category}]`; door keeps categories not matching `/shirt\|swag/i`, swag the others | bare | `door-check.page.ts` 463-478; `t-shirt-redemption.page.ts` 311-326 |
| `inventory` | a list `[{id (the access code), quantity, name?, dietary?, has_allergy?, allergy?}]`; **Mock:** one row per attendee who bought the product, `quantity` the quantity bought (not what is left: the door keeps its own "already checked in"), every optional field sent | bare list | `door-check.page.ts` 390-427 |
| `fetch_products` | `attendee_access_code`, `attendee_name`, `attendee_id`, `has_items_to_redeem`, `redeemable_products_by_category: {"<category name>": [{product_id, product_name, redeemable, purchased}]}`; door also `dietary`, `has_allergy`, `allergy` | bare | `t-shirt-redemption.page.ts` 119-130; `door-check.page.ts` 300-324 |
| `redeem` | `errors: [{message}]` (shown joined by `; ` as "Partial redemption: …") and `redeemable_products_by_category` (what this call redeemed; empty means "Nothing was redeemed"). **Mock:** each product redeemed is listed in `fetch_products`'s item shape with `redeemable` what is left after it; a product not bought, already redeemed or asked for more than is left is an `errors` entry, and the others still go through | bare | `t-shirt-redemption.page.ts` 167-185; door stores the whole reply, 190-192 |
| `coc_attendees` | `data: [{access_code, full_name, nickname, badge_name, violations}]` | `{code, data}` | `mask-violation.page.ts` 88-93 |
| `coc_capture` | `data.{nickname, full_name, badge_name, email, violations}` | `{code, data}` | `mask-violation.page.ts` 55-67; `mask-violation.page.html` 90-109 |
| `lead_sponsors` | `sponsors: [{id, name, booth_number?, logo_url?}]` | bare | `map.ts` 370, 392-396, 411 |
| `lead_capture` | `data.first_name` (Ionic stores the whole reply) | `{code, data}` | `pycon-api.ts` 326-330; `map.ts` 91, 186-193 |
| `lead_note` | nothing; **Mock:** `{"code": 200, "data": {}}` | any | `pycon-api.ts` 363-368 |

### Errors

- **`authenticate`:** Ionic shows the error body's `message` as the toast `"Invalid Auth: " + message`, and nothing at
  all when there is no `message` (`login.ts` 34-41, 74-79). **Mock:** a wrong email or password is `401
  {"message": "Invalid email or password."}`.
- **Signed calls:** Ionic reads no error body; it logs and rethrows (`catchError` at every timeout above).
  **Mock:** every error is `{"code": <status>, "error": "<message>"}`, the 2019 shape; the client's
  `ApiError.message` is the `error` (or `message`) string.
- **Mock statuses:** 401 for a missing or unknown `X-API-Key` (or a key revoked by a fault); 403 for a missing or
  malformed timestamp (anything but ASCII digits with no sign or leading zero, the string Ionic sends), a timestamp more than 600 s from the mock's clock, or a wrong signature; 403 also for an
  account without the endpoint's role flag (see [Role gates](#role-gates)); 404 for an unknown
  route (method and path, trailing slash included; checked before the signature), year, product, category, sponsor or attendee (access code), a `badge_validator` that doesn't match the badge
  (lead capture checks it always, `redeem` only when non-empty), and a note for a lead
  this sponsor hasn't captured; 400 for a body that is not a JSON object (`authenticate`'s included, in the `{code, error}` shape), a missing or malformed query parameter or body field, an
  unknown `fetch_products` mode, a staff lead call without `sponsor_id`, and a note whose `accessCode` isn't the path's. An error message never echoes the request. Every reply
  is JSON with a `Date` header from the mock's clock, which the client uses to learn clock skew (D-53). Replies are
  serialised like request bodies (`core/signing.py`'s `canonical_body`) and carry no floats.

### Role gates

Ionic shows each tool by flag (`map.ts` 308-320 and the menu, research §0.6) and reads no error body, so a wrong role
only logs. **Mock:** the server enforces the same gates and answers a wrong role `403 {"code": 403, "error": "This
account's role can't use this endpoint."}`, after the signature check.

| Endpoints | Flag |
|---|---|
| `check_in/*` (door and swag) | `door_check_in` |
| `mask_violations/*` | `mask_violation` |
| `lead_retrieval/*` | `lead_retrieval` or `door_check_in` |

A lead goes to the sponsor the request names (`sponsor_id`, in the capture query or the note body, a string as Ionic
stores it), else to the account's own sponsor. **Mock:** an account without `door_check_in` may name only its own
sponsor (403 otherwise), and a call that names none from an account with no sponsor of its own is 400.

## Unknown

What the client code cannot tell us (research §12), and how the mock models each. Every "Mock" here is our choice,
made so the client's behaviour can be tested both ways where it matters; none is a fact about the PSF's server.

| Open point | Mock |
|---|---|
| Is `lead_retrieval/capture` idempotent? A response lost after the server committed makes the client send it again. | Both, selected by `MockState(capture="idempotent" \| "non_idempotent")` (D-57). Idempotent: one lead per (sponsor, attendee); a repeat returns 200 with the same reply. Non-idempotent: every request adds a lead row, so a lost response yields a duplicate the tests detect. |
| Is `redeem_products` idempotent for a repeated door payload (Ionic re-sends every 60 s until it gets an answer)? | The same switch. Idempotent: a product already redeemed with the same (attendee, quantity, `scanned_at`) is listed as redeemed again and nothing more is redeemed, so a repeated payload gets the first reply. Non-idempotent: a repeat redeems again while quantity is left, then reports `errors`. |
| What `force` means on `mask_violations/capture`, and whether the per-frame GET is de-duplicated. | POST with `force: true` always records an incident (with its `notes`). GET, and a POST without `force`: idempotent mode records at most one incident per attendee per 60 s and otherwise returns the current count; non-idempotent mode records one per request. |
| The timestamp window. | 600 s either side of the mock's clock (**2019**; the current value is UNCONFIRMED). The clock is injectable, and `--skew SECONDS` shifts it. |
| Status codes for a bad key versus a bad signature or timestamp, and for an invalid badge. | 401 unknown key; 403 bad signature or timestamp outside the window; 404 invalid badge (see [Errors](#errors)). The client treats 401 and 403 alike (`ApiError.is_auth`), so only the mock's own tests depend on the split. |
| How the server rebuilds the signed path (Django's `get_full_path()` re-escapes the path). | The raw request target as received. Ionic's unencoded `fetch_products` query is safe only while access codes and ids are URL-safe; the mock's are. |
| The full reply schemas, and whether `authenticate` returns more than the fields above. | Only the fields in [Replies](#replies), with plausible values; nothing more. |
| Whether sponsor names arrive JSON-quoted (`map.ts` 59, 83, 93 and 317 strip `"` around a stored name, which suggests a past bug). | One seeded sponsor's name arrives with literal quotes, so the client's stripping is exercised; the others are plain. |
| Whether the server checks `badge_validator` on `redeem_products` (door omits it, swag may send `""`). | Checked only when non-empty: a wrong one is 404. |

## Seed data (`tests/fixtures/mock/`)

`MockState.from_seed(capture=...)` loads one JSON file, `tests/fixtures/mock/seed.json`, into a fresh state each
time. Every name in it is made up, every email is at `example.com`, and every password, key and secret is fake
(`mock-<role>`, `mock-key-<role>`, `mock-secret-<role>`) and works only against the mock. Its shape:

```json
{
  "year": 2026,
  "accounts": [
    {"role": "sponsor", "email": "sponsor@example.com", "password": "mock-sponsor", "nickname": "Sam Sponsor",
     "key": "mock-key-sponsor", "secret": "mock-secret-sponsor", "sponsor_id": 1, "favorites": [],
     "features": {"lead_retrieval": true, "door_check_in": false, "mask_violation": false, "is_speaker": false}}
  ],
  "sponsors": [{"id": 1, "name": "Example Corp", "booth_number": "101", "logo_url": null}],
  "categories": [{"id": 1, "name": "Tutorials"}, {"id": 3, "name": "T-Shirt"}],
  "products": [{"id": 10, "name": "Wed May 13 9:00 AM - All about decorators", "category": 1}],
  "attendees": [
    {"id": 1, "access_code": "MOCK0001", "validator": "v4l1d01", "first_name": "Ada", "full_name": "Ada Example",
     "nickname": "ada", "badge_name": "Ada", "email": "ada@example.com", "violations": 0,
     "dietary": "", "has_allergy": false, "allergy": "", "products": {"10": 1}}
  ]
}
```

- **Accounts:** one per role, each with its flags and its `favorites` (strings): `attendee` (no flags), `speaker` (`is_speaker`), `sponsor`
  (`lead_retrieval`, with the `sponsor_id` its leads go to), `staff` (`door_check_in`: door, swag, and lead scanning on
  behalf of a sponsor, as Ionic's `map.ts` 308-320 treats a door-check account without lead retrieval) and `coc`
  (`mask_violation`), plus `all` with every flag. The `attendee` account sends only `lead_retrieval: false` and leaves
  the other flags out, to exercise "absent means false". `role` is for the seed and the tests; no reply carries it.
- **Sponsors:** three: `Example Corp` (booth and logo), `"Quoted Labs"` with literal quotes (see [Unknown](#unknown);
  no logo) and `Sample Systems` (neither; a missing booth or logo is left out of the reply). The `sponsor` and `all`
  accounts belong to sponsor 1.
- **Categories and products:** two session categories (`Tutorials`, `Summits`) and two swag ones (`T-Shirt`,
  `Swag Bag`, matching `/shirt|swag/i`), so both filters have something to keep; tutorial names carry Ionic's
  `Wed May 13 9:00 AM - …` prefix, which the door sorts by.
- **Attendees:** four (`MOCK0001` to `MOCK0004`, validators `v4l1d01` to `v4l1d04`), each with its `id`, the fields the
  replies above return, its prior Code of Conduct incidents (`violations`: 0, 1, 3, 0), and the quantity of each
  product bought (`products`, product id to quantity: two T-shirts for `MOCK0001`, two seats at a tutorial for
  `MOCK0003`, nothing for `MOCK0004`).
  The printable badge sheet (`badges.py`) is made from them.
- `year` is the conference year the mock serves; requests for another year are 404.

### What the mock records

The state keeps every write in order, so tests count how often a capture was applied under each semantics (D-57):
`leads` (sponsor, access code, time), `notes` (sponsor, access code, note, time), `redemptions` (access code,
product, quantity, `scanned_at`) and `incidents` (access code, notes, forced, time). Under `capture="idempotent"`
the same lead capture or door payload twice leaves one row; under `"non_idempotent"`, two (a redemption only while
quantity is left). An idempotent mock also keeps each redeem request's first reply in `redeem_replies` and
answers a retry with it. Incident counts in replies are the seeded `violations` plus the recorded incidents.

## Code

- `handlers.py`: the pure `handle(state, method, raw_path, headers, body) -> (status, headers, body)`. It does no
  I/O and reads the time only from `MockState.now`, which tests replace with a fixed clock. It checks the route (the
  `SIGNED` table, where `{}` matches one path segment), then the key, timestamp and signature
  (`hmac.compare_digest` against `core/signing.py`'s `sign` over the raw target and body as received), then runs the
  endpoint with a `Call` (the account, the time, the raw query, the path segment and the body). It also holds the
  account endpoints.
- `state.py`: `MockState` (the seed, the capture semantics and the records above), `Call`, and `Refused`, an error
  reply in the `{code, error}` envelope.
- `parse.py`: reads JSON bodies, raw (`fetch_products`) and percent-decoded (CoC, lead capture) queries, and id lists.
- `check_in.py`, `conduct.py`, `leads.py`: the staff endpoints for door and swag, Code of Conduct, and lead
  retrieval, each behind its [role gate](#role-gates).
- `transport.py`: `mock_transport(state)`, an `httpx.MockTransport` over `handle` that passes `request.url.raw_path`
  and `request.content` unchanged, for client tests.
- Tests: `tests/test_mock_api.py` (routing, envelopes, the signature check and Ionic's vectors),
  `tests/test_mock_api_accounts.py` (the account endpoints, directly and through the transport),
  `tests/test_mock_api_check_in.py` (the role gates, door and swag, both semantics) and
  `tests/test_mock_api_leads.py` (Code of Conduct and leads, both semantics), with helpers in
  `tests/mock_calls.py`.

## Running it

To come with the server: [`docs/development.md`](../../docs/development.md) §6 has the planned command, faults and
base URLs, and this section will document the final options.
