"""Render a self-contained HTML 'target-state' dashboard the user can work through by hand.

Pure-ish: takes loaded BookFacts (+ optional proposed ratings and draft counts) and returns
one HTML string with inline CSS/JS — no external assets, no network, no account writes. It
shows current→target scores and a checkbox action board (ticks persist via localStorage) so
the user can do the moves on Goodreads themselves at their own pace.
"""

from __future__ import annotations

import html
from collections.abc import Mapping, Sequence

from gr_autopilot.curate import find_duplicates, hygiene
from gr_autopilot.insights.metrics import BookFact, compute
from gr_autopilot.presence import signature

READ = "read"
_EXISTENTIAL_AUTHORS = {
    "Fyodor Dostoevsky", "Hermann Hesse", "Franz Kafka", "Aldous Huxley",
    "Viktor E. Frankl", "George Orwell", "Theodore John Kaczynski",
}

_CSS = """
:root{--paper:#f6f1e7;--ink:#241f1b;--soft:#6b5d4f;--line:#ddd2bf;--accent:#7c2d2d;--good:#3f6f4f}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);
  font:16px/1.55 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}
.wrap{max-width:880px;margin:0 auto;padding:48px 24px 80px}
h1{font-family:Georgia,'Times New Roman',serif;font-size:40px;margin:0 0 6px;letter-spacing:-.5px}
h2{font-family:Georgia,serif;font-size:24px;margin:40px 0 14px;border-bottom:2px solid var(--line);padding-bottom:6px}
.sub{color:var(--soft);font-style:italic;margin:0 0 8px}
.scores{display:flex;flex-wrap:wrap;gap:14px;margin:26px 0}
.score{flex:1 1 150px;background:#fffdf8;border:1px solid var(--line);border-radius:10px;padding:16px 18px}
.score .n{font-family:Georgia,serif;font-size:30px}
.score .n .to{color:var(--accent)}
.score .lbl{color:var(--soft);font-size:13px;text-transform:uppercase;letter-spacing:.06em}
.card{background:#fffdf8;border:1px solid var(--line);border-radius:12px;padding:18px 22px;margin:14px 0}
.task{display:flex;gap:12px;align-items:flex-start;padding:7px 0;border-top:1px solid #efe7d6}
.task:first-child{border-top:0}
.task input{margin-top:5px;width:17px;height:17px;accent-color:var(--good);flex:none}
.task label{cursor:pointer}
.done label{text-decoration:line-through;color:var(--soft)}
.star{color:var(--accent);font-weight:700}
.bio{background:#f1ece0;border-left:3px solid var(--accent);padding:12px 16px;border-radius:6px;
  font-family:Georgia,serif;font-size:17px}
.pill{display:inline-block;background:#efe7d6;border-radius:20px;padding:2px 11px;margin:3px 4px 0 0;font-size:13px}
.muted{color:var(--soft);font-size:14px}
footer{margin-top:40px;color:var(--soft);font-size:13px;text-align:center}
a{color:var(--accent)}
"""

_JS = """
(function(){
  document.querySelectorAll('input[type=checkbox]').forEach(function(cb){
    var k='gr-'+cb.id;
    cb.checked = localStorage.getItem(k)==='1';
    cb.closest('.task').classList.toggle('done', cb.checked);
    cb.addEventListener('change', function(){
      localStorage.setItem(k, cb.checked?'1':'0');
      cb.closest('.task').classList.toggle('done', cb.checked);
    });
  });
})();
"""


def _e(s: object) -> str:
    return html.escape(str(s))


def _task(cid: str, text: str) -> str:
    return (
        f'<div class="task"><input type="checkbox" id="{cid}">'
        f'<label for="{cid}">{text}</label></div>'
    )


def _score(label: str, current: object, target: object) -> str:
    return (
        f'<div class="score"><div class="n">{_e(current)} '
        f'<span class="to">&rarr; {_e(target)}</span></div>'
        f'<div class="lbl">{_e(label)}</div></div>'
    )


