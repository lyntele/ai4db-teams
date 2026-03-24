#!/usr/bin/env python3
"""Generate a polished, bilingual (EN/ZH) dashboard from researchers.json."""

import argparse
import json
import os

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from utils import load_researchers, load_institutions

OUT_DIR = os.path.join(os.path.dirname(__file__), '..')
HTML_PATH = os.path.join(OUT_DIR, 'dashboard.html')
CSV_PATH  = os.path.join(OUT_DIR, 'data', 'researchers.csv')

# ── Colour palette ────────────────────────────────────────────
REGION_COLORS  = {'Asia':'#6366f1','Europe':'#0ea5e9','North America':'#10b981','Oceania':'#f59e0b'}
TYPE_COLORS    = {'faculty':'#6366f1','industry':'#f59e0b'}
CHANCE_COLORS  = {'high':'#10b981','medium':'#f59e0b','low':'#ef4444','internship-only':'#a855f7'}
PRIORITY_COLORS= {'high':'#ef4444','medium':'#f59e0b','low':'#94a3b8'}

PLOTLY_TEMPLATE = dict(
    layout=dict(
        font=dict(family="Inter, -apple-system, sans-serif", size=13, color="#334155"),
        paper_bgcolor="white", plot_bgcolor="white",
        colorway=["#6366f1","#0ea5e9","#10b981","#f59e0b","#ef4444","#a855f7","#ec4899"],
        xaxis=dict(gridcolor="#f1f5f9", linecolor="#e2e8f0"),
        yaxis=dict(gridcolor="#f1f5f9", linecolor="#e2e8f0"),
        legend=dict(bgcolor="rgba(255,255,255,0.9)", bordercolor="#e2e8f0", borderwidth=1),
        margin=dict(l=16, r=16, t=48, b=16),
    )
)


# ── Data ──────────────────────────────────────────────────────

def build_df(data, institutions):
    rows = []
    for r in data['researchers']:
        inst_key = r.get('institution','')
        inst = institutions.get(inst_key, {})
        rows.append({
            **r,
            'inst_display': inst.get('display_name', inst_key),
            'lat': inst.get('lat', 0),
            'lon': inst.get('lon', 0),
            'qs_rank': inst.get('qs_rank'),
            'inst_type': inst.get('type',''),
            'tags_str': ', '.join(r.get('tags',[])),
            'focus_str': ', '.join(r.get('research_focus',[])),
        })
    return pd.DataFrame(rows)


# ── Charts ────────────────────────────────────────────────────

def chart_map(df):
    agg = df.groupby(['institution','inst_display','lat','lon','type']).agg(
        count=('id','size'),
        names=('name', lambda x: '<br>'.join(x)),
    ).reset_index()
    fig = px.scatter_geo(
        agg, lat='lat', lon='lon', size='count', color='type',
        color_discrete_map=TYPE_COLORS,
        hover_name='inst_display',
        hover_data={'names':True,'count':True,'lat':False,'lon':False,'type':False},
        projection='natural earth', size_max=28,
    )
    fig.update_geos(
        showcountries=True, countrycolor="#e2e8f0",
        showcoastlines=True, coastlinecolor="#cbd5e1",
        showland=True, landcolor="#f8fafc",
        showocean=True, oceancolor="#eff6ff",
        showlakes=True, lakecolor="#eff6ff",
    )
    fig.update_layout(height=560, **PLOTLY_TEMPLATE['layout'])
    return fig


def chart_institution(df):
    agg = df.groupby(['inst_display','region']).size().reset_index(name='count')
    agg = agg.sort_values('count', ascending=True)
    fig = px.bar(agg, x='count', y='inst_display', color='region',
                 color_discrete_map=REGION_COLORS, orientation='h',
                 labels={'inst_display':'','count':'Count'})
    fig.update_layout(height=max(380, len(agg)*24),
                      margin=dict(l=180,r=16,t=24,b=16),
                      **{k:v for k,v in PLOTLY_TEMPLATE['layout'].items() if k not in ('margin',)})
    return fig


