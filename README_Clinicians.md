# OrthoAI Clinical Validation Feature

This feature is integrated into the main OrthoAI backend. It does not require a
separate Dockerfile, compose file, or requirements file.

## Routes

- Main demo console: `/`
- UI: `/clinical/?case_id=<orthoai_case_id>`
- API: `/api/v1/clinical/*`
- OpenAPI docs: `/docs`

The main demo console now includes a header/menu entry for Clinical Validation.
It checks for a signed-in token and a completed source case before sending the
user to `/clinical/?case_id=<id>`. The backend also enforces this:

- all clinical API routes require the existing OrthoAI bearer token
- `case_id` must belong to the signed-in user
- the source case must have a completed inference job and stored results

## Data Store

Clinical validation records are stored in SQLite at:

```text
data/orthoai_clinical.db
```

Override with:

```bash
ORTHOAI_CLINICAL_DB=/path/to/orthoai_clinical.db
```

The clinical store is separate from the core OrthoAI diagnosis database. Each
clinical record is linked back to the source OrthoAI case through
`orthoai_case_id`.

## API Summary

All routes below are under `/api/v1/clinical` and require:

```http
Authorization: Bearer <OrthoAI JWT>
```

Routes scoped to a diagnosis require `source_case_id`:

| Method & path | Purpose |
|---|---|
| `GET /health?source_case_id=` | Confirms auth and completed-diagnosis access. |
| `POST /cases?source_case_id=` | Creates a clinical validation record. |
| `GET /cases?source_case_id=&site=&limit=&offset=` | Lists records for the diagnosis. |
| `GET /cases/{id}` | Fetches one record after ownership validation. |
| `PUT /cases/{id}` | Replaces one clinical validation record. |
| `DELETE /cases/{id}` | Deletes one clinical validation record. |
| `GET /stats?source_case_id=&site=` | Returns validation summary metrics. |
| `GET /export.csv?source_case_id=&site=` | Exports the diagnosis-scoped records as CSV. |

## Frontend Token Handling

The static UI is served from `app/static/`. The clinical page lives at
`app/static/clinical/index.html`.

Both pages attempt to reuse a token from common browser storage keys:

- `orthoai_access_token`
- `access_token`
- `accessToken`
- `authToken`
- `token`
- `jwt`

If the main frontend stores the token under a different key, either add that key
to the static HTML token discovery list or pass the token through the page's
session-token field.
