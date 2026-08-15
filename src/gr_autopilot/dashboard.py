"""Render a self-contained HTML 'target-state' dashboard the user can work through by hand.

Pure-ish: takes loaded BookFacts (+ optional proposed ratings and draft counts) and returns
one HTML string with inline CSS/JS — no external assets it can't live without, no account
writes. It opens with a sequenced launch plan, shows current→target scorecards and a few
data visualizations, then a checkbox action board (ticks persist via localStorage).

Styling is ported from lscaturchio.xyz: Fraunces display serif + Instrument Sans body + IBM
Plex Mono "wall labels", forest-green-on-warm-paper, hairline borders (no shadows), and a
dark mode. No webfont fetch — self-contained means no network requests at all, so the font
stacks name the site fonts (used if installed locally) and fall back to system fonts.
"""

from __future__ import annotations

import html
from collections.abc import Mapping, Sequence

from gr_autopilot.curate import find_duplicates, hygiene
from gr_autopilot.insights.metrics import BookFact, compute
from gr_autopilot.launch import DEFAULT_CADENCE, LaunchPlan, build_launch_plan
from gr_autopilot.presence import signature

_CSS = """
:root{
  --bg:#f5f2ed;--fg:#1a202c;--card:#faf8f6;--primary:#2c5530;--secondary:#4d7350;
  --muted:#e8e4df;--muted-fg:#5a6577;--accent:#faf0e0;--border:#ddd5cc;
  --good:#3f6f4f;--warn:#b9750f;
  --serif:'Fraunces',Georgia,'Times New Roman',serif;
  --sans:'Instrument Sans',ui-sans-serif,system-ui,-apple-system,sans-serif;
  --mono:'IBM Plex Mono',ui-monospace,'SFMono-Regular',Menlo,monospace;
  --r-md:8px;--r-lg:10px;--r-xl:14px;--r-2xl:18px;
}
@media (prefers-color-scheme: dark){:root{
  --bg:#0f1419;--fg:#fafafa;--card:#131a24;--primary:#3dd44a;--secondary:#2d6031;
  --muted:#1f2937;--muted-fg:#b3bcc4;--accent:#1f2a3a;--border:#232f3f;
  --good:#3dd44a;--warn:#fbbf24;
}}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.6 var(--sans);
  -webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}
body::before{content:"";position:fixed;inset:0;pointer-events:none;z-index:9999;opacity:.035;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='160'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.8' numOctaves='2'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E")}
::selection{background:color-mix(in srgb,var(--primary) 22%,transparent);color:var(--fg)}
.wrap{max-width:900px;margin:0 auto;padding:64px 24px 96px}
.kick{font:500 .72rem/1.4 var(--mono);text-transform:uppercase;letter-spacing:.16em;
  color:var(--muted-fg);font-variant-numeric:tabular-nums}
h1{font-family:var(--serif);font-weight:700;font-size:clamp(2.3rem,6vw,3.4rem);
  line-height:1.04;letter-spacing:-.03em;margin:10px 0 8px}
h2{font-family:var(--serif);font-weight:600;font-size:clamp(1.45rem,3.4vw,1.9rem);
  letter-spacing:-.02em;margin:52px 0 16px;padding-bottom:8px;border-bottom:1px solid var(--border)}
.sub{color:var(--muted-fg);font-size:1.08rem;max-width:60ch;margin:0}
.scards{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px;margin:30px 0}
.scard{background:var(--card);border:1px solid var(--border);border-radius:var(--r-xl);padding:16px 18px}
.scard .snum{font-family:var(--serif);font-weight:600;font-size:1.8rem;margin:6px 0 12px;
  font-variant-numeric:tabular-nums}
.scard .arr{color:var(--primary)}
.meter{display:block;height:7px;background:var(--muted);border-radius:99px;overflow:hidden}
.meter>span{display:block;height:100%;background:var(--primary);border-radius:99px}
.card{background:var(--card);border:1px solid var(--border);border-radius:var(--r-2xl);
  padding:20px 24px;margin:14px 0}
.launch{border-left:4px solid var(--primary)}
.launch h2{border:0;margin:2px 0}
.lh{font-family:var(--serif);font-weight:600;font-size:1.18rem;letter-spacing:-.01em;margin:22px 0 2px}
.lblurb{color:var(--muted-fg);font-size:.95rem;margin:0 0 8px}
.task{display:flex;gap:12px;align-items:flex-start;padding:9px 0;border-top:1px solid var(--border)}
.task:first-child{border-top:0}
.task input{margin-top:5px;width:17px;height:17px;accent-color:var(--primary);flex:none}
.task label{cursor:pointer}
.done label{text-decoration:line-through;color:var(--muted-fg)}
.star{color:var(--primary);font-weight:600}
.vizgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px}
.viz{background:var(--card);border:1px solid var(--border);border-radius:var(--r-2xl);padding:18px 20px}
.viz .kick{margin-bottom:12px}
.bars{display:flex;flex-direction:column;gap:9px}
.barrow{display:grid;grid-template-columns:64px 1fr 34px;align-items:center;gap:10px}
.barrow .bl{font:500 .8rem var(--mono);color:var(--muted-fg);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.barrow .bv{font:500 .8rem var(--mono);color:var(--fg);text-align:right;font-variant-numeric:tabular-nums}
.bio{background:var(--accent);border-left:3px solid var(--primary);padding:14px 18px;
  border-radius:var(--r-md);font-family:var(--serif);font-size:1.05rem;line-height:1.55}
.pill{display:inline-block;background:var(--muted);border-radius:99px;padding:3px 12px;
  margin:4px 5px 0 0;font:500 .8rem var(--mono);color:var(--muted-fg)}
.muted{color:var(--muted-fg);font-size:.95rem}
code{font:.88em var(--mono);background:var(--muted);padding:1px 6px;border-radius:5px}
footer{margin-top:56px;color:var(--muted-fg);font-size:.85rem;text-align:center;line-height:1.7}
a{color:var(--primary);text-underline-offset:3px}
"""

