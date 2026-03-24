#!/usr/bin/env python3
"""Generate dashboard.html with 5 interactive tabs from researchers.json."""

import argparse
import json
import os

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from utils import load_researchers, load_institutions

OUT_DIR = os.path.join(os.path.dirname(__file__), '..')
HTML_PATH = os.path.join(OUT_DIR, 'dashboard.html')
CSV_PATH = os.path.join(OUT_DIR, 'data', 'researchers.csv')

# ── colour maps ──────────────────────────────────────────────

REGION_COLORS = {
    'Asia': '#e74c3c',
    'Europe': '#3498db',
    'North America': '#2ecc71',
    'Oceania': '#f39c12',
}
TYPE_COLORS = {'faculty': '#3498db', 'industry': '#e67e22'}
CHANCE_COLORS = {
    'high': '#27ae60', 'medium': '#f1c40f',
    'low': '#e74c3c', 'internship-only': '#9b59b6',
}
PRIORITY_COLORS = {'high': '#e74c3c', 'medium': '#f39c12', 'low': '#95a5a6'}


def build_df(data, institutions):
    rows = []
    for r in data['researchers']:
        inst_key = r.get('institution', '')
        inst = institutions.get(inst_key, {})
        rows.append({
            **r,
            'inst_display': inst.get('display_name', inst_key),
            'lat': inst.get('lat', 0),
            'lon': inst.get('lon', 0),
            'qs_rank': inst.get('qs_rank'),
            'inst_type': inst.get('type', ''),
            'tags_str': ', '.join(r.get('tags', [])),
            'focus_str': ', '.join(r.get('research_focus', [])),
        })
    return pd.DataFrame(rows)


# ── Tab 1: World Map ─────────────────────────────────────────

def fig_map(df):
    agg = df.groupby(['institution', 'inst_display', 'lat', 'lon', 'type']).agg(
        count=('id', 'size'),
        names=('name', lambda x: '<br>'.join(x)),
    ).reset_index()

    fig = px.scatter_geo(
        agg, lat='lat', lon='lon',
        size='count', color='type',
        color_discrete_map=TYPE_COLORS,
        hover_name='inst_display',
        hover_data={'names': True, 'count': True, 'lat': False, 'lon': False, 'type': False},
        projection='natural earth',
        title='Researcher Geographic Distribution',
        size_max=30,
    )
    fig.update_layout(height=600, margin=dict(l=0, r=0, t=40, b=0))
    return fig


# ── Tab 2: Institution Bar ───────────────────────────────────

def fig_institution(df):
    agg = df.groupby(['inst_display', 'region']).size().reset_index(name='count')
    agg = agg.sort_values('count', ascending=True)
    fig = px.bar(
        agg, x='count', y='inst_display', color='region',
        color_discrete_map=REGION_COLORS,
        orientation='h',
        title='Researchers per Institution',
        labels={'inst_display': '', 'count': 'Count'},
    )
    fig.update_layout(height=max(400, len(agg) * 22), margin=dict(l=200))
    return fig


# ── Tab 3: Research Tags ─────────────────────────────────────

def fig_tags(df):
    records = []
    for _, row in df.iterrows():
        for tag in row.get('tags', []) or []:
            records.append({'tag': tag, 'chance': row.get('admission_chance', 'medium')})
    tdf = pd.DataFrame(records)
    if tdf.empty:
        return go.Figure()
    agg = tdf.groupby(['tag', 'chance']).size().reset_index(name='count')
    fig = px.bar(
        agg, x='tag', y='count', color='chance',
        color_discrete_map=CHANCE_COLORS,
        barmode='stack',
        title='Research Tags Distribution',
        labels={'tag': 'Tag', 'count': 'Count'},
    )
    fig.update_layout(height=500)
    return fig


# ── Tab 4: Application Kanban ────────────────────────────────

def fig_kanban(df):
    status_order = [
        'considering', 'shortlisted', 'contacted', 'awaiting-reply',
        'applied', 'accepted', 'rejected', 'not-applicable',
    ]
    agg = df.groupby(['application_status', 'priority']).size().reset_index(name='count')
    agg['application_status'] = pd.Categorical(agg['application_status'], categories=status_order, ordered=True)
    agg = agg.sort_values('application_status')
    fig = px.bar(
        agg, x='application_status', y='count', color='priority',
        color_discrete_map=PRIORITY_COLORS,
        barmode='stack',
        title='Application Status Kanban',
        labels={'application_status': 'Status', 'count': 'Count'},
    )
    fig.update_layout(height=450)
    return fig


# ── Tab 5: Full Table (HTML) ─────────────────────────────────

