# SMN Studio

Visual workflow builder for the SMN platform — drag-and-drop nodes into governed, auditable automation workflows.

## Architecture

```
studio/
├── frontend/          # Vite + React + React Flow canvas
│   ├── src/
│   │   ├── App.tsx              # Root + API key gate
│   │   ├── components/
│   │   │   ├── Editor.tsx       # Main canvas editor
│   │   │   ├── WorkflowList.tsx # Workflow library
│   │   │   ├── NodePalette.tsx  # Drag-to-add sidebar
│   │   │   ├── ConfigPanel.tsx  # Node config forms
│   │   │   ├── RunsPanel.tsx    # Execution history
│   │   │   └── StudioNode.tsx   # Universal node component
│   │   ├── api/client.ts        # API client (talks to /studio/api/v1)
│   │   └── types/workflow.ts    # Shared TypeScript types + NODE_PALETTE
│   └── dist/                    # Built output — served by FastAPI at /studio
└── README.md                    # This file

src/smn/studio/                  # Python backend (part of smn package)
├── __init__.py
├── db.py                        # Separate SQLAlchemy engine (studio.db)
├── models.py                    # Workflow, WorkflowRun, WorkflowRunStep, WebhookToken
├── schemas.py                   # Pydantic schemas
├── executor.py                  # DAG topological sort + node execution engine
├── router.py                    # FastAPI router mounted at /studio/api/v1
└── nodes/
    ├── base.py                  # BaseNode + NodeResult + template resolver
    ├── agent.py                 # Run a governed SMN Agent
    ├── llm_prompt.py            # Raw LLM call with templates
    ├── http.py                  # Governed outbound HTTP (SSRF protected)
    ├── condition.py             # Branch on a comparison (true/false handles)
    └── delay.py                 # asyncio.sleep pause
```

## Node Types

| Node | Purpose | Output Handles |
|------|---------|---------------|
| **SMN Agent** | Runs a governed SMN agent through the Trust Plane | `output` |
| **LLM Prompt** | Direct LLM call with system + user message templates | `output` |
| **HTTP Request** | Outbound HTTPS call with SSRF protection | `output` |
| **Condition** | Branch on `left op right` comparison | `true` / `false` |
| **Delay** | Pause execution up to 300 seconds | `output` |

## Template Variables

In any node config field, reference outputs from previous nodes using `{{node_id.field}}`:

```
{{trigger.body.query}}         → the body of the webhook that started the run
{{node-1.output}}              → full output string from node-1
{{node-2.data.status_code}}    → nested field from an HTTP node
```

## Development

### Backend (already integrated into `smn serve`)

```bash
# From repo root — studio DB is auto-created alongside smn.db
smn serve
```

The studio API is available at `http://localhost:8000/studio/api/v1`.

### Frontend (dev mode with hot reload)

```bash
cd studio/frontend
npm install
npm run dev
# → http://localhost:5173/studio
```

Vite proxies `/studio/api` requests to the running SMN server on `:8000`.

### Build for production

```bash
cd studio/frontend
npm run build
# → dist/ is created and will be served by FastAPI at /studio
smn serve
# → http://localhost:8000/studio
```

## API Reference

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/studio/api/v1/workflows` | Create workflow |
| `GET` | `/studio/api/v1/workflows` | List workflows |
| `GET` | `/studio/api/v1/workflows/{id}` | Get workflow |
| `PUT` | `/studio/api/v1/workflows/{id}` | Update workflow definition |
| `DELETE` | `/studio/api/v1/workflows/{id}` | Delete workflow |
| `POST` | `/studio/api/v1/workflows/{id}/run` | Manually trigger a run |
| `GET` | `/studio/api/v1/workflows/{id}/runs` | List recent runs |
| `GET` | `/studio/api/v1/runs/{run_id}` | Get run + step details |
| `POST` | `/studio/api/v1/workflows/{id}/webhooks` | Create webhook trigger |
| `POST` | `/studio/webhooks/{token}` | Inbound webhook (no auth required — token is the secret) |

All endpoints (except webhook inbound) require `X-API-Key`.

## Adding Node Types

1. Create `src/smn/studio/nodes/my_node.py` extending `BaseNode`
2. Register in `src/smn/studio/nodes/__init__.py` → `NODE_REGISTRY`
3. Add a `NodeMeta` entry to `studio/frontend/src/types/workflow.ts` → `NODE_PALETTE`
4. Add a config form section in `studio/frontend/src/components/ConfigPanel.tsx`
