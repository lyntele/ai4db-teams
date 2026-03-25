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

# ── Palette ───────────────────────────────────────────────────
REGION_COLORS  = {
    'Asia': '#6366f1',
    'Europe': '#0ea5e9',
    'North America': '#10b981',
    'Oceania': '#f59e0b',
    'South America': '#ef4444',
    'Africa': '#14b8a6',
}
TYPE_COLORS    = {'faculty':'#818cf8','industry':'#fb923c'}
CHANCE_COLORS  = {'high':'#10b981','medium':'#f59e0b','low':'#ef4444','internship-only':'#a855f7'}
PRIORITY_COLORS= {'high':'#ef4444','medium':'#f59e0b','low':'#94a3b8'}

HOVER_LABEL = dict(
    bgcolor='#0f172a', bordercolor='#334155',
    font=dict(family='Inter, sans-serif', size=12, color='#f1f5f9'),
)
BASE_LAYOUT = dict(
    font=dict(family='Inter, -apple-system, sans-serif', size=13, color='#334155'),
    paper_bgcolor='white', plot_bgcolor='white',
    hoverlabel=HOVER_LABEL,
    margin=dict(l=16, r=16, t=40, b=16),
)


# ── Data helpers ──────────────────────────────────────────────

def build_df(data, institutions):
    rows = []
    for r in data['researchers']:
        inst_key = r.get('institution', '')
        inst = institutions.get(inst_key, {})
        row = dict(r)
        row['inst_display'] = inst.get('display_name') or r.get('institution_display_name') or inst_key
        row['lat'] = inst.get('lat') if inst else r.get('institution_lat')
        row['lon'] = inst.get('lon') if inst else r.get('institution_lon')
        row['qs_rank'] = inst.get('qs_rank') if inst else r.get('institution_qs_rank')
        row['inst_type'] = inst.get('type', '')
        row['tags_str'] = ', '.join(r.get('tags', []))
        row['focus_str'] = ', '.join(r.get('research_focus', []))
        row.pop('institution_display_name', None)
        row.pop('institution_qs_rank', None)
        row.pop('institution_lat', None)
        row.pop('institution_lon', None)
        rows.append(row)
    return pd.DataFrame(rows)


