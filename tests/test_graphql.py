from gr_autopilot.actions.graphql import (
    build_shelve_request,
    build_unshelve_request,
    parse_gid,
    parse_jwt,
)

GID = "kca://book/amzn1.gr.book.v1.tlO_PYZREqIcBeayzhXEYA"


def test_build_shelve_request() -> None:
    r = build_shelve_request(GID, "to-read")
    assert r["operationName"] == "ShelveBook"
    assert r["variables"] == {"input": {"id": GID, "shelfName": "to-read"}}
    assert "mutation ShelveBook" in str(r["query"])


def test_build_unshelve_request() -> None:
    r = build_unshelve_request(GID)
    assert r["operationName"] == "UnshelveBook"
    assert r["variables"] == {"input": {"id": GID}}


def test_parse_jwt() -> None:
    nd: dict[str, object] = {"props": {"pageProps": {"jwtToken": "ey.token.sig"}}}
    assert parse_jwt(nd) == "ey.token.sig"
    assert parse_jwt({"props": {"pageProps": {}}}) is None
    assert parse_jwt({}) is None


def test_parse_gid_from_id_field() -> None:
    nd: dict[str, object] = {
        "props": {"pageProps": {"apolloState": {"Book:abc": {"__typename": "Book", "id": GID}}}}
    }
    assert parse_gid(nd) == GID


def test_parse_gid_from_key_fallback() -> None:
    nd: dict[str, object] = {
        "props": {"pageProps": {"apolloState": {f"Book:{GID}": {"__typename": "Book"}}}}
    }
    assert parse_gid(nd) == GID


def test_parse_gid_none_when_no_book() -> None:
    assert parse_gid({"props": {"pageProps": {"apolloState": {}}}}) is None
