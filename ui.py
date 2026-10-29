"""Pure presentational HTML for Streamlit (no user-controlled HTML injection)."""
from html import escape


def safe(value):
    return escape(str(value), quote=True)


def header(admin=False):
    suffix = '<span class="nav-pill">ADMIN CONTROL</span>' if admin else '<span class="nav-pill">LIVE PUZZLE EXPERIENCE</span>'
    return f'''<div class="party-header"><div class="party-brand"><span class="brand-mark">✦</span><span>PUZZLE<span class="brand-purple">PARTY</span></span></div>{suffix}</div>'''


def hero(eyebrow, title, subtitle, badge="", compact=False):
    flag = f'<span class="hero-chip">{safe(badge)}</span>' if badge else ''
    cls = 'hero hero--compact' if compact else 'hero'
    return f'''<section class="{cls}"><div class="hero-orb hero-orb--one"></div><div class="hero-orb hero-orb--two"></div><div class="hero-content"><p class="eyebrow">{safe(eyebrow)}</p><h1>{safe(title)}</h1><p class="hero-copy">{safe(subtitle)}</p>{flag}</div></section>'''


def section_title(label, hint="", icon="✦"):
    return f'''<div class="section-heading"><div><span class="section-icon">{safe(icon)}</span><span class="section-title">{safe(label)}</span></div><span class="section-subtitle">{safe(hint)}</span></div>'''


def mini_label(label, value, color="neutral"):
    return f'<div class="mini-stat mini-stat--{safe(color)}"><span>{safe(label)}</span><strong>{safe(value)}</strong></div>'


def timer_panel(remaining, state="running", label="HÁTRALÉVŐ IDŐ"):
    color = 'urgent' if remaining <= 30 and state == 'running' else 'regular'
    minutes, seconds = divmod(max(0, remaining), 60)
    shown = f'{minutes:02}:{seconds:02}'
    if state == 'lobby':
        shown = '– – : – –'
    elif state == 'finished':
        shown = '00:00'
    helper = ('Készenlétben · az admin indít' if state == 'lobby' else
              'Az idő lejárt' if state == 'finished' else
              'Utolsó pillanatok!' if color == 'urgent' else 'Mindenkinek ugyanannyi idő')
    return f'''<div class="timer-card timer-card--{color}"><div class="timer-head"><span>◷ &nbsp;{safe(label)}</span><span class="timer-dot"></span></div><div class="timer-number">{shown}</div><div class="timer-caption">{safe(helper)}</div></div>'''


def status_banner(status, text):
    icon = {'ok': '✓', 'warn': '!', 'info': '◉'}.get(status, '◉')
    return f'<div class="save-status save-status--{safe(status)}"><span class="save-icon">{icon}</span>{safe(text)}</div>'


def announcement(text, time_label=None):
    time_html = f'<span class="announcement-time">{safe(time_label)}</span>' if time_label else ''
    return f'''<div class="announcement"><div class="announcement-mark">✦</div><div><div class="announcement-heading">ÜZENET A JÁTÉKVEZETŐTŐL {time_html}</div><div class="announcement-text">{safe(text)}</div></div></div>'''


def stat_card(label, value, accent="violet", detail=""):
    note = f'<div class="stat-detail">{safe(detail)}</div>' if detail else ''
    return f'<div class="stat-card stat-card--{safe(accent)}"><span class="stat-label">{safe(label)}</span><strong class="stat-value">{safe(value)}</strong>{note}</div>'


def result_hero(name, correct, total, points):
    percent = round(correct / total * 100) if total else 0
    return f'''<div class="result-hero"><div class="result-spark">✦ ✧ ✦</div><div class="result-eyebrow">A FORDULÓ VÉGET ÉRT</div><h1>Szép játék, {safe(name)}!</h1><div class="result-score">{points}<span> PONT</span></div><div class="result-subline">{correct} / {total} helyes válasz · {percent}% találati arány</div></div>'''


def podium(rows, heading="A forduló dobogója"):
    if not rows:
        return '<div class="empty-state">A dobogóra még nem került játékos.</div>'
    # Visual order: second, first, third. Never insert unescaped names.
    chunks = []
    for place in (2, 1, 3):
        if len(rows) < place:
            chunks.append('<div class="podium-blank"></div>')
            continue
        r = rows[place - 1]
        medal = {1: '🥇', 2: '🥈', 3: '🥉'}[place]
        chunks.append(f'''<div class="podium-player podium-player--{place}"><div class="podium-medal">{medal}</div><div class="podium-person">{safe(r['nev'])}</div><div class="podium-score">{r['pont']} pont</div><div class="podium-step">{place}.</div></div>''')
    return f'<div class="podium-wrap"><h2>{safe(heading)}</h2><div class="podium-grid">{"".join(chunks)}</div></div>'
