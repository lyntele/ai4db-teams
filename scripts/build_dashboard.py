#!/usr/bin/env python3
"""Generate a polished, bilingual (EN/ZH) dashboard from researchers.json."""

import argparse
import json as _json
import os

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from utils import load_researchers, load_institutions

OUT_DIR   = os.path.join(os.path.dirname(__file__), '..')
HTML_PATH = os.path.join(OUT_DIR, 'dashboard.html')
INDEX_PATH = os.path.join(OUT_DIR, 'index.html')
CSV_PATH  = os.path.join(OUT_DIR, 'data', 'researchers.csv')
LITERATURE_REPORT_PATH = os.path.join(OUT_DIR, 'data', 'literature_reports', 'db_llm', 'latest.json')

# ── Palette ───────────────────────────────────────────────────
REGION_COLORS  = {
    'Asia': '#0f766e',
    'Europe': '#2563eb',
    'North America': '#c2410c',
    'Oceania': '#7c3aed',
    'South America': '#dc2626',
    'Africa': '#0891b2',
}
TYPE_COLORS    = {'faculty':'#0f766e','industry':'#c2410c'}
CHANCE_COLORS  = {'high':'#15803d','medium':'#b45309','low':'#b91c1c','internship-only':'#6d28d9'}
PRIORITY_COLORS= {'high':'#dc2626','medium':'#d97706','low':'#64748b'}

HOVER_LABEL = dict(
    bgcolor='#0f172a', bordercolor='#334155',
    font=dict(family='Plus Jakarta Sans, sans-serif', size=12, color='#f1f5f9'),
)
BASE_LAYOUT = dict(
    font=dict(family='Plus Jakarta Sans, sans-serif', size=13, color='#334155'),
    paper_bgcolor='white', plot_bgcolor='white',
    hoverlabel=HOVER_LABEL,
    margin=dict(l=16, r=16, t=40, b=16),
)

JUNIOR_ROLE_HINTS = (
    'student', 'phd', 'ph.d', 'doctoral', 'master', 'msc',
    'undergrad', 'undergraduate', 'research assistant', 'intern',
)


# ── Data helpers ──────────────────────────────────────────────

def has_text(value):
    return bool(str(value or '').strip())


def classify_profile_segment(entry):
    if entry.get('type') == 'industry':
        return 'main'

    position = str(entry.get('position') or '').strip().lower()
    if any(hint in position for hint in JUNIOR_ROLE_HINTS):
        return 'student'
    if position:
        return 'main'
    if has_text(entry.get('homepage')):
        return 'student'
    return 'paper-author'


def build_df(data, institutions):
    rows = []
    for r in data['researchers']:
        inst_key = r.get('institution', '')
        inst = institutions.get(inst_key, {})
        row = dict(r)
        row['inst_display'] = inst.get('display_name') or r.get('institution_display_name') or inst_key
        row['country'] = inst.get('country') or r.get('country') or ''
        row['region'] = inst.get('region') or r.get('region') or ''
        row['lat'] = inst.get('lat') if inst else r.get('institution_lat')
        row['lon'] = inst.get('lon') if inst else r.get('institution_lon')
        row['qs_rank'] = inst.get('qs_rank') if inst else r.get('institution_qs_rank')
        row['inst_type'] = inst.get('type', '')
        row['tags_str'] = ', '.join(r.get('tags', []))
        row['focus_str'] = ', '.join(r.get('research_focus', []))
        row['profile_segment'] = classify_profile_segment(r)
        row['has_homepage'] = has_text(r.get('homepage') or r.get('research_group_url'))
        row.pop('institution_display_name', None)
        row.pop('institution_qs_rank', None)
        row.pop('institution_lat', None)
        row.pop('institution_lon', None)
        rows.append(row)
    return pd.DataFrame(rows)


def load_literature_report():
    if not os.path.exists(LITERATURE_REPORT_PATH):
        return {}
    with open(LITERATURE_REPORT_PATH, 'r', encoding='utf-8') as handle:
        return _json.load(handle)


def curated_df(df):
    return df[df['profile_segment'] == 'main'].copy()


def student_df(df):
    return df[(df['profile_segment'] == 'student') & (df['has_homepage'])].copy()


def build_researcher_map_data(df):
    """Dict keyed by institution raw key → drawer card data."""
    result = {}
    for _, r in df.iterrows():
        key = r.get('institution', '')
        if not key:
            continue
        research_focus = r.get('research_focus') if isinstance(r.get('research_focus'), list) else []
        tags = r.get('tags') if isinstance(r.get('tags'), list) else []
        members = r.get('members') if isinstance(r.get('members'), list) else []
        result.setdefault(
            key,
            {
                'display_name': r.get('inst_display', key),
                'country': r.get('country', '') or '',
                'region': r.get('region', '') or '',
                'qs_rank': r.get('qs_rank'),
                'researchers': [],
            },
        )
        result[key]['researchers'].append({
            'name':     r.get('name', ''),
            'position': r.get('position', ''),
            'type':     r.get('type', ''),
            'homepage': r.get('homepage', '') or r.get('research_group_url', '') or '',
            'research_focus': research_focus,
            'tags':           tags,
            'admission_chance': r.get('admission_chance', '') or '',
            'priority':       r.get('priority', '') or '',
            'taking_students': bool(r.get('currently_taking_students', False)),
            'notes': r.get('notes', '') or '',
            'members': [
                {
                    'name': m.get('name', ''),
                    'position': m.get('position', ''),
                    'homepage': m.get('homepage', '') or '',
                    'notes': m.get('notes', '') or '',
                }
                for m in members
            ],
        })
    return result


# ── Charts ────────────────────────────────────────────────────

def chart_map(df):
    agg = df.groupby(['institution', 'inst_display', 'lat', 'lon', 'type']).agg(
        count=('id', 'size'),
        names=('name', lambda x: '<br>'.join(x)),
    ).reset_index()

    fig = px.scatter_geo(
        agg, lat='lat', lon='lon', size='count', color='type',
        color_discrete_map=TYPE_COLORS,
        hover_name='inst_display',
        hover_data={'names': True, 'count': True, 'lat': False, 'lon': False, 'type': False},
        custom_data=['institution'],
        projection='natural earth',
        size_max=32,
    )
    fig.update_traces(
        marker=dict(opacity=0.92, line=dict(width=1.5, color='rgba(255,255,255,0.5)')),
        hovertemplate=(
            '<b>%{hovertext}</b><br>'
            'Researchers: %{marker.size}<br>'
            '<span style="color:#94a3b8;font-size:11px">● Click to view profiles</span>'
            '<extra></extra>'
        ),
    )
    fig.update_geos(
        showcountries=True,  countrycolor='#334155',
        showcoastlines=True, coastlinecolor='#475569',
        showland=True,       landcolor='#1e293b',
        showocean=True,      oceancolor='#0f172a',
        showlakes=True,      lakecolor='#1e293b',
        showframe=False,     bgcolor='#0f172a',
    )
    fig.update_layout(
        height=560,
        paper_bgcolor='#0f172a', plot_bgcolor='#0f172a',
        font=dict(family='Plus Jakarta Sans, sans-serif', size=13, color='#94a3b8'),
        margin=dict(l=0, r=0, t=8, b=0),
        hoverlabel=HOVER_LABEL,
        legend=dict(bgcolor='rgba(15,23,42,0.85)', bordercolor='#334155',
                    borderwidth=1, font=dict(color='#cbd5e1')),
    )
    return fig