def chart_tags(df):
    records = []
    for _, row in df.iterrows():
        for tag in (row.get('tags') or []):
            records.append({'tag':tag,'chance':row.get('admission_chance','medium')})
    tdf = pd.DataFrame(records)
    if tdf.empty:
        return go.Figure()
    agg = tdf.groupby(['tag','chance']).size().reset_index(name='count')
    fig = px.bar(agg, x='tag', y='count', color='chance',
                 color_discrete_map=CHANCE_COLORS, barmode='stack',
                 labels={'tag':'','count':'Count'})
    fig.update_layout(height=420, **PLOTLY_TEMPLATE['layout'])
    return fig


def chart_kanban(df):
    order = ['considering','shortlisted','contacted','awaiting-reply',
             'applied','accepted','rejected','not-applicable']
    agg = df.groupby(['application_status','priority']).size().reset_index(name='count')
    agg['application_status'] = pd.Categorical(agg['application_status'], categories=order, ordered=True)
    agg = agg.sort_values('application_status')
    fig = px.bar(agg, x='application_status', y='count', color='priority',
                 color_discrete_map=PRIORITY_COLORS, barmode='stack',
                 labels={'application_status':'','count':'Count'})
    fig.update_layout(height=420, **PLOTLY_TEMPLATE['layout'])
    return fig


def chart_region_donut(df):
    agg = df.groupby('region').size().reset_index(name='count')
    fig = px.pie(agg, names='region', values='count',
                 color='region', color_discrete_map=REGION_COLORS, hole=0.55)
    fig.update_traces(textinfo='percent+label', hovertemplate='%{label}: %{value}<extra></extra>')
    fig.update_layout(height=320, showlegend=False,
                      margin=dict(l=16,r=16,t=24,b=16),
                      **{k:v for k,v in PLOTLY_TEMPLATE['layout'].items() if k not in ('margin',)})
    return fig


def chart_type_donut(df):
    agg = df.groupby('type').size().reset_index(name='count')
    fig = px.pie(agg, names='type', values='count',
                 color='type', color_discrete_map=TYPE_COLORS, hole=0.55)
    fig.update_traces(textinfo='percent+label', hovertemplate='%{label}: %{value}<extra></extra>')
    fig.update_layout(height=320, showlegend=False,
                      margin=dict(l=16,r=16,t=24,b=16),
                      **{k:v for k,v in PLOTLY_TEMPLATE['layout'].items() if k not in ('margin',)})
    return fig


# ── HTML components ───────────────────────────────────────────

def to_div(fig):
    return fig.to_html(full_html=False, include_plotlyjs=False, config={'responsive':True})


def stats_cards(df):
    total     = len(df)
    faculty   = (df['type']=='faculty').sum()
    industry  = (df['type']=='industry').sum()
    high_pri  = (df['priority']=='high').sum()
    cards = [
        ('total',    total,    'total-label',    '🎓'),
        ('faculty',  faculty,  'faculty-label',  '🏫'),
        ('industry', industry, 'industry-label', '🏢'),
        ('high-pri', high_pri, 'priority-label', '⭐'),
    ]
    html = '<div class="stats-row">'
    for key, val, label_key, icon in cards:
        html += f'''
      <div class="stat-card">
        <div class="stat-icon">{icon}</div>
        <div class="stat-body">
          <div class="stat-value">{val}</div>
          <div class="stat-label" data-i18n="{label_key}"></div>
        </div>
      </div>'''
    html += '</div>'
    return html