def build_table_html(df):
    cols = [
        ('Name', 'name'), ('Type', 'type'), ('Institution', 'inst_display'),
        ('Country', 'country'), ('Region', 'region'), ('Position', 'position'),
        ('Research Focus', 'focus_str'), ('Tags', 'tags_str'),
        ('Chance', 'admission_chance'), ('Status', 'application_status'),
        ('Priority', 'priority'), ('Homepage', 'homepage'), ('Notes', 'notes'),
    ]

    chance_badges = {
        'high': '#27ae60', 'medium': '#f1c40f', 'low': '#e74c3c', 'internship-only': '#9b59b6',
    }

    rows_html = []
    for _, row in df.iterrows():
        cells = []
        for header, key in cols:
            val = row.get(key, '')
            if val is None:
                val = ''
            if key == 'homepage' and val:
                val = f'<a href="{val}" target="_blank">Link</a>'
            elif key == 'admission_chance' and val in chance_badges:
                c = chance_badges[val]
                val = f'<span style="background:{c};color:#fff;padding:2px 8px;border-radius:4px;font-size:12px">{val}</span>'
            elif key == 'priority':
                c = PRIORITY_COLORS.get(val, '#999')
                val = f'<span style="color:{c};font-weight:bold">{val}</span>'
            cells.append(f'<td>{val}</td>')
        rows_html.append('<tr>' + ''.join(cells) + '</tr>')

    headers = ''.join(f'<th>{h}</th>' for h, _ in cols)
    return f"""
    <div style="overflow-x:auto">
    <table id="researcherTable" class="sortable">
      <thead><tr>{headers}</tr></thead>
      <tbody>{''.join(rows_html)}</tbody>
    </table>
    </div>"""


# ── Filters HTML ─────────────────────────────────────────────

def build_filters_html(df):
    regions = sorted(df['region'].dropna().unique())
    types = sorted(df['type'].dropna().unique())
    priorities = sorted(df['priority'].dropna().unique())

    all_tags = set()
    for tags in df['tags']:
        if isinstance(tags, list):
            all_tags.update(tags)
    tags = sorted(all_tags)

    def options(values, name):
        opts = f'<option value="">All {name}</option>'
        for v in values:
            opts += f'<option value="{v}">{v}</option>'
        return opts

    return f"""
    <div class="filters">
      <select id="filterRegion" onchange="filterTable()">{options(regions, 'Regions')}</select>
      <select id="filterType" onchange="filterTable()">{options(types, 'Types')}</select>
      <select id="filterPriority" onchange="filterTable()">{options(priorities, 'Priorities')}</select>
      <select id="filterTag" onchange="filterTable()">{options(tags, 'Tags')}</select>
      <input type="text" id="filterSearch" placeholder="Search name..." oninput="filterTable()">
    </div>"""


# ── Assemble HTML ────────────────────────────────────────────

