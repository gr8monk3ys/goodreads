CREATE TABLE IF NOT EXISTS books (
    book_id         INTEGER PRIMARY KEY,
    title           TEXT NOT NULL,
    author          TEXT,
    isbn            TEXT,
    isbn13          TEXT,
    my_rating       INTEGER DEFAULT 0,
    avg_rating      REAL,
    exclusive_shelf TEXT,
    date_read       TEXT,
    date_added      TEXT
);

CREATE TABLE IF NOT EXISTS reviews (
    book_id      INTEGER PRIMARY KEY REFERENCES books(book_id) ON DELETE CASCADE,
    review_html  TEXT,
    review_text  TEXT,
    has_spoiler  INTEGER DEFAULT 0,
    source       TEXT DEFAULT 'csv',
    generated_at TEXT,
    is_empty     INTEGER GENERATED ALWAYS AS
                 (CASE WHEN review_text IS NULL OR review_text = '' THEN 1 ELSE 0 END) STORED
);

CREATE TABLE IF NOT EXISTS shelves (
    shelf_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT UNIQUE NOT NULL,
    is_exclusive INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS book_shelves (
    book_id  INTEGER REFERENCES books(book_id) ON DELETE CASCADE,
    shelf_id INTEGER REFERENCES shelves(shelf_id) ON DELETE CASCADE,
    PRIMARY KEY (book_id, shelf_id)
);

CREATE TABLE IF NOT EXISTS runs (
    run_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at      TEXT,
    finished_at     TEXT,
    mode            TEXT,  -- 'dry_run' | 'live'
    actions_planned INTEGER DEFAULT 0,
    actions_done    INTEGER DEFAULT 0,
    actions_failed  INTEGER DEFAULT 0,
    notes           TEXT
);

CREATE TABLE IF NOT EXISTS actions_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id       INTEGER REFERENCES runs(run_id),
    book_id      INTEGER,
    action_type  TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    status       TEXT NOT NULL,  -- planned|dry_run|done|failed|skipped_idempotent
    dry_run      INTEGER DEFAULT 0,
    created_at   TEXT,
    detail       TEXT
);

CREATE INDEX IF NOT EXISTS idx_actions_idempotency
    ON actions_log (book_id, action_type, payload_hash, status);

CREATE TABLE IF NOT EXISTS book_genres (
    book_id INTEGER REFERENCES books(book_id) ON DELETE CASCADE,
    genre   TEXT NOT NULL,
    PRIMARY KEY (book_id, genre)
);
