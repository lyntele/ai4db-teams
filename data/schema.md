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
| `institution` | string | institutions.json 中的 key |
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
| `currently_taking_students` | bool | 是否招生 |
| `admission_chance` | string | `"high"` / `"medium"` / `"low"` / `"internship-only"` |
| `application_status` | string | `considering` / `shortlisted` / `contacted` / `awaiting-reply` / `applied` / `rejected` / `accepted` / `not-applicable` |
| `priority` | string | `"high"` / `"medium"` / `"low"` |
| `contact_history` | array[{date, method, notes}] | 联系记录 |
| `notes` | string | 备注 |
| `added_date` | string | `YYYY-MM-DD` |
| `last_updated` | string | `YYYY-MM-DD` |

## Controlled vocabulary for tags

`NL2SQL` · `text-to-SQL` · `data-agents` · `LLM-DB` · `query-optimization`
`table-QA` · `RAG` · `schema-linking` · `vector-DB` · `knowledge-graph`
`data-integration` · `ML-systems` · `NLP`