def build_researcher_map_data(df):
    """Dict keyed by institution raw key → drawer card data."""
    result = {}
    for _, r in df.iterrows():
        key = r.get('institution', '')
        if not key:
            continue
        result.setdefault(key, {'display_name': r.get('inst_display', key), 'researchers': []})
        result[key]['researchers'].append({
            'name':     r.get('name', ''),
            'position': r.get('position', ''),
            'type':     r.get('type', ''),
            'homepage': r.get('homepage', '') or '',
            'research_focus': list(r.get('research_focus') or []),
            'tags':           list(r.get('tags') or []),
            'admission_chance': r.get('admission_chance', '') or '',
            'priority':       r.get('priority', '') or '',
            'taking_students': bool(r.get('currently_taking_students', False)),
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
        font=dict(family='Inter, sans-serif', size=13, color='#94a3b8'),
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
            colorscale=[[0, '#a5b4fc'], [0.5, '#6366f1'], [1, '#3730a3']],
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
        'considering': '#6366f1', 'shortlisted': '#8b5cf6',
        'contacted': '#0ea5e9', 'awaiting-reply': '#f59e0b',
        'applied': '#3b82f6', 'accepted': '#10b981',
        'rejected': '#ef4444', 'not-applicable': '#94a3b8',
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
            fillcolor='rgba(99,102,241,0.04)',
        ),
        hovertemplate='<b>%{y}</b><br>Count: %{x}<br>%{percentInitial} of pipeline<extra></extra>',
        textfont=dict(family='Inter, sans-serif', size=12, color='white'),
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
        textinfo='percent', textfont=dict(size=12, family='Inter'),
        hovertemplate='<b>%{label}</b><br>%{value} researchers (%{percent})<extra></extra>',
        direction='clockwise', sort=False,
        pull=[0.05] + [0] * (len(agg) - 1),
    ))
    fig.add_annotation(text=f'<b>{total}</b>', x=0.5, y=0.57, showarrow=False,
                       font=dict(size=30, color='#0f172a', family='Inter'),
                       xref='paper', yref='paper')
    fig.add_annotation(text='researchers', x=0.5, y=0.43, showarrow=False,
                       font=dict(size=11, color='#64748b', family='Inter'),
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
        textinfo='percent', textfont=dict(size=12, family='Inter'),
        hovertemplate='<b>%{label}</b><br>%{value} (%{percent})<extra></extra>',
        pull=[0.05, 0],
    ))
    fig.add_annotation(text=f'<b>{total}</b>', x=0.5, y=0.57, showarrow=False,
                       font=dict(size=30, color='#0f172a', family='Inter'),
                       xref='paper', yref='paper')
    fig.add_annotation(text='total', x=0.5, y=0.43, showarrow=False,
                       font=dict(size=11, color='#64748b', family='Inter'),
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
        (len(df),                        'total-label',    '🎓', '#6366f1'),
        ((df['type']=='faculty').sum(),  'faculty-label',  '🏫', '#0ea5e9'),
        ((df['type']=='industry').sum(), 'industry-label', '🏢', '#10b981'),
        ((df['priority']=='high').sum(), 'priority-label', '⭐', '#f59e0b'),
    ]
    html = '<div class="stats-row">'
    for val, i18n, icon, color in cards:
        html += f'''
      <div class="stat-card" style="border-left:3px solid {color}">
        <div class="stat-icon">{icon}</div>
        <div class="stat-body">
          <div class="stat-value" style="color:{color}">{val}</div>
          <div class="stat-label" data-i18n="{i18n}"></div>
        </div>
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


# ── Full HTML ─────────────────────────────────────────────────

def assemble(df, figs, table_html, filters_html, offline=False):
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

    # ---------- CSS ----------
    CSS = """
:root{
  --bg:#f8fafc;--card:#fff;--border:#e2e8f0;--text:#0f172a;
  --text2:#64748b;--accent:#6366f1;
  --shadow:0 1px 3px rgba(0,0,0,.06),0 4px 16px rgba(0,0,0,.05);
  --radius:12px;
}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Inter',sans-serif;background:var(--bg);color:var(--text);min-height:100vh;display:flex;flex-direction:column}

/* Header */
.header{background:linear-gradient(135deg,#0f172a 0%,#1e1b4b 50%,#312e81 100%);
  color:#fff;padding:20px 32px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px}
.header-left h1{font-size:22px;font-weight:700;letter-spacing:-.3px}
.header-left p{font-size:13px;opacity:.7;margin-top:3px}
.header-right{display:flex;align-items:center;gap:12px}
.lang-toggle{background:rgba(255,255,255,.12);border:1px solid rgba(255,255,255,.2);
  color:#fff;padding:6px 16px;border-radius:20px;cursor:pointer;font-size:13px;font-weight:500;
  transition:background .2s;font-family:'Inter',sans-serif}
.lang-toggle:hover{background:rgba(255,255,255,.22)}
.meta-tag{background:rgba(99,102,241,.35);border:1px solid rgba(99,102,241,.5);
  color:#c7d2fe;padding:4px 12px;border-radius:20px;font-size:12px}

/* Stats */
.stats-row{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;padding:20px 28px 0}
.stat-card{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);
  padding:16px 20px;display:flex;align-items:center;gap:14px;box-shadow:var(--shadow)}
.stat-icon{font-size:26px}
.stat-value{font-size:28px;font-weight:700;line-height:1}
.stat-label{font-size:12px;color:var(--text2);margin-top:3px;font-weight:500}

/* Tabs */
.tabs{display:flex;padding:20px 28px 0;overflow-x:auto;gap:0}
.tab-btn{padding:10px 20px;border:none;background:none;cursor:pointer;font-size:13px;font-weight:500;
  color:var(--text2);border-bottom:2px solid transparent;transition:all .18s;white-space:nowrap;
  font-family:'Inter',sans-serif}
.tab-btn:hover{color:var(--accent)}
.tab-btn.active{color:var(--accent);border-bottom-color:var(--accent)}

/* Content */
.tab-content{display:none;padding:16px 28px 28px;animation:fadeIn .2s ease}
.tab-content.active{display:block}
@keyframes fadeIn{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:translateY(0)}}
.card{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);
  padding:20px;box-shadow:var(--shadow);margin-bottom:16px}
.card-title{font-size:12px;font-weight:600;color:var(--text2);margin-bottom:12px;
  text-transform:uppercase;letter-spacing:.6px}
.chart-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px}
.card-hint{font-size:12px;color:#475569;margin:-8px 0 12px}

/* Filters */
.filter-bar{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:16px;
  padding:14px;background:var(--card);border:1px solid var(--border);border-radius:var(--radius);
  box-shadow:var(--shadow)}
.filter-bar select,.filter-input{
  padding:7px 12px;border:1px solid var(--border);border-radius:8px;font-size:13px;
  font-family:'Inter',sans-serif;background:white;color:var(--text);outline:none;transition:border .15s}
.filter-bar select:focus,.filter-input:focus{border-color:var(--accent)}
.filter-input{width:190px}

/* Table */
.table-wrap{overflow-x:auto;border-radius:var(--radius);border:1px solid var(--border);
  box-shadow:var(--shadow)}
#researcherTable{width:100%;border-collapse:collapse;font-size:13px}
#researcherTable th{background:#f8fafc;padding:10px 12px;text-align:left;cursor:pointer;
  user-select:none;white-space:nowrap;border-bottom:2px solid var(--border);
  font-weight:600;font-size:11px;color:var(--text2);text-transform:uppercase;letter-spacing:.5px}
#researcherTable th:hover{background:#f1f5f9;color:var(--accent)}
#researcherTable th::after{content:' ↕';opacity:.3;font-size:10px}
#researcherTable td{padding:10px 12px;border-bottom:1px solid #f1f5f9;vertical-align:top}
#researcherTable tr:hover td{background:#fafbff}
.table-link{color:var(--accent);text-decoration:none;font-weight:500}
.table-link:hover{text-decoration:underline}

/* Badges */
.badge{display:inline-block;padding:2px 9px;border-radius:20px;font-size:11px;font-weight:600;letter-spacing:.2px}
.badge-high{background:#dcfce7;color:#15803d}
.badge-medium{background:#fef9c3;color:#a16207}
.badge-low{background:#fee2e2;color:#b91c1c}
.badge-internship-only{background:#f3e8ff;color:#7c3aed}
.badge-type-faculty{background:#eef2ff;color:#4338ca}
.badge-type-industry{background:#fffbeb;color:#b45309}
.priority-dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:5px;vertical-align:middle}
.priority-high{background:#ef4444}
.priority-medium{background:#f59e0b}
.priority-low{background:#94a3b8}

/* ── Map drawer ── */
#drawerOverlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:9998;
  backdrop-filter:blur(2px)}
#drawerOverlay.open{display:block}
#instDrawer{position:fixed;top:0;right:-440px;width:420px;height:100vh;
  background:#0f172a;border-left:1px solid #1e293b;
  box-shadow:-12px 0 40px rgba(0,0,0,.6);z-index:9999;
  transition:right .32s cubic-bezier(.4,0,.2,1);
  display:flex;flex-direction:column;font-family:'Inter',sans-serif;overflow:hidden}
#instDrawer.open{right:0}
#drawerHeader{padding:20px 20px 16px;border-bottom:1px solid #1e293b;
  display:flex;align-items:center;justify-content:space-between;flex-shrink:0}
#drawerTitle{font-size:15px;font-weight:600;color:#f1f5f9;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
#drawerClose{background:none;border:none;color:#64748b;cursor:pointer;
  font-size:22px;line-height:1;padding:2px 8px;border-radius:6px;transition:background .15s,color .15s}
#drawerClose:hover{background:#1e293b;color:#f1f5f9}
#drawerBody{flex:1;overflow-y:auto;padding:16px;
  scrollbar-width:thin;scrollbar-color:#334155 #0f172a}
#drawerBody::-webkit-scrollbar{width:4px}
#drawerBody::-webkit-scrollbar-track{background:#0f172a}
#drawerBody::-webkit-scrollbar-thumb{background:#334155;border-radius:3px}

/* Researcher mini-cards */
.r-card{background:#1e293b;border:1px solid #334155;border-radius:10px;
  padding:14px 16px;margin-bottom:12px;transition:border-color .15s,transform .15s}
.r-card:hover{border-color:#6366f1;transform:translateX(-2px)}
.r-card-top{display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:8px}
.r-name{font-size:14px;font-weight:600;color:#f1f5f9;line-height:1.3}
.r-pos{font-size:12px;color:#94a3b8;margin-top:2px}
.r-open{display:inline-block;padding:2px 7px;border-radius:10px;font-size:10px;font-weight:600;
  background:#052e16;color:#4ade80;border:1px solid #166534;flex-shrink:0;margin-left:8px}
.r-chance{display:inline-block;padding:2px 9px;border-radius:10px;font-size:11px;font-weight:600;margin-bottom:10px}
.r-chance-high{background:#052e16;color:#4ade80;border:1px solid #166534}
.r-chance-medium{background:#451a03;color:#fb923c;border:1px solid #92400e}
.r-chance-low{background:#3f1d1d;color:#f87171;border:1px solid #7f1d1d}
.r-chance-internship-only{background:#2e1065;color:#c084fc;border:1px solid #6b21a8}
.r-tags{display:flex;flex-wrap:wrap;gap:5px;margin:8px 0 10px}
.r-tag{padding:2px 8px;border-radius:12px;font-size:11px;font-weight:500;
  background:#312e81;color:#c7d2fe;border:1px solid #3730a3}
.r-link{display:inline-flex;align-items:center;gap:6px;color:#818cf8;
  font-size:12px;font-weight:500;text-decoration:none;
  padding:6px 14px;border:1px solid #3730a3;border-radius:8px;
  background:rgba(99,102,241,.08);transition:background .15s,border-color .15s}
.r-link:hover{background:rgba(99,102,241,.2);border-color:#6366f1;color:#a5b4fc}
.r-no-link{font-size:12px;color:#475569}
"""

    # ---------- i18n ----------
    LANG_JS = r"""
const LANG = {
  en: {
    'title':            'AI4DB Research Teams Tracker',
    'subtitle':         'LLM + Database · NL2SQL · Data Agents — PhD / Internship Target List',
    'meta-tag':         'PhD / Internship',
    'total-label':      'Total Researchers',
    'faculty-label':    'Faculty',
    'industry-label':   'Industry Teams',
    'priority-label':   'High Priority',
    'tab-overview':     'Overview',
    'tab-map':          'World Map',
    'tab-institutions': 'Institutions',
    'tab-tags':         'Research Tags',
    'tab-kanban':       'Application Status',
    'tab-directory':    'Directory',
    'chart-region':     'By Region',
    'chart-type':       'Faculty vs Industry',
    'chart-map':        'Geographic Distribution',
    'chart-inst':       'Researchers per Institution',
    'chart-tags':       'Research Tags',
    'chart-kanban':     'Application Pipeline',
    'filter-region-all':   'All Regions',
    'filter-type-all':     'All Types',
    'filter-priority-all': 'All Priorities',
    'filter-tag-all':      'All Tags',
    'filter-search':       'Search name…',
    'link-text':    'Link',
    'name-col':     'Name',       'type-col':    'Type',
    'inst-col':     'Institution','country-col': 'Country',
    'region-col':   'Region',     'pos-col':     'Position',
    'focus-col':    'Research Focus','tags-col':  'Tags',
    'chance-col':   'Admission',  'status-col':  'Status',
    'pri-col':      'Priority',   'link-col':    'Homepage',
  },
  zh: {
    'title':            'AI4DB 研究团队追踪',
    'subtitle':         'LLM + 数据库 · NL2SQL · 数据智能体 — 博士申请 / 实习目标列表',
    'meta-tag':         '博士 / 实习',
    'total-label':      '学者总数',
    'faculty-label':    '学术界',
    'industry-label':   '工业界',
    'priority-label':   '高优先级',
    'tab-overview':     '概览',
    'tab-map':          '世界地图',
    'tab-institutions': '机构分布',
    'tab-tags':         '研究方向',
    'tab-kanban':       '申请状态',
    'tab-directory':    '完整名录',
    'chart-region':     '地区分布',
    'chart-type':       '学术 vs 工业',
    'chart-map':        '地理分布',
    'chart-inst':       '各机构学者数',
    'chart-tags':       '研究方向分布',
    'chart-kanban':     '申请漏斗',
    'filter-region-all':   '全部地区',
    'filter-type-all':     '全部类型',
    'filter-priority-all': '全部优先级',
    'filter-tag-all':      '全部标签',
    'filter-search':       '搜索姓名…',
    'link-text':    '主页',
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
}
function toggleLang() { applyLang(currentLang==='en' ? 'zh' : 'en'); }

/* Tabs */
function showTab(idx) {
  document.querySelectorAll('.tab-content').forEach((el,i) => el.classList.toggle('active', i===idx));
  document.querySelectorAll('.tab-btn').forEach((el,i) => el.classList.toggle('active', i===idx));
  if (idx < 5) window.dispatchEvent(new Event('resize'));
  if (idx === 1) setTimeout(attachMapClick, 200);
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

/* ── Drawer ── */
function openDrawer(instKey) {
  const data = RESEARCHER_MAP[instKey];
  if (!data) return;
  document.getElementById('drawerTitle').textContent = data.display_name;
  const body = document.getElementById('drawerBody');
  body.innerHTML = '';
  data.researchers.forEach(r => {
    const chClass = 'r-chance-' + (r.admission_chance||'medium').replace(/\s/g,'-');
    const tagsHtml = (r.tags||[]).map(t=>`<span class="r-tag">${t}</span>`).join('');
    const openBadge = r.taking_students ? '<span class="r-open">Open</span>' : '';
    const linkBtn = r.homepage
      ? `<a href="${r.homepage}" target="_blank" rel="noopener" class="r-link">
           <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
             <path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6"/>
             <polyline points="15 3 21 3 21 9"/>
             <line x1="10" y1="14" x2="21" y2="3"/>
           </svg>
           Homepage
         </a>`
      : '<span class="r-no-link">No homepage listed</span>';
    body.innerHTML += `
      <div class="r-card">
        <div class="r-card-top">
          <div><div class="r-name">${r.name}</div><div class="r-pos">${r.position||''}</div></div>
          ${openBadge}
        </div>
        <span class="r-chance ${chClass}">${r.admission_chance||''}</span>
        <div class="r-tags">${tagsHtml}</div>
        ${linkBtn}
      </div>`;
  });
  document.getElementById('instDrawer').classList.add('open');
  document.getElementById('drawerOverlay').classList.add('open');
}
function closeDrawer() {
  document.getElementById('instDrawer').classList.remove('open');
  document.getElementById('drawerOverlay').classList.remove('open');
}
document.addEventListener('keydown', e => { if (e.key==='Escape') closeDrawer(); });

function attachMapClick() {
  const mapDiv = document.querySelector('#tab-1 .js-plotly-plot');
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
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
{plotly_js}
<style>{CSS}</style>
</head>
<body>

<div class="header">
  <div class="header-left">
    <h1 data-i18n="title">AI4DB Research Teams Tracker</h1>
    <p data-i18n="subtitle">LLM + Database · NL2SQL · Data Agents</p>
  </div>
  <div class="header-right">
    <span class="meta-tag" data-i18n="meta-tag">PhD / Internship</span>
    <button class="lang-toggle" onclick="toggleLang()">中文</button>
  </div>
</div>

{sc}

<div class="tabs">
  <button class="tab-btn active" onclick="showTab(0)" data-i18n="tab-overview">Overview</button>
  <button class="tab-btn"        onclick="showTab(1)" data-i18n="tab-map">World Map</button>
  <button class="tab-btn"        onclick="showTab(2)" data-i18n="tab-institutions">Institutions</button>
  <button class="tab-btn"        onclick="showTab(3)" data-i18n="tab-tags">Research Tags</button>
  <button class="tab-btn"        onclick="showTab(4)" data-i18n="tab-kanban">Application Status</button>
  <button class="tab-btn"        onclick="showTab(5)" data-i18n="tab-directory">Directory</button>
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
  <div class="card" style="background:#0f172a;border-color:#1e293b;padding:16px 16px 0">
    <div class="card-title" data-i18n="chart-map" style="color:#94a3b8">Geographic Distribution</div>
    <p class="card-hint" style="color:#475569">● Click any bubble to open researcher profiles</p>
    {map_div}
  </div>
</div>

<div class="tab-content" id="tab-2">
  <div class="card">
    <div class="card-title" data-i18n="chart-inst">Researchers per Institution</div>
    {inst_div}
  </div>
</div>

<div class="tab-content" id="tab-3">
  <div class="card">
    <div class="card-title" data-i18n="chart-tags">Research Tags</div>
    {tags_div}
  </div>
</div>

<div class="tab-content" id="tab-4">
  <div class="card">
    <div class="card-title" data-i18n="chart-kanban">Application Pipeline</div>
    {kanban_div}
  </div>
</div>

<div class="tab-content" id="tab-5">
  {filters_html}
  <div class="table-wrap">{table_html}</div>
</div>

<!-- Drawer -->
<div id="drawerOverlay" onclick="closeDrawer()"></div>
<div id="instDrawer">
  <div id="drawerHeader">
    <div id="drawerTitle"></div>
    <button id="drawerClose" onclick="closeDrawer()">×</button>
  </div>
  <div id="drawerBody"></div>
</div>

<script>{JS}</script>
</body>
</html>"""


# ── Main ──────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--offline', action='store_true')
    args = parser.parse_args()

    data = load_researchers()
    institutions = load_institutions()
    df = build_df(data, institutions)

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
    html = assemble(df, figs, table_html, filters_html, offline=args.offline)

    with open(HTML_PATH, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"  Dashboard: {HTML_PATH}")

    with open(INDEX_PATH, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"  Index: {INDEX_PATH}")


if __name__ == '__main__':
    main()