def build_table(df):
    cols = [
        ('name-col',    'name'),
        ('type-col',    'type'),
        ('inst-col',    'inst_display'),
        ('country-col', 'country'),
        ('region-col',  'region'),
        ('pos-col',     'position'),
        ('focus-col',   'focus_str'),
        ('tags-col',    'tags_str'),
        ('chance-col',  'admission_chance'),
        ('status-col',  'application_status'),
        ('pri-col',     'priority'),
        ('link-col',    'homepage'),
    ]
    rows_html = []
    for _, r in df.iterrows():
        cells = []
        for i18n_key, col in cols:
            val = r.get(col) or ''
            if col == 'homepage' and val:
                cell = f'<a href="{val}" target="_blank" class="table-link" data-i18n-attr="link-text"></a>'
            elif col == 'admission_chance' and val:
                cell = f'<span class="badge badge-{val}">{val}</span>'
            elif col == 'type' and val:
                cell = f'<span class="badge badge-type-{val}">{val}</span>'
            elif col == 'priority' and val:
                cell = f'<span class="priority-dot priority-{val}"></span>{val}'
            else:
                cell = str(val)
            cells.append(f'<td data-col="{col}">{cell}</td>')
        rows_html.append('<tr>' + ''.join(cells) + '</tr>')

    headers = ''.join(
        f'<th data-col="{col}" data-i18n="{key}" onclick="sortTable(this)"></th>'
        for key, col in cols
    )
    return f'''
    <table id="researcherTable">
      <thead><tr>{headers}</tr></thead>
      <tbody>{''.join(rows_html)}</tbody>
    </table>'''


def build_filters(df):
    regions   = sorted(df['region'].dropna().unique())
    types     = sorted(df['type'].dropna().unique())
    priorities= sorted(df['priority'].dropna().unique())
    all_tags  = sorted({t for tags in df['tags'] if isinstance(tags,list) for t in tags})

    def sel(fid, key, vals, i18n_prefix):
        opts = f'<option value="" data-i18n="{i18n_prefix}-all"></option>'
        for v in vals:
            opts += f'<option value="{v}">{v}</option>'
        return f'<select id="{fid}" onchange="filterTable()">{opts}</select>'

    return f'''
    <div class="filter-bar">
      {sel("fRegion",   "region",   regions,    "filter-region")}
      {sel("fType",     "type",     types,       "filter-type")}
      {sel("fPriority", "priority", priorities, "filter-priority")}
      {sel("fTag",      "tag",      all_tags,    "filter-tag")}
      <input id="fSearch" type="text" class="filter-input"
             data-i18n-placeholder="filter-search" oninput="filterTable()">
    </div>'''


# ── Full HTML assembly ─────────────────────────────────────────