def build_dashboard_html(
    facts: Sequence[BookFact],
    *,
    draft_counts: Mapping[str, int] | None = None,
    proposed_ratings: Mapping[int, int] | None = None,
    bio: str = "",
) -> str:
    m = compute(facts)
    sig = signature(facts)
    hyg = hygiene(facts)
    dups = find_duplicates(facts)
    drafts = dict(draft_counts or {})
    props = dict(proposed_ratings or {})
    read = [f for f in facts if f.exclusive_shelf == READ]
    unreviewed = [f for f in read if not f.has_review]
    members = sorted(
        (f for f in read if f.my_rating == 5 or f.author in _EXISTENTIAL_AUTHORS),
        key=lambda f: -f.my_rating,
    )
    n_read = m.reviews.n_read

    s: list[str] = ["<!doctype html><html lang='en'><head><meta charset='utf-8'>",
                    "<meta name='viewport' content='width=device-width,initial-scale=1'>",
                    "<title>Your Goodreads — target state</title>",
                    f"<style>{_CSS}</style></head><body><div class='wrap'>"]

    s.append("<h1>Your Goodreads, leveled up</h1>")
    canon = " · ".join(sig.five_star_titles) or "your standout reads"
    s.append(f"<p class='sub'>A reader of {canon}. Tick each off as you do it on Goodreads.</p>")

    s.append("<div class='scores'>")
    s.append(_score("Books rated", m.ratings.n_rated, n_read))
    s.append(_score("Reviews written", m.reviews.n_reviewed, n_read))
    s.append(_score("Read dates logged", n_read - m.pace.n_missing_date, n_read))
    s.append(_score("Featured shelf", 0, 1))
    s.append("</div>")

    # 1. Ratings
    s.append(f"<h2>1 · Rate {m.ratings.n_unrated} books</h2><div class='card'>")
    s.append("<p class='muted'>Suggested stars in parentheses — your call; change freely.</p>")
    for i, f in enumerate(hyg.unrated_reads):
        sug = props.get(f.book_id)
        tag = f' <span class="star">({"&#9733;"*sug})</span>' if sug else ""
        s.append(_task(f"rate{i}", f"{_e(f.title)} — {_e(f.author)}{tag}"))
    s.append("</div>")

    # 2. Reviews
    s.append(f"<h2>2 · Post {len(unreviewed)} reviews</h2><div class='card'>")
    ready = drafts.get("draft", 0) + drafts.get("approved", 0)
    s.append(f"<p class='muted'>{ready} editable drafts are waiting in "
             "<code>drafts/reviews/</code> — edit in your voice, then post.</p>")
    for i, f in enumerate(unreviewed):
        s.append(_task(f"rev{i}", f"{_e(f.title)} — {_e(f.author)}"))
    s.append("</div>")

    # 3. Shelf
    s.append("<h2>3 · Create the <code>existential-classics</code> shelf</h2><div class='card'>")
    s.append(_task("shelfmake", "Create a custom shelf named <b>existential-classics</b>, "
                                "then feature it on your profile"))
    for i, f in enumerate(members):
        s.append(_task(f"shelf{i}", f"Add: {_e(f.title)} — {_e(f.author)}"))
    s.append("</div>")

    # 4. Dates
    s.append(f"<h2>4 · Backfill {len(hyg.undated_reads)} read-dates</h2><div class='card'>")
    s.append("<p class='muted'>Even just the year fixes your stats & Reading Challenge.</p>")
    for i, f in enumerate(hyg.undated_reads):
        s.append(_task(f"date{i}", f"{_e(f.title)} — {_e(f.author)}"))
    s.append("</div>")

    # 5. Duplicates
    if dups:
        s.append(f"<h2>5 · Merge {len(dups)} duplicate(s)</h2><div class='card'>")
        for i, (title, group) in enumerate(dups):
            s.append(_task(f"dup{i}", f"Merge {len(group)} editions of <b>{_e(title)}</b>"))
        s.append("</div>")

    # 6. Bio + signature
    s.append("<h2>6 · Bio &amp; signature</h2><div class='card'>")
    if bio:
        s.append(f"<div class='bio'>{_e(bio)}</div>")
    s.append(_task("bio", "Paste an edited bio into Settings &rarr; Profile"))
    if sig.top_authors:
        s.append("<p style='margin-top:14px'>Signature authors: " +
                 "".join(f"<span class='pill'>{_e(a)}</span>" for a, _ in sig.top_authors[:6]) +
                 "</p>")
    if sig.top_eras:
        s.append("<p>Eras you live in: " +
                 "".join(f"<span class='pill'>{_e(b)}</span>" for b, _ in sig.top_eras[:5]) +
                 "</p>")
    s.append("</div>")

    # 7. Social
    s.append("<h2>7 · Follow &amp; engage <span class='muted'>(do by hand)</span></h2><div class='card'>")
    for i, t in enumerate([
        "Open your 5&#9733; books &rarr; Community Reviews; follow ~10 reviewers you like",
        "Follow your signature authors' Goodreads pages",
        "Each week: like + one thoughtful comment on a review of a book you've read",
    ]):
        s.append(_task(f"social{i}", t))
    s.append("</div>")

    s.append("<footer>Generated by gr-autopilot · read-only · nothing here was posted for you."
             "<br>Live automation for ratings: <code>gr apply</code>.</footer>")
    s.append(f"</div><script>{_JS}</script></body></html>")
    return "\n".join(s)
