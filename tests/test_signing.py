"""Request signing against vectors from Ionic's own code (D-52; API-01, AUTH-03).

`tests/fixtures/ionic/signing.json` was produced once by running Ionic's
`buildRequestAuthHeaders` under Node (`tools/capture_ionic_reference/README.md`).
The client and the mock share `core/signing.py`, so these outside vectors are what
would catch a mistake both sides make.
"""

import hashlib
import json
from pathlib import Path

import pytest

from pycon_us.core.signing import auth_headers, canonical_body, enc, js_round, sign

FIXTURE = Path(__file__).parent / "fixtures" / "ionic" / "signing.json"
VECTORS = json.loads(FIXTURE.read_text(encoding="utf-8"))
CASES = {case["name"]: case for case in VECTORS["cases"]}
FETCH_PRODUCTS = (
    "/2027/api/v1/check_in/fetch_products/"
    "?attendee_access_code=ABC123&category_pk_list=1,2&mode=redemption_mode"
)


def body_of(case: dict) -> bytes:
    """The body bytes we would send for a case: our serialisation of its payload, or none."""
    return canonical_body(case["payload"]) if "payload" in case else b""


def path_of(case: dict) -> str:
    """The path we would request for a case, its query built as that Ionic call builds it."""
    query = case.get("query")
    if query is None:
        return case["path"]
    value = enc if query["encoded"] else str
    params = "&".join(f"{name}={value(raw)}" for name, raw in query["params"])
    return f"{query['base']}?{params}"


def test_the_vectors_come_from_ionic_at_the_pinned_versions() -> None:
    """The fixture records Ionic's commit and the sha1-uint8array its lock file resolves."""
    captured = VECTORS["captured"]
    assert (
        captured["ionic"]
        == "PyCon/pycon-us-mobile@2aa6df8a86890df2d243f9e165905957614ae47e"
    )
    assert captured["packages"] == {"sha1-uint8array": "0.10.7"}
    assert {"node", "npm", "esbuild", "date"} <= captured.keys()


def test_every_case_the_issue_lists_is_captured() -> None:
    """The vectors cover encoding, bodies, query order, rounding and null credentials."""
    assert set(CASES) == {
        "get-empty-body",
        "get-query-encoded",
        "get-query-encoded-reordered",
        "get-query-unencoded",
        "patch-favorites",
        "post-note-non-ascii",
        "post-escapes",
        "post-redeem-dynamic-keys",
        "post-mask-violation-force",
        "round-below-half",
        "round-half-even",
        "round-half-odd",
        "round-above-half",
        "null-credentials",
    }


@pytest.mark.parametrize("name", list(CASES))
def test_the_signature_matches_ionic(name: str) -> None:
    """Our path, body, timestamp and signature equal Ionic's, byte for byte."""
    case = CASES[name]
    path, body = path_of(case), body_of(case)
    timestamp = js_round(case["now_ms"] / 1000)
    assert path == case["path"]
    assert body == case["body"].encode("utf-8")
    assert str(timestamp) == case["headers"]["X-API-Timestamp"]
    assert (
        sign(case["secret"], timestamp, case["method"], path, body)
        == case["headers"]["X-API-Signature"]
    )


@pytest.mark.parametrize("name", list(CASES))
def test_the_headers_match_ionic(name: str) -> None:
    """The headers helper gives Ionic's three headers from the key, secret and current time."""
    case = CASES[name]
    headers = auth_headers(
        case["key"],
        case["secret"],
        case["now_ms"] / 1000,
        case["method"],
        path_of(case),
        body_of(case),
    )
    assert headers == case["headers"]


def test_a_missing_secret_signs_as_an_empty_one() -> None:
    """Signed out, a None secret signs as Ionic's join() renders null: as "", not "None"."""
    args = (1747324800, "GET", "/2027/api/v1/user/check_features/")
    assert sign(None, *args) == sign("", *args) != sign("None", *args)


def test_the_query_order_changes_the_signature() -> None:
    """The same parameters in another order sign differently: the query is signed as sent."""
    first = CASES["get-query-encoded"]["headers"]["X-API-Signature"]
    second = CASES["get-query-encoded-reordered"]["headers"]["X-API-Signature"]
    assert first != second


def test_a_half_second_rounds_up_where_python_rounds_to_even() -> None:
    """At x.5 s with x even, Math.round goes up and Python's round goes down."""
    case = CASES["round-half-even"]
    seconds = case["now_ms"] / 1000
    assert round(seconds) == 1747324800
    assert js_round(seconds) == int(case["headers"]["X-API-Timestamp"]) == 1747324801


@pytest.mark.parametrize(
    ("x", "expected"),
    [
        (0.5, 1),
        (1.5, 2),
        (2.5, 3),
        (-0.5, 0),
        (-1.5, -1),
        (-2.5, -2),
        (0.49999999999999994, 0),
        (2.4999999999999996, 2),
        (1747324800.5, 1747324801),
    ],
)
def test_js_round_rounds_halves_up(x: float, expected: int) -> None:
    """js_round matches Math.round at and just below halves, negatives included."""
    assert js_round(x) == expected


@pytest.mark.parametrize(
    ("method", "path", "body", "signature"),
    [
        (
            "GET",
            "/2027/api/v1/user/mobile_state/",
            b"",
            "77946e44677e7f97445336dd9de5f0a0b58dc016",
        ),
        (
            "PATCH",
            "/2027/api/v1/user/mobile_state/",
            canonical_body({"favorites": ["123", "poster-detail-7"]}),
            "59b274bd80705949c06a5fd31abfe5f54307dc26",
        ),
        (
            "POST",
            "/2027/api/v1/lead_retrieval/ABC123/note/",
            canonical_body(
                {"accessCode": "ABC123", "note": "Interest: hot\nNotes: café"}
            ),
            "798ff969a24a536d3df9f504dcb16987f73dbd41",
        ),
        (
            "GET",
            FETCH_PRODUCTS,
            b"",
            "3b49566459ec1ee2a43bdae2a2d87835c9aada52",
        ),
    ],
)
def test_the_architecture_vectors(
    method: str, path: str, body: bytes, signature: str
) -> None:
    """The four vectors of architecture §10.3 hold, and equal a plain hashlib SHA-1."""
    assert sign("s3cr3t", 1747324800, method, path, body) == signature
    base = b"s3cr3t1747324800" + method.encode() + path.encode() + body
    assert hashlib.sha1(base).hexdigest() == signature


def test_the_body_keeps_non_ascii_and_escapes_as_json_stringify() -> None:
    """Non-ASCII stays as UTF-8; quotes, backslashes and control characters are escaped."""
    body = canonical_body({"a": 'é "q" \\ /\n\t\x01', "b": [1, True, None]})
    assert body == '{"a":"é \\"q\\" \\\\ /\\n\\t\\u0001","b":[1,true,null]}'.encode()


def test_enc_keeps_what_encode_uri_component_keeps() -> None:
    """Our encoder escapes everything but letters, digits and -_.!~*'() as UTF-8 percent-escapes."""
    assert enc("AZaz09-_.!~*'()") == "AZaz09-_.!~*'()"
    assert enc("a b/c?d=e&f+g,h:ä") == "a%20b%2Fc%3Fd%3De%26f%2Bg%2Ch%3A%C3%A4"