def assemble(df, figs, table_html, filters_html, offline=False):
    plotly_js = '<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>'
    if offline:
        import plotly
        plotly_js = f'<script>{plotly.offline.get_plotlyjs()}</script>'

    map_div, inst_div, tags_div, kanban_div, region_div, type_div = [to_div(f) for f in figs]
    sc = stats_cards(df)

    return f"""<!DOCTYPE html>
<html lang="en" data-lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AI4DB Research Teams Tracker</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
{plotly_js}
<style>
:root{{
  --bg:#f8fafc; --card:#ffffff; --border:#e2e8f0; --text:#0f172a;
  --text2:#64748b; --accent:#6366f1; --accent2:#4f46e5;
  --sidebar:#0f172a;
  --shadow:0 1px 3px rgba(0,0,0,.06),0 4px 16px rgba(0,0,0,.04);
  --radius:12px;
}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'Inter',sans-serif;background:var(--bg);color:var(--text);min-height:100vh;display:flex;flex-direction:column}}

/* ── Header ── */
.header{{background:linear-gradient(135deg,#0f172a 0%,#1e1b4b 50%,#312e81 100%);
  color:#fff;padding:20px 32px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px}}
.header-left h1{{font-size:22px;font-weight:700;letter-spacing:-.3px}}
.header-left p{{font-size:13px;opacity:.7;margin-top:3px}}
.header-right{{display:flex;align-items:center;gap:12px}}
.lang-toggle{{background:rgba(255,255,255,.12);border:1px solid rgba(255,255,255,.2);
  color:#fff;padding:6px 16px;border-radius:20px;cursor:pointer;font-size:13px;font-weight:500;
  transition:background .2s}}
.lang-toggle:hover{{background:rgba(255,255,255,.22)}}
.meta-tag{{background:rgba(99,102,241,.35);border:1px solid rgba(99,102,241,.5);
  color:#c7d2fe;padding:4px 12px;border-radius:20px;font-size:12px}}

/* ── Stats ── */
.stats-row{{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;padding:20px 28px 0}}
.stat-card{{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);
  padding:16px 20px;display:flex;align-items:center;gap:14px;box-shadow:var(--shadow)}}
.stat-icon{{font-size:26px}}
.stat-value{{font-size:28px;font-weight:700;color:var(--accent);line-height:1}}
.stat-label{{font-size:12px;color:var(--text2);margin-top:3px;font-weight:500}}

/* ── Tabs ── */
.tabs{{display:flex;gap:0;padding:20px 28px 0;overflow-x:auto}}
.tab-btn{{padding:10px 20px;border:none;background:none;cursor:pointer;font-size:13px;font-weight:500;
  color:var(--text2);border-bottom:2px solid transparent;transition:all .18s;white-space:nowrap;
  font-family:'Inter',sans-serif}}
.tab-btn:hover{{color:var(--accent)}}
.tab-btn.active{{color:var(--accent);border-bottom-color:var(--accent)}}

/* ── Content ── */
.tab-content{{display:none;padding:16px 28px 28px;animation:fadeIn .2s ease}}
.tab-content.active{{display:block}}
@keyframes fadeIn{{from{{opacity:0;transform:translateY(4px)}}to{{opacity:1;transform:translateY(0)}}}}
.card{{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);
  padding:20px;box-shadow:var(--shadow);margin-bottom:16px}}
.card-title{{font-size:14px;font-weight:600;color:var(--text2);margin-bottom:14px;
  text-transform:uppercase;letter-spacing:.5px}}
.chart-grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px}}

/* ── Filters ── */
.filter-bar{{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:16px;
  padding:14px;background:var(--card);border:1px solid var(--border);border-radius:var(--radius);
  box-shadow:var(--shadow)}}
.filter-bar select,.filter-input{{
  padding:7px 12px;border:1px solid var(--border);border-radius:8px;font-size:13px;
  font-family:'Inter',sans-serif;background:white;color:var(--text);outline:none;transition:border .15s}}
.filter-bar select:focus,.filter-input:focus{{border-color:var(--accent)}}
.filter-input{{width:190px}}

/* ── Table ── */
#researcherTable{{width:100%;border-collapse:collapse;font-size:13px}}
#researcherTable th{{background:#f8fafc;padding:10px 12px;text-align:left;
  cursor:pointer;user-select:none;white-space:nowrap;border-bottom:2px solid var(--border);
  font-weight:600;font-size:12px;color:var(--text2);text-transform:uppercase;letter-spacing:.4px}}
#researcherTable th:hover{{background:#f1f5f9;color:var(--accent)}}
#researcherTable th::after{{content:' ↕';opacity:.35;font-size:10px}}
#researcherTable td{{padding:10px 12px;border-bottom:1px solid #f1f5f9;vertical-align:top;color:var(--text)}}
#researcherTable tr:hover td{{background:#fafbff}}
.table-link{{color:var(--accent);text-decoration:none;font-weight:500}}
.table-link::before{{content:'↗ '}}
.table-link:hover{{text-decoration:underline}}
.table-wrap{{overflow-x:auto;border-radius:var(--radius);border:1px solid var(--border);box-shadow:var(--shadow)}}

/* ── Badges ── */
.badge{{display:inline-block;padding:2px 9px;border-radius:20px;font-size:11px;font-weight:600;
  letter-spacing:.2px}}
.badge-high{{background:#dcfce7;color:#15803d}}
.badge-medium{{background:#fef9c3;color:#a16207}}
.badge-low{{background:#fee2e2;color:#b91c1c}}
.badge-internship-only{{background:#f3e8ff;color:#7c3aed}}
.badge-type-faculty{{background:#eef2ff;color:#4338ca}}
.badge-type-industry{{background:#fffbeb;color:#b45309}}
.priority-dot{{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:5px;vertical-align:middle}}
.priority-high{{background:#ef4444}}
.priority-medium{{background:#f59e0b}}
.priority-low{{background:#94a3b8}}
</style>
</head>
<body>

<!-- Header -->
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

<!-- Stats -->
{sc}

<!-- Tabs -->
<div class="tabs">
  <button class="tab-btn active" onclick="showTab(0)" data-i18n="tab-overview">Overview</button>
  <button class="tab-btn"        onclick="showTab(1)" data-i18n="tab-map">World Map</button>
  <button class="tab-btn"        onclick="showTab(2)" data-i18n="tab-institutions">Institutions</button>
  <button class="tab-btn"        onclick="showTab(3)" data-i18n="tab-tags">Research Tags</button>
  <button class="tab-btn"        onclick="showTab(4)" data-i18n="tab-kanban">Application Status</button>
  <button class="tab-btn"        onclick="showTab(5)" data-i18n="tab-directory">Directory</button>
</div>

<!-- Tab 0: Overview -->
<div class="tab-content active" id="tab-0">
  <div class="chart-grid">
    <div class="card">
      <div class="card-title" data-i18n="chart-region-title">By Region</div>
      {region_div}
    </div>
    <div class="card">
      <div class="card-title" data-i18n="chart-type-title">Faculty vs Industry</div>
      {type_div}
    </div>
  </div>
</div>

<!-- Tab 1: World Map -->
<div class="tab-content" id="tab-1">
  <div class="card">
    <div class="card-title" data-i18n="chart-map-title">Geographic Distribution</div>
    {map_div}
  </div>
</div>

<!-- Tab 2: Institutions -->
<div class="tab-content" id="tab-2">
  <div class="card">
    <div class="card-title" data-i18n="chart-inst-title">Researchers per Institution</div>
    {inst_div}
  </div>
</div>

<!-- Tab 3: Research Tags -->
<div class="tab-content" id="tab-3">
  <div class="card">
    <div class="card-title" data-i18n="chart-tags-title">Research Focus Distribution</div>
    {tags_div}
  </div>
</div>

<!-- Tab 4: Application Kanban -->
<div class="tab-content" id="tab-4">
  <div class="card">
    <div class="card-title" data-i18n="chart-kanban-title">Application Pipeline</div>
    {kanban_div}
  </div>
</div>

<!-- Tab 5: Directory -->
<div class="tab-content" id="tab-5">
  {filters_html}
  <div class="table-wrap">
    {table_html}
  </div>
</div>

<script>
// ── i18n ────────────────────────────────────────────────────────
const LANG = {{
  en: {{
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
    'chart-region-title':  'By Region',
    'chart-type-title':    'Faculty vs Industry',
    'chart-map-title':     'Geographic Distribution',
    'chart-inst-title':    'Researchers per Institution',
    'chart-tags-title':    'Research Focus Distribution',
    'chart-kanban-title':  'Application Pipeline',
    'filter-region-all':   'All Regions',
    'filter-type-all':     'All Types',
    'filter-priority-all': 'All Priorities',
    'filter-tag-all':      'All Tags',
    'filter-search':       'Search name…',
    'link-text':           'Link',
    'name-col':     'Name',       'type-col':   'Type',
    'inst-col':     'Institution','country-col':'Country',
    'region-col':   'Region',     'pos-col':    'Position',
    'focus-col':    'Research Focus','tags-col': 'Tags',
    'chance-col':   'Admission',  'status-col': 'Status',
    'pri-col':      'Priority',   'link-col':   'Homepage',
  }},
  zh: {{
    'title':            'AI4DB 研究团队追踪',
    'subtitle':         'LLM + 数据库 · NL2SQL · 数据智能体 — 博士申请 / 实习目标列表',
    'meta-tag':         '博士 / 实习',
    'total-label':      '学者总数',
    'faculty-label':    '学术界',
    'industry-label':   '工业界团队',
    'priority-label':   '高优先级',
    'tab-overview':     '概览',
    'tab-map':          '世界地图',
    'tab-institutions': '机构分布',
    'tab-tags':         '研究方向',
    'tab-kanban':       '申请状态',
    'tab-directory':    '完整名录',
    'chart-region-title':  '地区分布',
    'chart-type-title':    '学术界 vs 工业界',
    'chart-map-title':     '地理分布',
    'chart-inst-title':    '各机构学者数',
    'chart-tags-title':    '研究方向分布',
    'chart-kanban-title':  '申请漏斗',
    'filter-region-all':   '全部地区',
    'filter-type-all':     '全部类型',
    'filter-priority-all': '全部优先级',
    'filter-tag-all':      '全部标签',
    'filter-search':       '搜索姓名…',
    'link-text':           '主页',
    'name-col':     '姓名',       'type-col':   '类型',
    'inst-col':     '机构',       'country-col':'国家',
    'region-col':   '地区',       'pos-col':    '职位',
    'focus-col':    '研究方向',   'tags-col':   '标签',
    'chance-col':   '录取机会',   'status-col': '申请状态',
    'pri-col':      '优先级',     'link-col':   '主页',
  }}
}};

let currentLang = 'en';

function applyLang(lang) {{
  const t = LANG[lang];
  // data-i18n elements
  document.querySelectorAll('[data-i18n]').forEach(el => {{
    const key = el.dataset.i18n;
    if (t[key] !== undefined) el.textContent = t[key];
  }});
  // placeholder inputs
  document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {{
    const key = el.dataset.i18nPlaceholder;
    if (t[key] !== undefined) el.placeholder = t[key];
  }});
  // link text
  document.querySelectorAll('.table-link').forEach(el => {{
    el.textContent = (lang==='zh' ? '↗ 主页' : '↗ Link');
  }});
  // select first options (All X)
  document.querySelectorAll('select option[data-i18n]').forEach(el => {{
    const key = el.dataset.i18n;
    if (t[key] !== undefined) el.textContent = t[key];
  }});
  // toggle button label
  document.querySelector('.lang-toggle').textContent = lang==='en' ? '中文' : 'EN';
  document.documentElement.setAttribute('data-lang', lang);
  currentLang = lang;
}}

function toggleLang() {{
  applyLang(currentLang === 'en' ? 'zh' : 'en');
}}

// ── Tabs ────────────────────────────────────────────────────────
function showTab(idx) {{
  document.querySelectorAll('.tab-content').forEach((el, i) => {{
    el.classList.toggle('active', i===idx);
  }});
  document.querySelectorAll('.tab-btn').forEach((el, i) => {{
    el.classList.toggle('active', i===idx);
  }});
  if (idx < 5) window.dispatchEvent(new Event('resize'));
}}

// ── Table filter ─────────────────────────────────────────────────
function filterTable() {{
  const region   = (document.getElementById('fRegion')?.value   || '').toLowerCase();
  const type     = (document.getElementById('fType')?.value     || '').toLowerCase();
  const priority = (document.getElementById('fPriority')?.value || '').toLowerCase();
  const tag      = (document.getElementById('fTag')?.value      || '').toLowerCase();
  const search   = (document.getElementById('fSearch')?.value   || '').toLowerCase();
  document.querySelectorAll('#researcherTable tbody tr').forEach(row => {{
    const get = col => (row.querySelector(`td[data-col="${{col}}"]`)?.textContent||'').toLowerCase();
    let show = true;
    if (region   && get('region')           !== region)          show=false;
    if (type     && get('type').indexOf(type) === -1)            show=false;
    if (priority && get('priority').indexOf(priority) === -1)    show=false;
    if (tag      && get('tags_str').indexOf(tag)      === -1)    show=false;
    if (search   && get('name').indexOf(search)       === -1)    show=false;
    row.style.display = show ? '' : 'none';
  }});
}}

// ── Table sort ───────────────────────────────────────────────────
function sortTable(th) {{
  const col   = th.dataset.col;
  const asc   = th.dataset.sort !== 'asc';
  th.dataset.sort = asc ? 'asc' : 'desc';
  const tbody = th.closest('table').querySelector('tbody');
  Array.from(tbody.querySelectorAll('tr'))
    .sort((a,b) => {{
      const av = a.querySelector(`td[data-col="${{col}}"]`)?.textContent || '';
      const bv = b.querySelector(`td[data-col="${{col}}"]`)?.textContent || '';
      return asc ? av.localeCompare(bv) : bv.localeCompare(av);
    }})
    .forEach(r => tbody.appendChild(r));
}}

// Init
applyLang('en');
</script>
</body>
</html>"""


# ── Main ──────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--offline', action='store_true')
    args = parser.parse_args()

    data = load_researchers()
    institutions = load_institutions()
    df   = build_df(data, institutions)

    # Export CSV
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


if __name__ == '__main__':
    main()
