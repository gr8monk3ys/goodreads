from __future__ import annotations

# Goodreads' 2026 write API is AWS AppSync GraphQL (captured live; see
# docs/superpowers/research/write-flows-captured.md). Auth is a short-lived JWT
# the book page mints in __NEXT_DATA__.props.pageProps.jwtToken; mutations target
# the book GID (kca://book/...), not the numeric legacyId.
APPSYNC_URL = "https://kxbwmqov6jgg3daaamb744ycu4.appsync-api.us-east-1.amazonaws.com/graphql"

_SHELVE_MUTATION = (
    "mutation ShelveBook($input: ShelveBookInput!) { "
    "shelveBook(input: $input) { shelving { legacyId id shelf { name displayName } webUrl } } }"
)
# NOTE: only ShelveBook's full query is verified. UnshelveBook's variables shape is
# confirmed (removes successfully); its exact selection set is provisional.
_UNSHELVE_MUTATION = (
    "mutation UnshelveBook($input: UnshelveBookInput!) { "
    "unshelveBook(input: $input) { __typename } }"
)


def build_shelve_request(gid: str, shelf_name: str) -> dict[str, object]:
    """GraphQL request to shelve a book (add/set exclusive shelf). Verified contract."""
    return {
        "operationName": "ShelveBook",
        "variables": {"input": {"id": gid, "shelfName": shelf_name}},
        "query": _SHELVE_MUTATION,
    }


def build_unshelve_request(gid: str) -> dict[str, object]:
    """GraphQL request to remove a book from the user's shelves."""
    return {
        "operationName": "UnshelveBook",
        "variables": {"input": {"id": gid}},
        "query": _UNSHELVE_MUTATION,
    }


def parse_jwt(next_data: dict[str, object]) -> str | None:
    """Extract the AppSync JWT from a parsed __NEXT_DATA__ blob (props.pageProps.jwtToken)."""
    props = next_data.get("props")
    page_props = props.get("pageProps") if isinstance(props, dict) else None
    token = page_props.get("jwtToken") if isinstance(page_props, dict) else None
    return token if isinstance(token, str) and token else None


def parse_gid(next_data: dict[str, object]) -> str | None:
    """Extract the book GID (kca://book/...) from a parsed __NEXT_DATA__ blob."""
    props = next_data.get("props")
    page_props = props.get("pageProps") if isinstance(props, dict) else None
    apollo = page_props.get("apolloState") if isinstance(page_props, dict) else None
    if not isinstance(apollo, dict):
        return None
    for key, val in apollo.items():
        if isinstance(val, dict) and val.get("__typename") == "Book":
            gid = val.get("id")
            if isinstance(gid, str) and gid.startswith("kca://book/"):
                return gid
            if isinstance(key, str) and key.startswith("Book:kca://book/"):
                return key[len("Book:") :]
    return None
