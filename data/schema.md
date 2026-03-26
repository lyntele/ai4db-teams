# researchers.json Schema

## Top-level

```json
{
  "meta": { "version": "1.1", "last_updated": "YYYY-MM-DD" },
  "researchers": [ ...entries... ]
}
```

## Entry fields

| Field | Type | Enum / Notes |
|-------|------|--------------|
| `id` | string | `uid-NNN` 唯一标识 |
| `name` | string | 英文全名 |
| `type` | string | `"faculty"` / `"industry"` |
| `institution` | string | institutions.json 中的 key；自动发现时也可能是生成的 `QS_*` key |
| `institution_display_name` | string | 自动发现时用于展示的学校名；当学校还不在 institutions.json 时会出现 |
| `institution_qs_rank` | number | 自动发现时记录的 QS 排名 |
| `department` | string | 院系简称 |
| `country` | string | 国家 |
| `region` | string | `"Asia"` / `"Europe"` / `"North America"` / `"Oceania"` |
| `position` | string | 职位（Professor / Research Scientist 等） |
| `research_focus` | array[string] | 自由描述研究方向 |
| `tags` | array[string] | 受控词汇见下 |
| `homepage` | string | 个人主页 URL |
| `email` | string | 联系邮箱（可留空） |
| `google_scholar` | string | Scholar URL（可留空） |
| `notable_papers` | array[{title, venue, url}] | 代表作 |
| `research_group_url` | string | 课题组主页 |
| `members` | array[{name, position, homepage, notes}] | 工业界团队的公开成员列表；通常由近期相关论文作者回填，并优先复用已有个人主页 |
| `currently_taking_students` | bool | 是否招生 |
| `admission_chance` | string | `"high"` / `"medium"` / `"low"` / `"internship-only"` |
| `application_status` | string | `considering` / `shortlisted` / `contacted` / `awaiting-reply` / `applied` / `rejected` / `accepted` / `not-applicable` |
| `priority` | string | `"high"` / `"medium"` / `"low"` |
| `contact_history` | array[{date, method, notes}] | 联系记录 |
| `notes` | string | 备注 |
| `added_date` | string | `YYYY-MM-DD` |
| `last_updated` | string | `YYYY-MM-DD` |

自动发现的学校如果还没有正式收录到 `data/institutions.json`，会优先写入 `institution_display_name` 和 `institution_qs_rank`，这样 dashboard 仍然可以正常显示学校名和 QS 标记。

工业界团队如果没有稳定可用的团队主页，可以把 `homepage` / `research_group_url` 留空，同时在 `members` 里按论文作者回填成员；dashboard 会以可展开方式展示，若能找到个人主页就会直接链接。

## Controlled vocabulary for tags

`NL2SQL` · `text-to-SQL` · `data-agents` · `LLM-DB` · `query-optimization`
`table-QA` · `RAG` · `schema-linking` · `vector-DB` · `knowledge-graph`
`data-integration` · `ML-systems` · `NLP`
