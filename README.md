# armor-gw (Go)

**OpenAI-compatible LLM gateway that refuses to accept refusals.** Single binary, zero third-party dependencies, ~6 MB (stripped).

A self-hosted proxy that sits between your app and any OpenAI-compatible upstream. Every response is inspected by 13 refusal detectors; when a refusal is detected, the request is reformulated by one of 51 mutation operators and retried — while a second variant from a different strategy family races it in parallel. A Thompson-sampling bandit learns per-model which operator families actually work, and persists that knowledge across restarts.

```
your app ──> armor-gw ──> upstream (OpenAI / DeepSeek / any OpenAI-compatible)
                │
                ├─ 13 refusal detectors  (hard / soft / evasion / moral / substitute / dilution / silent / semantic / omission ...)
                ├─ 51 mutation operators (persona / encoding / inversion / text — 4 families)
                ├─ dual-operator racing  (goroutine per attempt, first clean answer wins)
                ├─ Thompson bandit       (per-model strategy learning, persisted)
                └─ embedded console      (glassmorphism web panel, no assets to ship)
```

## Quick start

```bash
# build (Go 1.21+; on a real machine this takes seconds)
go build -o armor-gw-go ./cmd/server

# configure one upstream + your downstream keys
export GW_KEYS=sk-your-key
export RELAY_BASE=https://api.deepseek.com/v1
export RELAY_API_KEY=sk-...
export RELAY_MODEL=deepseek-chat

./armor-gw-go
```

Open `http://127.0.0.1:8788/panel` — that's the console (embedded, no CDN, no assets).

Point any OpenAI SDK at it:

```python
from openai import OpenAI
client = OpenAI(base_url="http://127.0.0.1:8788/v1", api_key="sk-your-key")
r = client.chat.completions.create(model="deepseek-chat",
                                   messages=[{"role": "user", "content": "..."}])
```

## Why the Go version

The Python edition of this gateway ships an interpreter plus a dependency tree. This one is a single static file:

| | Python edition | Go edition |
|---|---|---|
| artifact | venv + deps | 1 binary (~6 MB (stripped)) |
| deploy | `pip install` on target | `scp` + run |
| cross-compile | — | `GOOS=linux GOARCH=amd64 go build` |
| memory | ~100 MB RSS class | ~10 MB RSS class |
| strategy learning | Thompson bandit | same, file-persisted |
| ops surface | FastAPI/uvicorn | net/http stdlib only |

## Environment variables

```bash
GW_HOST=0.0.0.0            # listen host
GW_PORT=8788               # listen port
GW_KEYS=sk-a,sk-b          # downstream auth keys (comma separated)
GW_RPM=120                 # per-key requests/min
GW_ADMIN_KEYS=sk-admin     # optional: keys allowed to write admin endpoints
GW_ADMIN_WRITE_GUARD=1     # enforce admin keys on write endpoints

# upstreams — first one that has a key wins; RELAY_* is the generic escape hatch
DEEPSEEK_API_KEY=           DEEPSEEK_BASE=  DEEPSEEK_MODEL=
OPENAI_API_KEY=             OPENAI_MODEL=
RELAY_API_KEY=              RELAY_BASE=     RELAY_MODEL=
```

## Endpoints

- `POST /v1/chat/completions` — OpenAI-compatible. Response carries `x_armor` (rounds, attempts, per-attempt verdicts).
- `GET /v1/models` — list upstream models.
- `GET /v1/admin/stats` — totals, per-route stats, avg rounds, last 50 requests.
- `GET /panel` — embedded console.
- `GET /health` — liveness.

## What the retry engine does

Each round fires **two goroutines** with different operator families (sampled by the bandit). The first non-refused answer wins the race; both attempts are recorded, and feedback is reported per-operator (the winner feeds `win`, the loser `loss`) so the bandit's per-model priors converge on what actually breaks that model's refusal behavior. Learning state lives in `data/strategy_bandit.json`, flushed at most once per 10 s and on SIGTERM.

## Hardening included

- downstream key auth + optional admin-key tier for write endpoints
- sliding-window rate limit per key, with dead-key GC
- input guards: payload size (30k chars), temperature/max_tokens ranges, NUL scrubbing
- disconnect cutoff: client hangs up → context cancels → pipeline stops immediately (no burned upstream tokens)
- transport retries with exponential backoff on 5xx / network errors; 4xx fast-fail
- path-safe embedded assets; console served `no-store`

## Relation to the Python edition

This is the Go rewrite of [armor-gw](https://github.com/Dixxxzao-01/armor-gw) (Python/FastAPI). The Python edition has the full 62-operator pool, the 65-question test bank, the decomposer fallback and the seven-layer scrub chain; the Go edition covers the high-frequency core (51 operators, all 13 detector classes, bandit learning) in a single-file deployment. Both share the same philosophy and the same `x_armor` response shape.

## License

MIT

## Heritage: the Python edition

The original Python/FastAPI implementation — full 62-operator pool, 65-question
test bank, seven-layer scrub chain, decomposer fallback — lives on under
[`legacy/python/`](legacy/) in this repo (runnable as-is; see its own README
history in git). The Go rewrite covers the high-frequency core in a single
6 MB file; the Python edition remains the reference implementation for the
research surface (breeder, testbank, prober).
