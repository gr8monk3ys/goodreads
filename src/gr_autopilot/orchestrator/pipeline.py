from __future__ import annotations

from gr_autopilot.config import Settings
from gr_autopilot.orchestrator.run import RunSummary, review_unreviewed

# Integration wiring that constructs the REAL components (bge embedder, Chroma
# store, Claude client, Playwright write backend). Requires the voice/generate/
# browser extras + ANTHROPIC_API_KEY + a built index + a captured session.
# Omitted from unit coverage; exercised end-to-end on a configured machine.


def run_review(dry_run: bool = True, limit: int | None = None) -> RunSummary:
    """Wire up real components and run the review workflow.

    Dry-run uses the NullBackend (no writes). Live uses the Playwright backend,
    which currently raises until its selectors are captured (see the runbook).
    """
    from gr_autopilot.actions.core import NullBackend
    from gr_autopilot.generate.anthropic_client import AnthropicChatClient
    from gr_autopilot.generate.generator import generate_review
    from gr_autopilot.generate.prompt import TargetBook
    from gr_autopilot.store.db import connect, init_db
    from gr_autopilot.voice.chroma_store import ChromaStore
    from gr_autopilot.voice.embedder import SentenceTransformerEmbedder

    settings = Settings()
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(settings.db_path)
    init_db(conn)

    embedder = SentenceTransformerEmbedder()
    store = ChromaStore(settings.db_path.parent / "chroma")
    client = AnthropicChatClient()

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