_JS = """
(function(){
  var boxes=document.querySelectorAll('input[type=checkbox]');
  var tally=document.getElementById('tally');
  function refresh(){
    var done=0; boxes.forEach(function(b){if(b.checked)done++;});
    if(tally) tally.textContent=done+' of '+boxes.length+' done';
  }
  boxes.forEach(function(cb){
    var k='gr-'+cb.id;
    cb.checked = localStorage.getItem(k)==='1';
    cb.closest('.task').classList.toggle('done', cb.checked);
    cb.addEventListener('change', function(){
      localStorage.setItem(k, cb.checked?'1':'0');
      cb.closest('.task').classList.toggle('done', cb.checked);
      refresh();
    });
  });
  refresh();
})();
"""


def _e(s: object) -> str:
    return html.escape(str(s))


def _task(cid: str, text: str) -> str:
    return (
        f'<div class="task"><input type="checkbox" id="{cid}">'
        f'<label for="{cid}">{text}</label></div>'
    )


def _scard(label: str, current: int, target: int) -> str:
    pct = min(100, round(current / target * 100)) if target else 0
    return (
        f'<div class="scard"><div class="kick">{_e(label)}</div>'
        f'<div class="snum">{current} <span class="arr">&rarr;</span> {target}</div>'
        f'<span class="meter"><span style="width:{pct}%"></span></span></div>'
    )


def _bars(rows: Sequence[tuple[str, int]]) -> str:
    if not rows:
        return '<p class="muted">No data yet.</p>'
    top = max((c for _, c in rows), default=0) or 1
    out = ['<div class="bars">']
    for label, count in rows:
        pct = round(count / top * 100)
        out.append(
            f'<div class="barrow"><span class="bl">{_e(label)}</span>'
            f'<span class="meter"><span style="width:{pct}%"></span></span>'
            f'<span class="bv">{count}</span></div>'
        )
    out.append("</div>")
    return "\n".join(out)