def chart_institution(df):
    # Keep qs_rank per institution (first non-null)
    agg = df.groupby(['inst_display', 'region']).agg(
        count=('id', 'size'),
        qs_rank=('qs_rank', lambda x: x.dropna().iloc[0] if x.notna().any() else None),
    ).reset_index().sort_values('count', ascending=True)

    fig = px.bar(
        agg, x='count', y='inst_display', color='region',
        color_discrete_map=REGION_COLORS, orientation='h',
        labels={'inst_display': '', 'count': 'Researchers'},
    )
    fig.update_traces(
        marker_line_width=0, opacity=0.9,
        hovertemplate='<b>%{y}</b><br>Researchers: %{x}<extra></extra>',
    )
    # QS rank annotations
    for _, row in agg.iterrows():
        if pd.notna(row.get('qs_rank')) and row['qs_rank']:
            fig.add_annotation(
                x=row['count'] + 0.12, y=row['inst_display'],
                text=f"QS #{int(row['qs_rank'])}",
                showarrow=False, xanchor='left',
                font=dict(size=10, color='#94a3b8'),
            )
    fig.update_layout(
        height=max(420, len(agg) * 26 + 60),
        margin=dict(l=180, r=90, t=24, b=16),
        bargap=0.32,
        xaxis=dict(gridcolor='#f1f5f9', linecolor='#e2e8f0', zeroline=False),
        yaxis=dict(tickfont=dict(size=11)),
        legend=dict(bgcolor='rgba(255,255,255,0.9)', bordercolor='#e2e8f0', borderwidth=1, title_text=''),
        **{k: v for k, v in BASE_LAYOUT.items() if k not in ('margin',)},
    )
    return fig


def chart_tags(df):
    records = []
    for _, row in df.iterrows():
        for tag in (row.get('tags') or []):
            records.append({'tag': tag})
    if not records:
        return go.Figure()
    tdf = pd.DataFrame(records)
    tag_totals = tdf.groupby('tag').size().reset_index(name='total')
    tag_totals = tag_totals.sort_values('total', ascending=True)

    fig = go.Figure()
    # Stem lines
    for _, r in tag_totals.iterrows():
        fig.add_shape(
            type='line', x0=0, x1=r['total'], y0=r['tag'], y1=r['tag'],
            line=dict(color='#e2e8f0', width=1.5), layer='below',
        )
    # Dots
    fig.add_trace(go.Scatter(
        x=tag_totals['total'], y=tag_totals['tag'],
        mode='markers+text',
        text=tag_totals['total'].astype(str),
        textposition='middle right',
        textfont=dict(size=11, color='#64748b'),
        marker=dict(
            size=18,
            color=tag_totals['total'],
            colorscale=[[0, '#99f6e4'], [0.5, '#0f766e'], [1, '#134e4a']],
            showscale=False,
            line=dict(width=2, color='white'),
        ),
        hovertemplate='<b>%{y}</b>: %{x} researchers<extra></extra>',
        showlegend=False,
    ))
    fig.update_layout(
        height=max(380, len(tag_totals) * 36 + 60),
        xaxis=dict(title='', gridcolor='#f1f5f9', linecolor='#e2e8f0', zeroline=False),
        yaxis=dict(gridcolor='#f1f5f9', tickfont=dict(size=12)),
        margin=dict(l=120, r=70, t=24, b=16),
        **{k: v for k, v in BASE_LAYOUT.items() if k not in ('margin',)},
    )
    return fig


def chart_kanban(df):
    ORDER = ['considering', 'shortlisted', 'contacted', 'awaiting-reply',
             'applied', 'accepted', 'rejected', 'not-applicable']
    LABELS = {
        'considering': 'Considering', 'shortlisted': 'Shortlisted',
        'contacted': 'Contacted', 'awaiting-reply': 'Awaiting Reply',
        'applied': 'Applied', 'accepted': 'Accepted',
        'rejected': 'Rejected', 'not-applicable': 'N/A',
    }
    COLORS = {
        'considering': '#0f766e', 'shortlisted': '#0f766e',
        'contacted': '#2563eb', 'awaiting-reply': '#d97706',
        'applied': '#1d4ed8', 'accepted': '#15803d',
        'rejected': '#dc2626', 'not-applicable': '#64748b',
    }
    counts = df.groupby('application_status').size().reindex(ORDER, fill_value=0)
    fig = go.Figure(go.Funnel(
        y=[LABELS[s] for s in ORDER],
        x=[int(counts[s]) for s in ORDER],
        textinfo='value+percent initial',
        marker=dict(
            color=[COLORS[s] for s in ORDER],
            line=dict(width=1, color='rgba(255,255,255,0.2)'),
        ),
        connector=dict(
            line=dict(color='rgba(255,255,255,0.08)', width=1),
            fillcolor='rgba(15,118,110,0.05)',
        ),
        hovertemplate='<b>%{y}</b><br>Count: %{x}<br>%{percentInitial} of pipeline<extra></extra>',
        textfont=dict(family='Plus Jakarta Sans, sans-serif', size=12, color='white'),
        opacity=0.93,
    ))
    fig.update_layout(
        height=460,
        margin=dict(l=16, r=16, t=24, b=16),
        **{k: v for k, v in BASE_LAYOUT.items() if k not in ('margin',)},
    )
    return fig


def chart_region_donut(df):
    ORDER = ['Asia', 'North America', 'Europe', 'Oceania', 'South America', 'Africa']
    agg = df.groupby('region').size().reset_index(name='count')
    agg['region'] = pd.Categorical(agg['region'], categories=ORDER, ordered=True)
    agg = agg.sort_values('region').dropna(subset=['region'])
    total = int(agg['count'].sum())

    fig = go.Figure(go.Pie(
        labels=agg['region'], values=agg['count'], hole=0.62,
        marker=dict(
            colors=[REGION_COLORS.get(r, '#94a3b8') for r in agg['region']],
            line=dict(color='white', width=3),
        ),
        textinfo='percent', textfont=dict(size=12, family='Plus Jakarta Sans'),
        hovertemplate='<b>%{label}</b><br>%{value} researchers (%{percent})<extra></extra>',
        direction='clockwise', sort=False,
        pull=[0.05] + [0] * (len(agg) - 1),
    ))
    fig.add_annotation(text=f'<b>{total}</b>', x=0.5, y=0.57, showarrow=False,
                       font=dict(size=30, color='#0f172a', family='Outfit'),
                       xref='paper', yref='paper')
    fig.add_annotation(text='researchers', x=0.5, y=0.43, showarrow=False,
                       font=dict(size=11, color='#64748b', family='Plus Jakarta Sans'),
                       xref='paper', yref='paper')
    fig.update_layout(
        height=340, showlegend=True,
        legend=dict(orientation='v', x=1.02, y=0.5,
                    font=dict(size=12), bgcolor='rgba(0,0,0,0)'),
        margin=dict(l=16, r=100, t=24, b=16),
        **{k: v for k, v in BASE_LAYOUT.items() if k not in ('margin',)},
    )
    return fig


def chart_type_donut(df):
    agg = df.groupby('type').size().reset_index(name='count')
    total = int(agg['count'].sum())

    fig = go.Figure(go.Pie(
        labels=agg['type'], values=agg['count'], hole=0.62,
        marker=dict(
            colors=[TYPE_COLORS.get(t, '#94a3b8') for t in agg['type']],
            line=dict(color='white', width=3),
        ),
        textinfo='percent', textfont=dict(size=12, family='Plus Jakarta Sans'),
        hovertemplate='<b>%{label}</b><br>%{value} (%{percent})<extra></extra>',
        pull=[0.05, 0],
    ))
    fig.add_annotation(text=f'<b>{total}</b>', x=0.5, y=0.57, showarrow=False,
                       font=dict(size=30, color='#0f172a', family='Outfit'),
                       xref='paper', yref='paper')
    fig.add_annotation(text='total', x=0.5, y=0.43, showarrow=False,
                       font=dict(size=11, color='#64748b', family='Plus Jakarta Sans'),
                       xref='paper', yref='paper')
    fig.update_layout(
        height=340, showlegend=True,
        legend=dict(orientation='v', x=1.02, y=0.5,
                    font=dict(size=12), bgcolor='rgba(0,0,0,0)'),
        margin=dict(l=16, r=100, t=24, b=16),
        **{k: v for k, v in BASE_LAYOUT.items() if k not in ('margin',)},
    )
    return fig


# ── HTML helpers ──────────────────────────────────────────────

def to_div(fig, div_id):
    return fig.to_html(
        full_html=False,
        include_plotlyjs=False,
        config={'responsive': True, 'displayModeBar': False},
        div_id=div_id,
    )