def assemble_html(figs, table_html, filters_html, offline=False):
    plotly_js = '<script src="https://cdn.plot.ly/plotly-2.32.0.min.js"></script>'
    if offline:
        import plotly
        plotly_js = f'<script>{plotly.offline.get_plotlyjs()}</script>'

    divs = []
    tab_names = ['World Map', 'Institutions', 'Research Tags', 'Application Kanban', 'Full Table']
    for i, fig in enumerate(figs):
        div_html = fig.to_html(full_html=False, include_plotlyjs=False)
        divs.append(div_html)

    tabs_buttons = ''
    tabs_content = ''
    for i, name in enumerate(tab_names):
        active = 'active' if i == 0 else ''
        display = 'block' if i == 0 else 'none'
        tabs_buttons += f'<button class="tab-btn {active}" onclick="showTab({i})">{name}</button>'

        if i < 4:
            tabs_content += f'<div class="tab-content" id="tab-{i}" style="display:{display}">{divs[i]}</div>'
        else:
            tabs_content += f'<div class="tab-content" id="tab-{i}" style="display:{display}">{filters_html}{table_html}</div>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI4DB Research Teams Tracker</title>
{plotly_js}
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f5f6fa; color: #333; }}
  .header {{ background: linear-gradient(135deg, #2c3e50, #3498db); color: #fff; padding: 24px 32px; }}
  .header h1 {{ font-size: 24px; margin-bottom: 4px; }}
  .header p {{ font-size: 14px; opacity: 0.85; }}
  .tabs {{ display: flex; gap: 0; background: #fff; border-bottom: 2px solid #e0e0e0; padding: 0 16px; }}
  .tab-btn {{ padding: 12px 24px; border: none; background: none; cursor: pointer; font-size: 14px; font-weight: 500; color: #666; border-bottom: 3px solid transparent; transition: all .2s; }}
  .tab-btn:hover {{ color: #3498db; }}
  .tab-btn.active {{ color: #3498db; border-bottom-color: #3498db; }}
  .tab-content {{ padding: 16px; background: #fff; margin: 16px; border-radius: 8px; box-shadow: 0 1px 4px rgba(0,0,0,0.08); }}
  .filters {{ display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 16px; padding: 12px; background: #f8f9fa; border-radius: 6px; }}
  .filters select, .filters input {{ padding: 8px 12px; border: 1px solid #ddd; border-radius: 4px; font-size: 13px; }}
  .filters input {{ width: 200px; }}
  table.sortable {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  table.sortable th {{ background: #f0f0f0; padding: 10px 8px; text-align: left; cursor: pointer; user-select: none; white-space: nowrap; border-bottom: 2px solid #ddd; }}
  table.sortable th:hover {{ background: #e0e0e0; }}
  table.sortable td {{ padding: 8px; border-bottom: 1px solid #eee; vertical-align: top; }}
  table.sortable tr:hover {{ background: #f8f9fa; }}
  table.sortable a {{ color: #3498db; text-decoration: none; }}
  table.sortable a:hover {{ text-decoration: underline; }}
</style>
</head>
<body>
<div class="header">
  <h1>AI4DB Research Teams Tracker</h1>
  <p>LLM + Database &middot; NL2SQL &middot; Data Agents &mdash; PhD / Internship Target List</p>
</div>
<div class="tabs">{tabs_buttons}</div>
{tabs_content}

<script>
function showTab(idx) {{
  document.querySelectorAll('.tab-content').forEach((el, i) => {{
    el.style.display = i === idx ? 'block' : 'none';
  }});
  document.querySelectorAll('.tab-btn').forEach((el, i) => {{
    el.classList.toggle('active', i === idx);
  }});
  // trigger plotly resize for chart tabs
  if (idx < 4) {{ window.dispatchEvent(new Event('resize')); }}
}}

function filterTable() {{
  const region = document.getElementById('filterRegion').value.toLowerCase();
  const type = document.getElementById('filterType').value.toLowerCase();
  const priority = document.getElementById('filterPriority').value.toLowerCase();
  const tag = document.getElementById('filterTag').value.toLowerCase();
  const search = document.getElementById('filterSearch').value.toLowerCase();

  const rows = document.querySelectorAll('#researcherTable tbody tr');
  rows.forEach(row => {{
    const cells = row.querySelectorAll('td');
    const name = (cells[0]?.textContent || '').toLowerCase();
    const rType = (cells[1]?.textContent || '').toLowerCase();
    const rRegion = (cells[4]?.textContent || '').toLowerCase();
    const rTags = (cells[7]?.textContent || '').toLowerCase();
    const rPriority = (cells[10]?.textContent || '').toLowerCase();

    let show = true;
    if (region && rRegion !== region) show = false;
    if (type && rType !== type) show = false;
    if (priority && rPriority.indexOf(priority) === -1) show = false;
    if (tag && rTags.indexOf(tag) === -1) show = false;
    if (search && name.indexOf(search) === -1) show = false;
    row.style.display = show ? '' : 'none';
  }});
}}

// Simple click-to-sort for table headers
document.querySelectorAll('table.sortable th').forEach((th, colIdx) => {{
  th.addEventListener('click', () => {{
    const table = th.closest('table');
    const tbody = table.querySelector('tbody');
    const rows = Array.from(tbody.querySelectorAll('tr'));
    const asc = th.dataset.sort !== 'asc';
    th.dataset.sort = asc ? 'asc' : 'desc';
    rows.sort((a, b) => {{
      const av = a.cells[colIdx]?.textContent || '';
      const bv = b.cells[colIdx]?.textContent || '';
      return asc ? av.localeCompare(bv) : bv.localeCompare(av);
    }});
    rows.forEach(r => tbody.appendChild(r));
  }});
}});
</script>
</body>
</html>"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--offline', action='store_true', help='Embed plotly.js for offline use')
    args = parser.parse_args()

    data = load_researchers()
    institutions = load_institutions()
    df = build_df(data, institutions)

    # Export CSV
    csv_cols = [
        'id', 'name', 'type', 'inst_display', 'country', 'region', 'position',
        'focus_str', 'tags_str', 'admission_chance', 'application_status',
        'priority', 'homepage', 'notes',
    ]
    df[csv_cols].to_csv(CSV_PATH, index=False, encoding='utf-8-sig')
    print(f"  CSV exported: {CSV_PATH}")

    figs = [fig_map(df), fig_institution(df), fig_tags(df), fig_kanban(df)]
    table_html = build_table_html(df)
    filters_html = build_filters_html(df)
    html = assemble_html(figs, table_html, filters_html, offline=args.offline)

    with open(HTML_PATH, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"  Dashboard: {HTML_PATH}")


if __name__ == '__main__':
    main()
