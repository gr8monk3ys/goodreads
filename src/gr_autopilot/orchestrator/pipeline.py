from __future__ import annotations

from gr_autopilot.config import Settings
from gr_autopilot.orchestrator.run import RunSummary

# Integration wiring that constructs the REAL components (bge embedder, Claude
# client, public catalog, Playwright write backend). Requires the voice/generate
# extras + ANTHROPIC_API_KEY (+ browser extra for live writes).
# Omitted from unit coverage; exercised end-to-end on a configured machine.
#
# The vector store is the in-memory one: the corpus is a few dozen reviews and
# prepare_corpus rebuilds the index every run anyway, so a persistent store
# (formerly Chroma, dropped for GHSA pre-auth code injection with no fixed
# release) bought nothing but the dependency.


def run_pipeline(
    dry_run: bool = True, limit: int | None = None, enrich: bool = False
) -> RunSummary:
    """Wire real components: (optionally) enrich genres, build the voice index, then review.

    enrich=True fetches genres for books missing them (public read, no auth) before
    indexing. Dry-run uses the NullBackend (no writes); live uses the Playwright
    backend, which raises until its selectors are captured (see the runbook).
    """
    from gr_autopilot.actions.core import NullBackend
    from gr_autopilot.catalog.goodreads_public import GoodreadsPublicCatalog
    from gr_autopilot.generate.anthropic_client import AnthropicChatClient
    from gr_autopilot.generate.generator import generate_review
    from gr_autopilot.generate.prompt import TargetBook
    from gr_autopilot.orchestrator.run import prepare_corpus, review_unreviewed
    from gr_autopilot.store.db import connect, init_db
    from gr_autopilot.voice.embedder import SentenceTransformerEmbedder
    from gr_autopilot.voice.memory_store import InMemoryVectorStore

    settings = Settings()
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(settings.db_path)
    init_db(conn)

    embedder = SentenceTransformerEmbedder()
    store = InMemoryVectorStore()
    client = AnthropicChatClient()

    catalog = GoodreadsPublicCatalog() if enrich else None
    prepare_corpus(conn, embedder=embedder, store=store, catalog=catalog)

    def generate_text(book: TargetBook) -> str:
        return generate_review(
            book, client=client, embedder=embedder, store=store, model=settings.model
        ).text

    return review_unreviewed(
        conn,
        generate_text=generate_text,
        backend=NullBackend(),
        settings=settings,
        dry_run=dry_run,
        limit=limit,
    )
