# Foe Agent

An early-stage, local-first AI software engineering workspace with a FastAPI backend, project/file manager, browser editor, Ollama chat streaming, file uploads, task records, and Docker-backed command execution.

## Status

This is a prototype, not a production-ready public service. Authentication and per-user authorization are not implemented. Do not expose it to the public internet or use it with untrusted users.

## Source package

The full source package is available in the project ZIP linked in the ChatGPT conversation. This repository is being populated with the source files.

## Quick start

Requires Python 3.11+ and an Ollama server.

```sh
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\Activate.ps1
python -m pip install -r requirements.txt
ollama pull qwen2.5-coder:7b
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000. Configure `OLLAMA_BASE_URL` and `OLLAMA_MODEL` as needed.

## Docker sandbox

Build with `docker build -f sandbox.Dockerfile -t foe-agent-sandbox:latest .`. Review `SECURITY.md` and `docs/SANDBOX.md` before enabling command execution. Never enable host commands on a public/shared deployment.

## Render

A `render.yaml` Blueprint is included in the source package. Ollama must be reachable from the Render service; `localhost:11434` refers to the Render instance, not your personal computer. Free instance storage is ephemeral.

## License

MIT (see `LICENSE`).