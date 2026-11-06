# 查询汇率 — Redacted Contract Snapshot

| Item | Evidence |
|---|---|
| Interface key | `LX-C6759B059E67` |
| Contract status | `READY_FOR_PRP` (Owner re-evaluation, see below) |
| Owner decision | `docs/data-sources/decisions/lingxing-fx-rate-source-decision.md` |
| Normalized interface source | `docs/integrations/lingxing-walmart-openapi/normalized/deleted_interfaces.csv#LX-C6759B059E67` |
| Evidence | Read-only probes run by the deploy role on 2026-11-02 and 2026-11-05; the normalized index has no field rows, so the fields below come from those responses |
| Path | `/erp/sc/routing/finance/currency/currencyMonth` |
| Method | `POST` |
| Protocol | `HTTPS` |
| Pagination | None; one request returns one month |
| Rate limit evidence | Unknown; the governed sync sends one request per month, sequentially |
| Authentication | Existing Lingxing query-sign client; no credential value is recorded here |
| Side effects | None observed; query only |
| Can enter PRP planning | `yes` |

## Request parameters

| Path | Type | Required | Notes |
|---|---|---|---|
| `date` | `string` | Yes | Month, `YYYY-MM` |

## Response fields

Observed shape: `code`, `message`, `error_details`, `request_id`, `response_time`, `data`, `total`. `code = 0` is success. `data` is an array with one row per currency (24 rows in both probes).

| Path | Type | Notes |
|---|---|---|
| `data[].date` | `string` | Month, `YYYY-MM` |
| `data[].code` | `string` | Currency code |
| `data[].name` | `string` | Currency name |
| `data[].icon` | `string` | Currency symbol; not stored |
| `data[].rate_org` | `string` (decimal) | Lingxing original rate; stored, not used for conversion |
| `data[].my_rate` | `string` (decimal) | The rate maintained in Lingxing; the only value used for conversion |
| `data[].update_time` | `string` | Provider update time; stored as text |

## Unknowns

Behaviour for a month with no rates has not been observed. The sync treats an empty or null `data` as "no rates this month", skips it, and fails the run only when every month is empty.