def _viz(title: str, rows: Sequence[tuple[str, int]]) -> str:
    return f'<div class="viz"><div class="kick">{_e(title)}</div>{_bars(rows)}</div>'


def _launch_card(plan: LaunchPlan) -> str:
    """The leading 'Start here' card — the sequenced campaign, not the flat board."""
    out = [
        '<div class="card launch"><h2>Start here — your launch sequence</h2>',
        f'<p class="muted">{plan.n_review_targets} reviews to write · '
        f"~{plan.reviews_per_week}/week · through the backlog in ~{plan.weeks_to_finish} "
        "weeks. Spread it out instead of doing it all at once — steadier tends to stick.</p>",
    ]
    for p in plan.phases:
        if p.key == "cadence":
            continue  # section 2 below renders plan.review_targets — the same list, same order
        out.append(f'<h3 class="lh">{_e(p.title)}</h3>')
        out.append(f'<p class="lblurb">{_e(p.blurb)}</p>')
        for step in p.steps:
            detail = f' <span class="muted">— {_e(step.detail)}</span>' if step.detail else ""
            out.append(_task(f"L-{p.key}-{step.key}", f"{_e(step.text)}{detail}"))
    out.append("</div>")
    return "\n".join(out)


def build_dashboard_html(
    facts: Sequence[BookFact],
    *,
    draft_counts: Mapping[str, int] | None = None,
    proposed_ratings: Mapping[int, int] | None = None,
    drafted_ids: set[int] | None = None,
    bio: str = "",
    reviews_per_week: int = DEFAULT_CADENCE,
) -> str:
    m = compute(facts)
    sig = signature(facts)
    hyg = hygiene(facts)
    dups = find_duplicates(facts)
    plan = build_launch_plan(
        facts, drafted_ids=drafted_ids or set(), bio=bio, reviews_per_week=reviews_per_week
    )
    drafts = dict(draft_counts or {})
    props = dict(proposed_ratings or {})
    unreviewed = plan.review_targets
    members = plan.shelf_members
    n_read = m.reviews.n_read

    s: list[str] = [
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width,initial-scale=1'>",
        "<title>Your Goodreads — target state</title>",
        f"<style>{_CSS}</style></head><body><div class='wrap'>",
    ]

    canon = " · ".join(_e(t) for t in sig.five_star_titles) or "your standout reads"
    s.append("<div class='kick'>Goodreads · target state · <span id='tally'></span></div>")
    s.append("<h1>Your reading, leveled up</h1>")
    s.append(
        f"<p class='sub'>A reader of {canon}. Everything below is yours to do by hand on "
        "Goodreads — tick each off as you go; your progress is saved in this browser.</p>"
    )

    # Scorecards: current -> target with a fill meter.
    s.append("<div class='scards'>")
    s.append(_scard("Books rated", m.ratings.n_rated, n_read))
    s.append(_scard("Reviews written", m.reviews.n_reviewed, n_read))
    s.append(_scard("Read dates logged", n_read - m.pace.n_missing_date, n_read))
    s.append(_scard("Featured shelf", 0, 1))
    s.append("</div>")

    # The sequenced campaign.
    s.append(_launch_card(plan))

    # Visualizations of the library as it stands.
    hist_rows = [(f"{star}★", m.ratings.histogram[star]) for star in (5, 4, 3, 2, 1)]
    pace_rows = [(str(y), c) for y, c in m.pace.reads_by_year]
    era_rows = list(m.eras.by_band)
    genre_rows = m.genres.top[:6]
    s.append("<h2>Your reading in numbers</h2><div class='vizgrid'>")
    s.append(_viz("Ratings you gave", hist_rows))
    if pace_rows:
        s.append(_viz("Books read by year", pace_rows))
    if era_rows:
        s.append(_viz("Eras you read", era_rows))
    if genre_rows:
        s.append(_viz("Top genres", genre_rows))
    s.append("</div>")

    # 1. Ratings
    s.append(f"<h2>1 · Rate {m.ratings.n_unrated} books</h2><div class='card'>")
    s.append("<p class='muted'>Suggested stars in parentheses — your call; change freely.</p>")
    for f in hyg.unrated_reads:
        sug = props.get(f.book_id)
        tag = f' <span class="star">({"&#9733;" * sug})</span>' if sug else ""
        s.append(_task(f"rate{f.book_id}", f"{_e(f.title)} — {_e(f.author)}{tag}"))
    s.append("</div>")

    # 2. Reviews
    s.append(f"<h2>2 · Post {len(unreviewed)} reviews</h2><div class='card'>")
    ready = drafts.get("draft", 0) + drafts.get("approved", 0)
    s.append(
        f"<p class='muted'>{ready} editable drafts are waiting in "
        "<code>drafts/reviews/</code> — edit in your voice, then post.</p>"
    )
    for f in unreviewed:
        s.append(_task(f"rev{f.book_id}", f"{_e(f.title)} — {_e(f.author)}"))
    s.append("</div>")

    # 3. Shelf
    s.append("<h2>3 · Create the <code>existential-classics</code> shelf</h2><div class='card'>")
    s.append(
        _task(
            "shelfmake",
            "Create a custom shelf named <b>existential-classics</b>, "
            "then feature it on your profile",
        )
    )
    for f in members:
        s.append(_task(f"shelf{f.book_id}", f"Add: {_e(f.title)} — {_e(f.author)}"))
    s.append("</div>")

    # 4. Dates
    s.append(f"<h2>4 · Backfill {len(hyg.undated_reads)} read-dates</h2><div class='card'>")
    s.append("<p class='muted'>Even just the year fixes your stats & Reading Challenge.</p>")
    for f in hyg.undated_reads:
        s.append(_task(f"date{f.book_id}", f"{_e(f.title)} — {_e(f.author)}"))
    s.append("</div>")

    # 5. Duplicates
    if dups:
        s.append(f"<h2>5 · Merge {len(dups)} duplicate(s)</h2><div class='card'>")
        for title, group in dups:
            s.append(
                _task(
                    f"dup{group[0].book_id}", f"Merge {len(group)} editions of <b>{_e(title)}</b>"
                )
            )
        s.append("</div>")

    # 6. Bio + signature
    s.append("<h2>6 · Bio &amp; signature</h2><div class='card'>")
    if bio:
        s.append(f"<div class='bio'>{_e(bio)}</div>")
    s.append(
        _task(
            "bio",
            "Paste an edited bio into Settings &rarr; Profile "
            "<span class='muted'>— make the words yours</span>",
        )
    )
    if sig.top_authors:
        s.append(
            "<p style='margin-top:14px'>Signature authors: "
            + "".join(f"<span class='pill'>{_e(a)}</span>" for a, _ in sig.top_authors[:6])
            + "</p>"
        )
    if sig.top_eras:
        s.append(
            "<p>Eras you live in: "
            + "".join(f"<span class='pill'>{_e(b)}</span>" for b, _ in sig.top_eras[:5])
            + "</p>"
        )
    s.append("</div>")

    # 7. Social
    s.append(
        "<h2>7 · Follow &amp; engage <span class='muted'>(do by hand)</span></h2><div class='card'>"
    )
    for i, t in enumerate(
        [
            "Open your 5&#9733; books &rarr; Community Reviews; follow ~10 reviewers you like",
            "Follow your signature authors' Goodreads pages",
            "Each week: like + one thoughtful comment on a review of a book you've read",
        ]
    ):
        s.append(_task(f"social{i}", t))
    s.append("</div>")

    s.append(
        "<footer>Generated by gr-autopilot · read-only · nothing here was posted for you."
        "<br>Sequenced campaign: <code>gr launch</code> · live ratings: <code>gr apply</code>."
        "</footer>"
    )
    s.append(f"</div><script>{_JS}</script></body></html>")
    return "\n".join(s)
