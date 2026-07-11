from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. All keys are overridable via GR_* env vars."""

    model_config = SettingsConfigDict(env_prefix="GR_", env_file=".env", extra="ignore")

    db_path: Path = Path("data/autopilot.db")
    drafts_dir: Path = Path("drafts/reviews")  # editable review drafts (never auto-posted)
    # Deliberately OUTSIDE the repo: data/ and drafts/ are git-ignored personal
    # content, so a worktree cleanup or reclone destroys them. Backups must not
    # live in the same blast radius.
    backup_dir: Path = Path.home() / "Backups" / "goodreads-autopilot"
    require_rating: bool = True  # rated-reads-only target rule (sign-off)
    disable_writes: bool = False  # kill switch (used by actions layer)
    max_actions_per_run: int = 10
    model: str = "claude-sonnet-4-6"
