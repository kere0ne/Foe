# Foe Agent

**An early-stage, local-first AI software engineering workspace.** Foe Agent provides a FastAPI backend and browser UI for project/file management, code editing, DeepSeek-compatible chat, file uploads, task planning, and optional sandboxed command execution.

## Features

- Create and manage workspaces backed by SQLite metadata.
- Browse, read, write, and delete project files with path checks.
- Upload files and ZIP archives with size and archive-entry limits.
- Stream responses from a configured Ollama model.
- Record task plans and view task history.
- Run explicit commands in a constrained Docker container when configured.
- Responsive dark interface with chat, files, editor, terminal, and task views.
- Health and model-connectivity endpoints.

## Important security notice

This is a **prototype**, not a production-ready public service. Google OAuth sign-in and per-user authorization are implemented; complete the Google and persistent-storage setup before public use. Do not expose this service to the public internet or use it with multiple untrusted users. Review [SECURITY.md](SECURITY.md) and [docs/SANDBOX.md](docs/SANDBOX.md). Never enable `FOE_ALLOW_HOST_COMMANDS=true` on a public/shared deployment.

## Quick start

Requires Python 3.11+ and an Ollama server.

```sh
python -m venv .venv
# macOS/Linux
source .venv/bin/activate
# Windows PowerShell: .venv\\Scripts\\Activate.ps1
python -m pip install -r requirements.txt
ollama pull qwen2.5-coder:7b
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000. Ollama defaults to `http://localhost:11434`; configure `OLLAMA_BASE_URL` and `OLLAMA_MODEL` as needed. A model is not bundled in this repository: Ollama runs the open model you choose.

## Hosted AI providers

Foe supports Meta Model API (Muse Spark) as its primary OpenAI-compatible provider, with optional DeepSeek, OpenRouter, and Gemini fallbacks. Configure `AI_PROVIDER=meta`, `META_API_BASE_URL=https://api.meta.ai/v1`, `META_MODEL=muse-spark-1.3`, and `MODEL_API_KEY`; optionally set `AI_FALLBACK_PROVIDERS=deepseek,openrouter,gemini` plus the matching provider API keys. Providers may have billing, quota, and rate limits; no hosted provider is unlimited.

## Google sign-in and persistent storage

Foe uses Google OAuth only. Follow [docs/GOOGLE_AUTH_SETUP.md](docs/GOOGLE_AUTH_SETUP.md) to configure the Google OAuth client and persistent database/storage. The app supports PostgreSQL via `DATABASE_URL`; project files are stored under `FOE_DATA_DIR`, which must point to a Render persistent disk mount (for example `/var/data`) to survive restarts. The current free web service has ephemeral storage, so a database alone does not preserve project files.

## GitHub MCP and Discord bot runtime

See [docs/GITHUB_MCP_AND_BOTS.md](docs/GITHUB_MCP_AND_BOTS.md) for Foe's custom GitHub MCP server, GitHub agent tools, and the separate Python/Node.js bot runtime. The bot runner can cap a launch at 20 hours, but it must run on a host that stays awake. A free Render web service cannot guarantee continuous bot uptime; a dedicated always-on worker may incur charges. The runtime executes project code, so keep it private and protect it with a strong `FOE_BOT_RUNTIME_TOKEN`.

## Docker sandbox

Build the sandbox image:

```sh
docker build -f sandbox.Dockerfile -t foe-agent-sandbox:latest .
docker compose up --build
```

The sandbox disables network access and applies container resource restrictions. Docker socket access is privileged; use it only on a machine you control. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Tests

```sh
pytest -q
```

## Deploying to Render

A `render.yaml` Blueprint is included. **Before using the public service, set `FOE_ACCESS_KEY`** to a long random secret in Render → your service → Environment. The service uses Google OAuth for account access. Configure `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and `GOOGLE_REDIRECT_URI` in Render; configure `DATABASE_URL` for durable account/session/project metadata and set `FOE_DATA_DIR` to a persistent disk mount for project files. Never commit secrets.

## Current limitations

Task creation records a plan only; it does not autonomously complete the work. Authentication, multi-user isolation, OAuth/GitHub operations, advanced IDE features, a full autonomous tool loop, multi-agent coordination, and production-grade monitoring are not implemented.

## License

MIT. See [LICENSE](LICENSE).
