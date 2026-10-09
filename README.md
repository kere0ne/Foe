# Foe Agent

**An early-stage, local-first AI software engineering workspace.** Foe Agent provides a FastAPI backend and browser UI for project/file management, code editing, Ollama chat streaming, file uploads, task planning, and Docker-backed command execution.

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

This is a **prototype**, not a production-ready public service. Authentication and per-user authorization are not implemented. Do not expose this service to the public internet or use it with multiple untrusted users. Review [SECURITY.md](SECURITY.md) and [docs/SANDBOX.md](docs/SANDBOX.md). Never enable `FOE_ALLOW_HOST_COMMANDS=true` on a public/shared deployment.

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

Foe supports DeepSeek as its primary OpenAI-compatible provider, with optional OpenRouter and Gemini fallbacks. Configure `AI_PROVIDER=deepseek`, `DEEPSEEK_API_KEY`, and optionally `AI_FALLBACK_PROVIDERS=openrouter,gemini` plus the corresponding fallback API keys in your service environment. Providers may have billing, quota, and rate limits; no hosted provider is unlimited.

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

A `render.yaml` Blueprint is included. **Before using the public service, set `FOE_ACCESS_KEY`** to a long random secret in Render → your service → Environment. The API fails closed until this is configured. Enter the same value in the Foe browser prompt. Do not commit the key or put it in source code. After pushing this repository, open [Render Blueprint](https://dashboard.render.com/blueprint/new?repo=https://github.com/kere0ne/Foe) and apply it. Set `OLLAMA_BASE_URL` to an Ollama API endpoint reachable from Render. `localhost:11434` on Render is not your personal computer. Free instance storage is ephemeral, so project files and SQLite data can be lost on restarts/redeploys. Do not publicly expose this prototype until authentication and production hardening are implemented.

## Current limitations

Task creation records a plan only; it does not autonomously complete the work. Authentication, multi-user isolation, OAuth/GitHub operations, advanced IDE features, a full autonomous tool loop, multi-agent coordination, and production-grade monitoring are not implemented.

## License

MIT. See [LICENSE](LICENSE).