def stats_cards(df):
    cards = [
        (len(df),                        'total-label',    'total-note',    '#0f766e'),
        ((df['type']=='faculty').sum(),  'faculty-label',  'faculty-note',  '#2563eb'),
        ((df['type']=='industry').sum(), 'industry-label', 'industry-note', '#c2410c'),
        ((df['priority']=='high').sum(), 'priority-label', 'priority-note', '#dc2626'),
    ]
    html = '<div class="stats-row">'
    for val, i18n, note_key, color in cards:
        html += f'''
      <div class="stat-card">
        <div class="stat-card-top">
          <div class="stat-label" data-i18n="{i18n}"></div>
          <span class="stat-accent" style="background:{color}"></span>
        </div>
        <div class="stat-value" style="color:{color}">{val}</div>
        <div class="stat-microcopy" data-i18n="{note_key}"></div>
      </div>'''
    return html + '</div>'


def build_table(df):
    cols = [
        ('name-col', 'name'), ('type-col', 'type'), ('inst-col', 'inst_display'),
        ('country-col', 'country'), ('region-col', 'region'), ('pos-col', 'position'),
        ('focus-col', 'focus_str'), ('tags-col', 'tags_str'),
        ('chance-col', 'admission_chance'), ('status-col', 'application_status'),
        ('pri-col', 'priority'), ('link-col', 'homepage'),
    ]
    rows = []
    for _, r in df.iterrows():
        cells = []
        for i18n_key, col in cols:
            val = r.get(col) or ''
            if col == 'homepage' and val:
                cell = f'<a href="{val}" target="_blank" rel="noopener" class="table-link">↗ <span data-i18n="link-text">Link</span></a>'
            elif col == 'admission_chance' and val:
                cell = f'<span class="badge badge-{val}">{val}</span>'
            elif col == 'type' and val:
                cell = f'<span class="badge badge-type-{val}">{val}</span>'
            elif col == 'priority' and val:
                cell = f'<span class="priority-dot priority-{val}"></span>{val}'
            else:
                cell = str(val)
            cells.append(f'<td data-col="{col}">{cell}</td>')
        rows.append('<tr>' + ''.join(cells) + '</tr>')

    headers = ''.join(
        f'<th data-col="{col}" data-i18n="{key}" onclick="sortTable(this)"></th>'
        for key, col in cols
    )
    return f'<table id="researcherTable"><thead><tr>{headers}</tr></thead><tbody>{"".join(rows)}</tbody></table>'


def build_filters(df):
    regions    = sorted(df['region'].dropna().unique())
    types      = sorted(df['type'].dropna().unique())
    priorities = sorted(df['priority'].dropna().unique())
    all_tags   = sorted({t for tags in df['tags'] if isinstance(tags, list) for t in tags})

    def sel(fid, i18n_prefix, vals):
        opts = f'<option value="" data-i18n="{i18n_prefix}-all"></option>'
        for v in vals:
            opts += f'<option value="{v}">{v}</option>'
        return f'<select id="{fid}" onchange="filterTable()">{opts}</select>'

    return f'''<div class="filter-bar">
      {sel("fRegion",   "filter-region",   regions)}
      {sel("fType",     "filter-type",     types)}
      {sel("fPriority", "filter-priority", priorities)}
      {sel("fTag",      "filter-tag",      all_tags)}
      <input id="fSearch" type="text" class="filter-input"
             data-i18n-placeholder="filter-search" oninput="filterTable()">
    </div>'''


def build_student_cards(df):
    if df.empty:
        return '<div class="empty-state" data-i18n="student-empty"></div>'

    cards = []
    ordered = df.sort_values(['inst_display', 'name'], ascending=[True, True])
    for _, r in ordered.iterrows():
        homepage = r.get('homepage') or r.get('research_group_url') or ''
        notes = r.get('notes') or ''
        cards.append(f'''
      <div class="student-card">
        <div class="student-card-top">
          <div>
            <div class="student-name">{r.get('name') or ''}</div>
            <div class="student-meta">{r.get('inst_display') or ''}</div>
          </div>
          <span class="badge badge-type-{r.get('type') or 'faculty'}">{r.get('type') or ''}</span>
        </div>
        <div class="student-submeta">{r.get('position') or ''}</div>
        {f'<a href="{homepage}" target="_blank" rel="noopener" class="table-link">↗ <span data-i18n="link-text">Link</span></a>' if homepage else ''}
        {f'<div class="student-note">{notes}</div>' if notes else ''}
      </div>''')

    return f'<div class="student-grid">{"".join(cards)}</div>'


def build_literature_cards(report):
    summary = report.get('summary') or {}
    papers = report.get('papers') or []
    new_researchers = report.get('new_researchers') or []
    run_date = report.get('run_date') or ''

    summary_cards = [
        ('literature-fetched', summary.get('openalex_works_fetched', 0)),
        ('literature-matched', summary.get('watchlist_matches', 0)),
        ('literature-added', summary.get('new_researchers_added', 0)),
        ('literature-updated', summary.get('existing_researchers_updated', 0)),
    ]
    summary_html = ''.join(
        f'''
      <div class="literature-stat">
        <span>{value}</span>
        <small data-i18n="{label_key}"></small>
      </div>'''
        for label_key, value in summary_cards
    )

    if not report:
        return '''
      <div class="empty-state" data-i18n="literature-empty"></div>
      <div class="literature-summary-grid"></div>'''

    cards = []
    for paper in papers[:18]:
        tags = paper.get('tags') or []
        authors = paper.get('authors') or []
        author_preview = authors[:8]
        author_chunks = []
        for author in author_preview:
            label = author.get('name') or ''
            affiliation = author.get('affiliation') or ''
            if affiliation:
                label = f'{label} ({affiliation})'
            author_chunks.append(label)
        author_text = '; '.join(author_chunks)
        remaining = max(len(authors) - len(author_preview), 0)
        tags_html = ''
        if tags:
            tags_html = '<div class="chip-row">' + ''.join(
                f'<span class="tag-chip">{tag}</span>' for tag in tags
            ) + '</div>'
        authors_html = f'<div class="literature-authors">{author_text}</div>' if author_text else ''
        more_html = f'<div class="literature-more">+{remaining} <span data-i18n="literature-more-authors"></span></div>' if remaining else ''
        link_html = f'<a href="{paper.get("url")}" target="_blank" rel="noopener" class="r-link">Paper</a>' if paper.get('url') else ''
        cards.append(f'''
      <article class="literature-card">
        <div class="literature-card-top">
          <div>
            <div class="literature-title">{paper.get('title') or ''}</div>
            <div class="literature-meta">{paper.get('publication_date') or ''} · {paper.get('venue') or ''}</div>
          </div>
          <span class="badge badge-type-faculty">score {paper.get('relevance_score') or 0}</span>
        </div>
        {tags_html}
        {authors_html}
        {more_html}
        <div class="r-links">
          {link_html}
        </div>
      </article>''')

    new_researchers_html = ''
    if new_researchers:
        items = ''.join(
            f'<li>{item.get("name") or ""} ({item.get("institution") or ""})</li>'
            for item in new_researchers[:10]
        )
        new_researchers_html = f'''
      <div class="literature-added-block">
        <div class="card-title" data-i18n="literature-added-title"></div>
        <ul class="literature-added-list">{items}</ul>
      </div>'''

    cards_html = ''.join(cards) if cards else '<div class="empty-state" data-i18n="literature-no-match"></div>'
    return f'''
      <div class="literature-summary-grid">{summary_html}</div>
      <div class="section-note"><span data-i18n="literature-run-date"></span>: {run_date or "N/A"}</div>
      {new_researchers_html}
      <div class="literature-grid">{cards_html}</div>'''


# ── Full HTML ─────────────────────────────────────────────────

def assemble(df, figs, table_html, filters_html, student_html, literature_html, offline=False):
    plotly_js = '<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>'
    if offline:
        import plotly
        plotly_js = f'<script>{plotly.offline.get_plotlyjs()}</script>'

    div_ids = [
        'chart-map',
        'chart-inst',
        'chart-tags',
        'chart-kanban',
        'chart-region',
        'chart-type',
    ]
    map_div, inst_div, tags_div, kanban_div, region_div, type_div = [
        to_div(fig, div_id) for fig, div_id in zip(figs, div_ids)
    ]
    sc = stats_cards(df)
    researcher_map_json = _json.dumps(build_researcher_map_data(df), ensure_ascii=False)
    latest_update = str(df['last_updated'].dropna().max()) if 'last_updated' in df and not df['last_updated'].dropna().empty else 'N/A'
    institution_count = int(df['inst_display'].nunique())
    region_count = int(df['region'].dropna().nunique())
    tag_count = len({tag for tags in df['tags'] if isinstance(tags, list) for tag in tags})

    # ---------- CSS ----------
    CSS = """
:root{
  --bg:#f5f1e8;--bg-soft:#fbf8f1;--card:rgba(255,255,255,.84);--card-strong:#fff;
  --border:rgba(15,23,42,.1);--text:#142132;--text2:#5e6c7c;--text3:#7b8794;
  --accent:#0f766e;--accent-2:#c2410c;--accent-soft:rgba(15,118,110,.12);
  --shadow:0 18px 40px rgba(20,33,50,.08);--shadow-soft:0 10px 24px rgba(20,33,50,.06);
  --radius:22px;--radius-sm:14px;
}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Plus Jakarta Sans',sans-serif;background:
  radial-gradient(circle at top left, rgba(15,118,110,.12), transparent 32%),
  radial-gradient(circle at top right, rgba(194,65,12,.12), transparent 24%),
  linear-gradient(180deg, #fbf8f1 0%, #f3ede1 100%);
  color:var(--text);min-height:100vh}
a,button,select,input{font-family:inherit}
.page-shell{width:min(1480px,calc(100vw - 40px));margin:24px auto 40px}
.header{position:relative;overflow:hidden;background:
  linear-gradient(135deg, #17324a 0%, #123d4f 42%, #6b2a12 100%);
  color:#f8fafc;padding:36px;border-radius:32px;display:grid;
  grid-template-columns:minmax(0,1.6fr) minmax(320px,1fr);gap:24px;
  box-shadow:0 30px 80px rgba(20,33,50,.18);border:1px solid rgba(255,255,255,.08)}
.header::before{content:'';position:absolute;inset:auto -8% -28% auto;width:320px;height:320px;
  background:radial-gradient(circle, rgba(255,255,255,.16) 0%, rgba(255,255,255,0) 68%);
  pointer-events:none}
.header-left{position:relative;z-index:1;display:flex;flex-direction:column;gap:14px}
.hero-kicker{display:inline-flex;align-items:center;width:max-content;padding:8px 14px;border-radius:999px;
  background:rgba(255,255,255,.1);border:1px solid rgba(255,255,255,.14);
  color:#d9ece8;font-size:12px;font-weight:600;letter-spacing:.08em;text-transform:uppercase}
.header-left h1{font-family:'Outfit',sans-serif;font-size:46px;line-height:1.02;font-weight:700;letter-spacing:-.04em;max-width:10ch}
.header-left p{max-width:62ch;font-size:15px;line-height:1.7;color:rgba(248,250,252,.8)}
.header-right{position:relative;z-index:1;display:flex;flex-direction:column;justify-content:space-between;gap:18px}
.header-actions{display:flex;justify-content:flex-end;gap:10px;flex-wrap:wrap}
.lang-toggle,.meta-tag{border-radius:999px;padding:9px 16px;font-size:12px;font-weight:600}
.lang-toggle{background:rgba(255,255,255,.12);border:1px solid rgba(255,255,255,.22);color:#f8fafc;cursor:pointer;
  transition:background .18s ease,border-color .18s ease,transform .18s ease}
.lang-toggle:hover{background:rgba(255,255,255,.2);border-color:rgba(255,255,255,.4);transform:translateY(-1px)}
.meta-tag{background:rgba(15,118,110,.26);border:1px solid rgba(167,243,208,.24);color:#d8f7ea}
.hero-panel{align-self:stretch;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.12);
  border-radius:24px;padding:20px;backdrop-filter:blur(14px)}
.hero-panel-label{font-size:12px;text-transform:uppercase;letter-spacing:.08em;color:rgba(226,232,240,.76);font-weight:600}
.hero-panel-date{margin-top:10px;font-family:'Outfit',sans-serif;font-size:28px;font-weight:700;letter-spacing:-.03em}
.hero-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin-top:18px}
.hero-metric{padding:14px;border-radius:18px;background:rgba(8,15,26,.16);border:1px solid rgba(255,255,255,.08)}
.hero-metric span{display:block;font-family:'Outfit',sans-serif;font-size:26px;font-weight:700;line-height:1}
.hero-metric small{display:block;margin-top:8px;color:rgba(226,232,240,.74);font-size:11px;text-transform:uppercase;letter-spacing:.08em}

.stats-row{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px;margin-top:18px}
.stat-card{padding:18px 20px;background:var(--card);border:1px solid rgba(20,33,50,.08);
  border-radius:24px;box-shadow:var(--shadow-soft);backdrop-filter:blur(10px)}
.stat-card-top{display:flex;align-items:center;justify-content:space-between;gap:12px}
.stat-label{font-size:12px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--text3)}
.stat-accent{width:34px;height:6px;border-radius:999px;display:inline-block}
.stat-value{margin-top:18px;font-family:'Outfit',sans-serif;font-size:38px;font-weight:700;line-height:1}
.stat-microcopy{margin-top:10px;font-size:13px;color:var(--text2)}

.tabs{display:flex;gap:8px;padding:10px;background:rgba(255,255,255,.52);border:1px solid rgba(20,33,50,.08);
  border-radius:999px;box-shadow:var(--shadow-soft);margin:18px 0 0;overflow-x:auto}
.tab-btn{padding:11px 18px;border:none;background:none;cursor:pointer;font-size:13px;font-weight:700;
  color:var(--text2);border-radius:999px;transition:all .18s ease;white-space:nowrap}
.tab-btn:hover{color:var(--text);background:rgba(15,118,110,.08)}
.tab-btn.active{color:#f8fafc;background:linear-gradient(135deg,#0f766e 0%, #115e59 100%);
  box-shadow:0 12px 24px rgba(15,118,110,.24)}

.tab-content{display:none;padding:18px 0 0;animation:fadeIn .22s ease}
.tab-content.active{display:block}
@keyframes fadeIn{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:translateY(0)}}
.card{background:var(--card);border:1px solid rgba(20,33,50,.08);border-radius:28px;padding:24px;
  box-shadow:var(--shadow);backdrop-filter:blur(12px);margin-bottom:18px}
.card.card-map{background:linear-gradient(180deg,#0f172a 0%, #14213d 100%);border-color:rgba(148,163,184,.18)}
.card-title{font-size:12px;font-weight:700;color:var(--text3);margin-bottom:12px;text-transform:uppercase;letter-spacing:.1em}
.card.card-map .card-title{color:#94a3b8}
.chart-grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}
.card-hint{font-size:13px;color:var(--text2);margin:-4px 0 14px}
.card.card-map .card-hint{color:#94a3b8}

.filter-bar{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:16px;padding:16px 18px;background:var(--card);
  border:1px solid rgba(20,33,50,.08);border-radius:24px;box-shadow:var(--shadow-soft)}
.filter-bar select,.filter-input{
  padding:10px 14px;border:1px solid rgba(20,33,50,.12);border-radius:14px;font-size:13px;
  background:rgba(255,255,255,.88);color:var(--text);outline:none;transition:border-color .15s ease,box-shadow .15s ease}
.filter-bar select:focus,.filter-input:focus{border-color:rgba(15,118,110,.45);box-shadow:0 0 0 4px rgba(15,118,110,.08)}
.filter-input{width:220px}

.section-note{margin:0 0 14px;padding:14px 16px;border-radius:18px;background:rgba(15,118,110,.07);
  border:1px solid rgba(15,118,110,.14);color:var(--text2);font-size:13px;line-height:1.55}
.table-wrap{overflow-x:auto;border-radius:28px;border:1px solid rgba(20,33,50,.08);box-shadow:var(--shadow);background:var(--card)}
#researcherTable{width:100%;border-collapse:collapse;font-size:13px}
#researcherTable th{background:rgba(251,248,241,.9);padding:14px 16px;text-align:left;cursor:pointer;
  user-select:none;white-space:nowrap;border-bottom:1px solid rgba(20,33,50,.08);
  font-weight:700;font-size:11px;color:var(--text3);text-transform:uppercase;letter-spacing:.08em}
#researcherTable th:hover{color:var(--accent)}
#researcherTable th::after{content:' ↕';opacity:.3;font-size:10px}
#researcherTable td{padding:14px 16px;border-bottom:1px solid rgba(20,33,50,.06);vertical-align:top}
#researcherTable tr:hover td{background:rgba(15,118,110,.03)}
.table-link{color:var(--accent);text-decoration:none;font-weight:700}
.table-link:hover{text-decoration:underline}
.student-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}
.student-card{padding:18px;border-radius:24px;background:var(--card);border:1px solid rgba(20,33,50,.08);box-shadow:var(--shadow-soft)}
.student-card-top{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;margin-bottom:8px}
.student-name{font-family:'Outfit',sans-serif;font-size:18px;font-weight:700;color:var(--text)}
.student-meta{font-size:12px;color:var(--text3);margin-top:4px}
.student-submeta{font-size:13px;color:var(--text2);margin-bottom:12px}
.student-note{margin-top:12px;font-size:13px;line-height:1.6;color:var(--text2)}
.empty-state{padding:24px;border-radius:24px;background:var(--card);border:1px dashed rgba(20,33,50,.16);color:var(--text2);text-align:center}
.literature-summary-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px;margin-bottom:16px}
.literature-stat{padding:18px;border-radius:22px;background:var(--card);border:1px solid rgba(20,33,50,.08);box-shadow:var(--shadow-soft)}
.literature-stat span{display:block;font-family:'Outfit',sans-serif;font-size:34px;font-weight:700;line-height:1;color:var(--accent)}
.literature-stat small{display:block;margin-top:10px;font-size:11px;color:var(--text3);text-transform:uppercase;letter-spacing:.08em}
.literature-added-block{margin:0 0 16px;padding:18px;border-radius:22px;background:var(--card);border:1px solid rgba(20,33,50,.08);box-shadow:var(--shadow-soft)}
.literature-added-list{margin:10px 0 0 18px;color:var(--text2);display:grid;gap:8px}
.literature-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}
.literature-card{padding:18px;border-radius:24px;background:var(--card);border:1px solid rgba(20,33,50,.08);box-shadow:var(--shadow-soft)}
.literature-card-top{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}
.literature-title{font-family:'Outfit',sans-serif;font-size:20px;font-weight:700;line-height:1.25;color:var(--text)}
.literature-meta{margin-top:6px;font-size:12px;color:var(--text3)}
.literature-authors{margin-top:14px;font-size:13px;line-height:1.7;color:var(--text2)}
.literature-more{margin-top:10px;font-size:12px;color:var(--text3)}

.badge{display:inline-block;padding:4px 10px;border-radius:999px;font-size:11px;font-weight:700;letter-spacing:.02em}
.badge-high{background:#dcfce7;color:#166534}
.badge-medium{background:#fef3c7;color:#92400e}
.badge-low{background:#fee2e2;color:#b91c1c}
.badge-internship-only{background:#ede9fe;color:#6d28d9}
.badge-type-faculty{background:#d9f0ed;color:#0f766e}
.badge-type-industry{background:#ffedd5;color:#c2410c}
.priority-dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:6px;vertical-align:middle}
.priority-high{background:#dc2626}
.priority-medium{background:#d97706}
.priority-low{background:#64748b}

#drawerOverlay{display:none;position:fixed;inset:0;background:rgba(20,33,50,.46);z-index:9998;backdrop-filter:blur(4px)}
#drawerOverlay.open{display:block}
#instDrawer{position:fixed;top:0;right:-520px;width:500px;height:100vh;
  background:linear-gradient(180deg,#142132 0%, #0e1927 100%);border-left:1px solid rgba(148,163,184,.18);
  box-shadow:-20px 0 60px rgba(15,23,42,.42);z-index:9999;transition:right .32s cubic-bezier(.4,0,.2,1);
  display:flex;flex-direction:column;overflow:hidden}
#instDrawer.open{right:0}
#drawerHeader{padding:22px 22px 18px;border-bottom:1px solid rgba(148,163,184,.14);display:flex;align-items:flex-start;justify-content:space-between;gap:12px;flex-shrink:0}
#drawerHeaderText{display:flex;flex-direction:column;gap:8px;min-width:0}
#drawerTitle{font-family:'Outfit',sans-serif;font-size:22px;font-weight:700;color:#f8fafc;line-height:1.05}
#drawerSubtitle{font-size:12px;color:#8ba0b6;text-transform:uppercase;letter-spacing:.08em}
#drawerClose{background:none;border:none;color:#8ba0b6;cursor:pointer;font-size:28px;line-height:1;padding:0 2px;border-radius:8px;transition:color .15s ease,transform .15s ease}
#drawerClose:hover{color:#f8fafc;transform:translateY(-1px)}
#drawerBody{flex:1;overflow-y:auto;padding:18px;scrollbar-width:thin;scrollbar-color:#334155 transparent}
#drawerBody::-webkit-scrollbar{width:6px}
#drawerBody::-webkit-scrollbar-thumb{background:#334155;border-radius:999px}

.drawer-intro{padding:18px;border-radius:22px;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.08);margin-bottom:14px}
.drawer-meta{display:flex;flex-wrap:wrap;gap:8px}
.drawer-meta-pill{padding:6px 10px;border-radius:999px;background:rgba(15,118,110,.18);border:1px solid rgba(94,234,212,.14);font-size:11px;font-weight:700;color:#d8f7ea}
.drawer-stats{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin-top:14px}
.drawer-stat{padding:12px;border-radius:18px;background:rgba(8,15,26,.28);border:1px solid rgba(255,255,255,.06)}
.drawer-stat span{display:block;font-family:'Outfit',sans-serif;font-size:24px;font-weight:700;color:#f8fafc}
.drawer-stat small{display:block;margin-top:6px;font-size:11px;color:#8ba0b6;text-transform:uppercase;letter-spacing:.08em}
.drawer-stack{display:grid;gap:12px}

.r-card{background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.08);border-radius:22px;padding:18px;transition:border-color .16s ease,transform .16s ease}
.r-card:hover{border-color:rgba(94,234,212,.22);transform:translateY(-1px)}
.r-card-top{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}
.r-meta{display:flex;flex-wrap:wrap;gap:8px;margin:14px 0 10px}
.r-type{display:inline-flex;padding:4px 10px;border-radius:999px;background:rgba(255,255,255,.08);font-size:11px;font-weight:700;color:#d6e2ef;text-transform:uppercase;letter-spacing:.08em}
.r-open{display:inline-flex;padding:4px 10px;border-radius:999px;background:rgba(22,163,74,.16);border:1px solid rgba(74,222,128,.18);font-size:11px;font-weight:700;color:#bbf7d0}
.r-name{font-size:17px;font-weight:700;color:#f8fafc;line-height:1.2}
.r-pos{font-size:13px;color:#94a3b8;margin-top:4px}
.r-chance{display:inline-flex;padding:4px 10px;border-radius:999px;font-size:11px;font-weight:700;margin-top:2px}
.r-chance-high{background:#052e16;color:#86efac;border:1px solid #166534}
.r-chance-medium{background:#431407;color:#fdba74;border:1px solid #9a3412}
.r-chance-low{background:#450a0a;color:#fca5a5;border:1px solid #991b1b}
.r-chance-internship-only{background:#2e1065;color:#d8b4fe;border:1px solid #6d28d9}
.chip-row{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}
.focus-chip,.tag-chip{display:inline-flex;padding:6px 10px;border-radius:999px;font-size:11px;font-weight:700}
.focus-chip{background:rgba(15,118,110,.14);color:#d1faf5;border:1px solid rgba(94,234,212,.12)}
.tag-chip{background:rgba(255,255,255,.08);color:#d6e2ef;border:1px solid rgba(255,255,255,.08)}
.r-notes{margin-top:14px;font-size:12px;line-height:1.65;color:#bfd0df}
.r-links{display:flex;flex-wrap:wrap;gap:10px;margin-top:14px}
.r-link{display:inline-flex;align-items:center;gap:6px;color:#d8f7ea;font-size:12px;font-weight:700;text-decoration:none;
  padding:8px 13px;border:1px solid rgba(94,234,212,.16);border-radius:14px;background:rgba(15,118,110,.14);
  transition:background .15s ease,border-color .15s ease,transform .15s ease}
.r-link:hover{background:rgba(15,118,110,.22);border-color:rgba(94,234,212,.28);transform:translateY(-1px)}
.r-no-link{font-size:12px;color:#71859a}
.team-members{margin-top:16px;padding-top:16px;border-top:1px solid rgba(255,255,255,.08)}
.team-members summary{cursor:pointer;list-style:none;font-size:12px;font-weight:700;color:#d6e2ef;text-transform:uppercase;letter-spacing:.08em}
.team-members summary::-webkit-details-marker{display:none}
.member-list{display:grid;gap:10px;margin-top:12px}
.member-card{background:rgba(8,15,26,.36);border:1px solid rgba(255,255,255,.08);border-radius:18px;padding:14px}
.member-card-top{display:flex;align-items:flex-start;justify-content:space-between;gap:10px}
.member-name{font-size:14px;font-weight:700;color:#f8fafc;line-height:1.25}
.member-pos{font-size:12px;color:#8ba0b6;margin-top:4px}
.member-note{font-size:12px;color:#bfd0df;margin-top:10px;line-height:1.6}
.member-link{margin-top:10px}
.member-no-link{font-size:12px;color:#71859a}

@media (max-width: 1180px){
  .header{grid-template-columns:1fr}
  .header-left h1{max-width:none}
  .hero-grid,.stats-row,.chart-grid,.student-grid,.literature-summary-grid,.literature-grid{grid-template-columns:repeat(2,minmax(0,1fr))}
}
@media (max-width: 760px){
  .page-shell{width:min(100vw - 20px, 100%);margin:10px auto 28px}
  .header{padding:24px;border-radius:26px}
  .header-left h1{font-size:34px}
  .hero-grid,.stats-row,.chart-grid,.drawer-stats,.student-grid,.literature-summary-grid,.literature-grid{grid-template-columns:1fr}
  .tabs{padding:8px}
  .tab-btn{padding:10px 14px}
  .card{padding:18px;border-radius:22px}
  .filter-input{width:100%}
  #instDrawer{width:min(100vw, 100%);right:-100vw}
}
"""

    # ---------- i18n ----------
    LANG_JS = r"""
const LANG = {
  en: {
    'hero-kicker':      'Targeted Directory',
    'title':            'AI4DB Research Teams Tracker',
    'subtitle':         'LLM + Database · NL2SQL · Data Agents — PhD / Internship Target List',
    'meta-tag':         'PhD / Internship',
    'hero-updated-label':'Dataset Refreshed',
    'institution-label':'Institutions',
    'region-label':    'Regions',
    'tag-count-label': 'Active Tags',
    'total-label':      'Visible Profiles',
    'faculty-label':    'Faculty / PIs',
    'industry-label':   'Industry Teams',
    'priority-label':   'High Priority',
    'total-note':       'Shown on the main dashboard',
    'faculty-note':     'Curated academic leads',
    'industry-note':    'Industry nodes',
    'priority-note':    'Priority stack',
    'tab-overview':     'Overview',
    'tab-literature':   'Literature Watch',
    'tab-map':          'World Map',
    'tab-institutions': 'Institutions',
    'tab-tags':         'Research Tags',
    'tab-kanban':       'Application Status',
    'tab-directory':    'Directory',
    'tab-students':     'Student Profiles',
    'chart-region':     'By Region',
    'chart-type':       'Faculty vs Industry',
    'chart-map':        'Geographic Distribution',
    'chart-inst':       'Researchers per Institution',
    'chart-tags':       'Research Tags',
    'chart-kanban':     'Application Pipeline',
    'map-hint':         'Click an institution bubble to inspect profiles and team members.',
    'directory-note':   'Main directory shows curated faculty and industry teams only. Unverified paper authors are hidden from the counts and filters.',
    'student-title':    'Student / Junior Profiles',
    'student-note':     'Only junior profiles with a personal homepage are listed here.',
    'student-empty':    'No student or junior profiles with a homepage have been curated yet.',
    'literature-fetched':'OpenAlex Fetched',
    'literature-matched':'Watchlist Matches',
    'literature-added':'New Profiles',
    'literature-updated':'Updated Profiles',
    'literature-added-title':'Added This Run',
    'literature-empty':'No literature report has been generated yet.',
    'literature-no-match':'No DB+LLM papers matched the latest run.',
    'literature-run-date':'Latest literature run',
    'literature-more-authors':'more authors',
    'filter-region-all':   'All Regions',
    'filter-type-all':     'All Types',
    'filter-priority-all': 'All Priorities',
    'filter-tag-all':      'All Tags',
    'filter-search':       'Search name…',
    'link-text':    'Link',
    'drawer-homepage':'Homepage',
    'drawer-no-homepage':'No homepage listed',
    'drawer-open':'Potentially Open',
    'drawer-members':'Members',
    'drawer-profiles':'Profiles',
    'drawer-teams':'Teams',
    'drawer-member-count':'Members',
    'drawer-type-faculty':'Faculty',
    'drawer-type-industry':'Industry',
    'drawer-subtitle':'Institution Snapshot',
    'name-col':     'Name',       'type-col':    'Type',
    'inst-col':     'Institution','country-col': 'Country',
    'region-col':   'Region',     'pos-col':     'Position',
    'focus-col':    'Research Focus','tags-col':  'Tags',
    'chance-col':   'Admission',  'status-col':  'Status',
    'pri-col':      'Priority',   'link-col':    'Homepage',
  },
  zh: {
    'hero-kicker':      '重点跟踪目录',
    'title':            'AI4DB 研究团队追踪',
    'subtitle':         'LLM + 数据库 · NL2SQL · 数据智能体 — 博士申请 / 实习目标列表',
    'meta-tag':         '博士 / 实习',
    'hero-updated-label':'数据更新到',
    'institution-label':'覆盖机构',
    'region-label':    '覆盖地区',
    'tag-count-label': '研究标签',
    'total-label':      '主名单条目',
    'faculty-label':    '教师 / PI',
    'industry-label':   '工业界',
    'priority-label':   '高优先级',
    'total-note':       '当前主页面展示的条目',
    'faculty-note':     '已核实的学术导师与PI',
    'industry-note':    '工业研究节点',
    'priority-note':    '重点关注名单',
    'tab-overview':     '概览',
    'tab-literature':   '最新文献',
    'tab-map':          '世界地图',
    'tab-institutions': '机构分布',
    'tab-tags':         '研究方向',
    'tab-kanban':       '申请状态',
    'tab-directory':    '完整名录',
    'tab-students':     '学生主页',
    'chart-region':     '地区分布',
    'chart-type':       '学术 vs 工业',
    'chart-map':        '地理分布',
    'chart-inst':       '各机构学者数',
    'chart-tags':       '研究方向分布',
    'chart-kanban':     '申请漏斗',
    'map-hint':         '点击任一机构气泡，可查看该机构下的个人与团队成员。',
    'directory-note':   '主目录只展示已核实的教师与工业界团队；自动抓到但未核实的论文作者不会进入计数和筛选。',
    'student-title':    '学生 / 初级研究者主页',
    'student-note':     '这里只展示带个人主页的学生或初级研究者条目。',
    'student-empty':    '目前还没有带个人主页的学生或初级研究者条目。',
    'literature-fetched':'抓取文献',
    'literature-matched':'命中文献',
    'literature-added':'新增条目',
    'literature-updated':'更新条目',
    'literature-added-title':'本轮新增',
    'literature-empty':'还没有生成过文献日报。',
    'literature-no-match':'最近一次运行没有命中 DB+LLM 文献。',
    'literature-run-date':'最近一次文献扫描',
    'literature-more-authors':'位作者',
    'filter-region-all':   '全部地区',
    'filter-type-all':     '全部类型',
    'filter-priority-all': '全部优先级',
    'filter-tag-all':      '全部标签',
    'filter-search':       '搜索姓名…',
    'link-text':    '主页',
    'drawer-homepage':'主页',
    'drawer-no-homepage':'暂无主页',
    'drawer-open':'可能招收',
    'drawer-members':'团队成员',
    'drawer-profiles':'个人条目',
    'drawer-teams':'团队条目',
    'drawer-member-count':'成员数',
    'drawer-type-faculty':'学术界',
    'drawer-type-industry':'工业界',
    'drawer-subtitle':'机构概览',
    'name-col':     '姓名',       'type-col':    '类型',
    'inst-col':     '机构',       'country-col': '国家',
    'region-col':   '地区',       'pos-col':     '职位',
    'focus-col':    '研究方向',   'tags-col':    '标签',
    'chance-col':   '录取机会',   'status-col':  '申请状态',
    'pri-col':      '优先级',     'link-col':    '主页',
  }
};
"""

    # ---------- JS ----------
    # Note: all { } here are literal JS, not f-string interpolations
    JS = (
        LANG_JS +
        "const RESEARCHER_MAP = " + researcher_map_json + ";\n"
        + r"""
let currentLang = 'en';
let currentDrawerKey = null;

function langText(key, fallback) {
  return LANG[currentLang]?.[key] || fallback || key;
}

function applyLang(lang) {
  const t = LANG[lang];
  document.querySelectorAll('[data-i18n]').forEach(el => {
    const k = el.dataset.i18n; if (t[k]!==undefined) el.textContent = t[k];
  });
  document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
    const k = el.dataset.i18nPlaceholder; if (t[k]!==undefined) el.placeholder = t[k];
  });
  document.querySelectorAll('select option[data-i18n]').forEach(el => {
    const k = el.dataset.i18n; if (t[k]!==undefined) el.textContent = t[k];
  });
  document.querySelectorAll('.table-link span[data-i18n="link-text"]').forEach(el => {
    el.textContent = t['link-text'] || 'Link';
  });
  document.querySelector('.lang-toggle').textContent = lang==='en' ? '中文' : 'EN';
  document.documentElement.setAttribute('data-lang', lang);
  currentLang = lang;
  if (currentDrawerKey) openDrawer(currentDrawerKey);
}
function toggleLang() { applyLang(currentLang==='en' ? 'zh' : 'en'); }

/* Tabs */
function showTab(idx) {
  document.querySelectorAll('.tab-content').forEach((el,i) => el.classList.toggle('active', i===idx));
  document.querySelectorAll('.tab-btn').forEach((el,i) => el.classList.toggle('active', i===idx));
  if (idx < 6) window.dispatchEvent(new Event('resize'));
  if (idx === 2) setTimeout(attachMapClick, 200);
}

/* Table filter */
function filterTable() {
  const region   = (document.getElementById('fRegion')?.value   || '').toLowerCase();
  const type     = (document.getElementById('fType')?.value     || '').toLowerCase();
  const priority = (document.getElementById('fPriority')?.value || '').toLowerCase();
  const tag      = (document.getElementById('fTag')?.value      || '').toLowerCase();
  const search   = (document.getElementById('fSearch')?.value   || '').toLowerCase();
  document.querySelectorAll('#researcherTable tbody tr').forEach(row => {
    const get = col => (row.querySelector(`td[data-col="${col}"]`)?.textContent||'').toLowerCase();
    let show = true;
    if (region   && get('region')   !== region)           show=false;
    if (type     && get('type').indexOf(type)   ===-1)    show=false;
    if (priority && get('priority').indexOf(priority)===-1) show=false;
    if (tag      && get('tags_str').indexOf(tag)===-1)    show=false;
    if (search   && get('name').indexOf(search)===-1)     show=false;
    row.style.display = show ? '' : 'none';
  });
}

/* Table sort */
function sortTable(th) {
  const col = th.dataset.col;
  const asc = th.dataset.sort !== 'asc';
  th.dataset.sort = asc ? 'asc' : 'desc';
  const tbody = th.closest('table').querySelector('tbody');
  Array.from(tbody.querySelectorAll('tr'))
    .sort((a,b)=>{
      const av = a.querySelector(`td[data-col="${col}"]`)?.textContent||'';
      const bv = b.querySelector(`td[data-col="${col}"]`)?.textContent||'';
      return asc ? av.localeCompare(bv) : bv.localeCompare(av);
    })
    .forEach(r=>tbody.appendChild(r));
}

function renderHomepageButton(url, extraClass='') {
  if (!url) return `<span class="r-no-link ${extraClass}">${langText('drawer-no-homepage', 'No homepage listed')}</span>`;
  return `<a href="${url}" target="_blank" rel="noopener" class="r-link ${extraClass}">
           <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
             <path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6"/>
             <polyline points="15 3 21 3 21 9"/>
             <line x1="10" y1="14" x2="21" y2="3"/>
           </svg>
           ${langText('drawer-homepage', 'Homepage')}
         </a>`;
}

function renderMemberCard(member) {
  const homepage = renderHomepageButton(member.homepage || '', 'member-link');
  return `
    <div class="member-card">
      <div class="member-card-top">
        <div>
          <div class="member-name">${member.name || ''}</div>
          <div class="member-pos">${member.position || ''}</div>
        </div>
      </div>
      ${homepage}
      ${member.notes ? `<div class="member-note">${member.notes}</div>` : ''}
    </div>`;
}

function renderResearchCard(r) {
  const chClass = 'r-chance-' + (r.admission_chance||'medium').replace(/\s/g,'-');
  const tagsHtml = (r.tags||[]).map(t=>`<span class="tag-chip">${t}</span>`).join('');
  const focusHtml = (r.research_focus||[]).slice(0, 4).map(t=>`<span class="focus-chip">${t}</span>`).join('');
  const openBadge = r.taking_students ? `<span class="r-open">${langText('drawer-open', 'Potentially Open')}</span>` : '';
  const linkBtn = renderHomepageButton(r.homepage || '');
  const members = Array.isArray(r.members) ? r.members : [];
  const membersHtml = members.length ? `
      <details class="team-members">
        <summary>${langText('drawer-members', 'Members')} (${members.length})</summary>
        <div class="member-list">
          ${members.map(renderMemberCard).join('')}
        </div>
      </details>` : '';
  const typeLabel = langText(`drawer-type-${r.type}`, r.type || '');
  return `
      <div class="r-card">
        <div class="r-card-top">
          <div>
            <div class="r-name">${r.name}</div>
            <div class="r-pos">${r.position||''}</div>
          </div>
          <span class="r-chance ${chClass}">${r.admission_chance||''}</span>
        </div>
        <div class="r-meta">
          <span class="r-type">${typeLabel}</span>
          ${openBadge}
        </div>
        ${focusHtml ? `<div class="chip-row">${focusHtml}</div>` : ''}
        ${tagsHtml ? `<div class="chip-row">${tagsHtml}</div>` : ''}
        ${r.notes ? `<div class="r-notes">${r.notes}</div>` : ''}
        <div class="r-links">${linkBtn}</div>
        ${membersHtml}
      </div>`;
}

/* ── Drawer ── */
function openDrawer(instKey) {
  const data = RESEARCHER_MAP[instKey];
  if (!data) return;
  currentDrawerKey = instKey;
  document.getElementById('drawerTitle').textContent = data.display_name;
  document.getElementById('drawerSubtitle').textContent = langText('drawer-subtitle', 'Institution Snapshot');
  const body = document.getElementById('drawerBody');
  const totalProfiles = data.researchers.length;
  const totalTeams = data.researchers.filter(r => r.type === 'industry' && ((r.position||'').toLowerCase().includes('team') || (Array.isArray(r.members) && r.members.length))).length;
  const totalMembers = data.researchers.reduce((sum, r) => sum + ((Array.isArray(r.members) ? r.members.length : 0)), 0);
  const metaParts = [data.region, data.country, data.qs_rank ? `QS #${data.qs_rank}` : ''].filter(Boolean);
  body.innerHTML = `
    <div class="drawer-intro">
      <div class="drawer-meta">
        ${metaParts.map(item => `<span class="drawer-meta-pill">${item}</span>`).join('')}
      </div>
      <div class="drawer-stats">
        <div class="drawer-stat"><span>${totalProfiles}</span><small>${langText('drawer-profiles', 'Profiles')}</small></div>
        <div class="drawer-stat"><span>${totalTeams}</span><small>${langText('drawer-teams', 'Teams')}</small></div>
        <div class="drawer-stat"><span>${totalMembers}</span><small>${langText('drawer-member-count', 'Members')}</small></div>
      </div>
    </div>
    <div class="drawer-stack">
      ${data.researchers.map(renderResearchCard).join('')}
    </div>`;
  document.getElementById('instDrawer').classList.add('open');
  document.getElementById('drawerOverlay').classList.add('open');
}
function closeDrawer() {
  document.getElementById('instDrawer').classList.remove('open');
  document.getElementById('drawerOverlay').classList.remove('open');
  currentDrawerKey = null;
}
document.addEventListener('keydown', e => { if (e.key==='Escape') closeDrawer(); });

function attachMapClick() {
  const mapDiv = document.querySelector('#tab-2 .js-plotly-plot');
  if (!mapDiv || mapDiv._bound) return;
  mapDiv._bound = true;
  mapDiv.on('plotly_click', function(evt) {
    if (!evt||!evt.points||!evt.points.length) return;
    const pt = evt.points[0];
    const key = pt.customdata ? pt.customdata[0] : null;
    if (key) openDrawer(key);
  });
}

// Init
applyLang('en');
setTimeout(attachMapClick, 600);
"""
    )

    # ---------- HTML ----------
    return f"""<!DOCTYPE html>
<html lang="en" data-lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AI4DB Research Teams Tracker</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@500;600;700&family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
{plotly_js}
<style>{CSS}</style>
</head>
<body>
<div class="page-shell">
<div class="header">
  <div class="header-left">
    <span class="hero-kicker" data-i18n="hero-kicker">Targeted Directory</span>
    <h1 data-i18n="title">AI4DB Research Teams Tracker</h1>
    <p data-i18n="subtitle">LLM + Database · NL2SQL · Data Agents</p>
  </div>
  <div class="header-right">
    <div class="header-actions">
      <span class="meta-tag" data-i18n="meta-tag">PhD / Internship</span>
      <button class="lang-toggle" onclick="toggleLang()">中文</button>
    </div>
    <div class="hero-panel">
      <div class="hero-panel-label" data-i18n="hero-updated-label">Dataset Refreshed</div>
      <div class="hero-panel-date">{latest_update}</div>
      <div class="hero-grid">
        <div class="hero-metric">
          <span>{institution_count}</span>
          <small data-i18n="institution-label">Institutions</small>
        </div>
        <div class="hero-metric">
          <span>{region_count}</span>
          <small data-i18n="region-label">Regions</small>
        </div>
        <div class="hero-metric">
          <span>{tag_count}</span>
          <small data-i18n="tag-count-label">Active Tags</small>
        </div>
      </div>
    </div>
  </div>
</div>

{sc}

<div class="tabs">
  <button class="tab-btn active" onclick="showTab(0)" data-i18n="tab-overview">Overview</button>
  <button class="tab-btn"        onclick="showTab(1)" data-i18n="tab-literature">Literature Watch</button>
  <button class="tab-btn"        onclick="showTab(2)" data-i18n="tab-map">World Map</button>
  <button class="tab-btn"        onclick="showTab(3)" data-i18n="tab-institutions">Institutions</button>
  <button class="tab-btn"        onclick="showTab(4)" data-i18n="tab-tags">Research Tags</button>
  <button class="tab-btn"        onclick="showTab(5)" data-i18n="tab-kanban">Application Status</button>
  <button class="tab-btn"        onclick="showTab(6)" data-i18n="tab-directory">Directory</button>
  <button class="tab-btn"        onclick="showTab(7)" data-i18n="tab-students">Student Profiles</button>
</div>

<div class="tab-content active" id="tab-0">
  <div class="chart-grid">
    <div class="card">
      <div class="card-title" data-i18n="chart-region">By Region</div>
      {region_div}
    </div>
    <div class="card">
      <div class="card-title" data-i18n="chart-type">Faculty vs Industry</div>
      {type_div}
    </div>
  </div>
</div>

<div class="tab-content" id="tab-1">
  <div class="card">
    <div class="card-title" data-i18n="tab-literature">Literature Watch</div>
    {literature_html}
  </div>
</div>

<div class="tab-content" id="tab-2">
  <div class="card card-map">
    <div class="card-title" data-i18n="chart-map">Geographic Distribution</div>
    <p class="card-hint" data-i18n="map-hint">Click an institution bubble to inspect profiles and team members.</p>
    {map_div}
  </div>
</div>

<div class="tab-content" id="tab-3">
  <div class="card">
    <div class="card-title" data-i18n="chart-inst">Researchers per Institution</div>
    {inst_div}
  </div>
</div>

<div class="tab-content" id="tab-4">
  <div class="card">
    <div class="card-title" data-i18n="chart-tags">Research Tags</div>
    {tags_div}
  </div>
</div>

<div class="tab-content" id="tab-5">
  <div class="card">
    <div class="card-title" data-i18n="chart-kanban">Application Pipeline</div>
    {kanban_div}
  </div>
</div>

<div class="tab-content" id="tab-6">
  <div class="section-note" data-i18n="directory-note"></div>
  {filters_html}
  <div class="table-wrap">{table_html}</div>
</div>

<div class="tab-content" id="tab-7">
  <div class="card">
    <div class="card-title" data-i18n="student-title">Student / Junior Profiles</div>
    <p class="card-hint" data-i18n="student-note"></p>
    {student_html}
  </div>
</div>

<!-- Drawer -->
<div id="drawerOverlay" onclick="closeDrawer()"></div>
<div id="instDrawer">
  <div id="drawerHeader">
    <div id="drawerHeaderText">
      <div id="drawerSubtitle"></div>
      <div id="drawerTitle"></div>
    </div>
    <button id="drawerClose" onclick="closeDrawer()">×</button>
  </div>
  <div id="drawerBody"></div>
</div>

<script>{JS}</script>
</div>
</body>
</html>"""


# ── Main ──────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--offline', action='store_true')
    args = parser.parse_args()

    data = load_researchers()
    institutions = load_institutions()
    literature_report = load_literature_report()
    full_df = build_df(data, institutions)
    df = curated_df(full_df)
    students = student_df(full_df)

    df[['id','name','type','inst_display','country','region','position',
        'focus_str','tags_str','admission_chance','application_status',
        'priority','homepage','notes']].to_csv(CSV_PATH, index=False, encoding='utf-8-sig')
    print(f"  CSV: {CSV_PATH}")

    figs = [
        chart_map(df),
        chart_institution(df),
        chart_tags(df),
        chart_kanban(df),
        chart_region_donut(df),
        chart_type_donut(df),
    ]
    table_html   = build_table(df)
    filters_html = build_filters(df)
    student_html = build_student_cards(students)
    literature_html = build_literature_cards(literature_report)
    html = assemble(df, figs, table_html, filters_html, student_html, literature_html, offline=args.offline)

    with open(HTML_PATH, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"  Dashboard: {HTML_PATH}")

    with open(INDEX_PATH, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"  Index: {INDEX_PATH}")


if __name__ == '__main__':
    main()
