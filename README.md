# Foe Agent

**Foe Engine is your local-first AI assistant and software engineering agent.** It combines chat, a project-aware coding loop, project files, an editor, uploads, sandboxed command execution, GitHub tools, and optional bot runtime support.

## What makes it yours

- Run an open model on a computer you control with Ollama. The default setup does not require a paid AI API key.
- Ask general questions in Chat mode or let Agent mode inspect and edit a selected project.
- Manage project files, upload individual files or ZIP archives, edit code, and review the agent work log.
- Let Agent mode inspect files, make edits, run project commands, build, test, inspect failures, and iterate—similar to a repository-aware coding CLI. Commands run inside a restricted Docker sandbox, not directly on the host.
- DeepSeek has been removed. The default Foe Engine uses Ollama and a downloadable open model; no paid model API key is required for local use.
- Choose a different Ollama model using the `OLLAMA_MODEL` environment variable.
- Save up to 500 personal memories (added manually in the Memory panel or automatically from your chats) in the Workspace → Memory panel; saved memories are private to your account and can be reviewed or deleted. Foe adds them as context to future chats and coding-agent runs.
- Foe remembers your conversations: chat history is saved to your account, recent chats are listed in the sidebar, and you can reopen or delete them.
- Web research: Agent and Assistant modes can search the public web and read pages, citing the source URLs they used.
- Assistant mode: with no project selected, the agent still works in a private Foe Assistant workspace, so Foe can research, write, and run things without a codebase.
- Use hosted providers only if you choose to configure their keys; provider access may have costs and limits.

Foe is your own software, not a newly trained frontier model. Local model quality and speed depend on the model you download and your computer's memory, CPU, and GPU.

## Run Foe Engine locally (recommended)

Requires Docker Desktop (or Docker Engine + Compose). The first launch downloads the default model, which can take several minutes and multiple gigabytes.

```sh
git clone https://github.com/kere0ne/Foe.git
cd Foe
docker compose up --build
```

Then open http://localhost:8000. Ollama runs as a separate local container, and Foe sends prompts to it over the private Compose network. Model files and Foe project data are stored in named Docker volumes, so they survive normal container restarts.

The default model is `qwen2.5-coder:7b`. To choose another Ollama model, create a `.env` file containing, for example:

```dotenv
OLLAMA_MODEL=qwen2.5-coder:7b
FOE_PORT=8000
```

Restart Compose after changing the model. Larger models can be smarter but need more RAM/VRAM; smaller models run on more machines but may make more mistakes.

## Existing Python/Ollama setup

Requires Python 3.11+ and an Ollama server:

```sh
python -m venv .venv
# macOS/Linux
source .venv/bin/activate
# Windows PowerShell: .venv\\Scripts\\Activate.ps1
python -m pip install -r requirements.txt
ollama pull qwen2.5-coder:7b
AI_PROVIDER=ollama OLLAMA_BASE_URL=http://localhost:11434 OLLAMA_MODEL=qwen2.5-coder:7b uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000.

## Hosted website versus your own model

The public Render deployment is only the web app; its free instance does not include the resources to run a large language model. For a truly API-key-free model, run Foe and Ollama on your own PC with the Compose setup above. To use a model from the hosted website, configure a reachable model endpoint and protect it with authentication; never expose an unauthenticated Ollama server to the public internet.

Optional hosted providers are configurable in Render using `AI_PROVIDER`, `AI_FALLBACK_PROVIDERS`, and the provider-specific keys. Hosted providers may charge money or enforce quotas.

## Google sign-in and persistent storage

Foe uses Google OAuth only. Follow [docs/GOOGLE_AUTH_SETUP.md](docs/GOOGLE_AUTH_SETUP.md) to configure Google OAuth and persistent database/storage. For a local install, Docker volumes persist project data. On Render, set `DATABASE_URL` for durable account/session/project metadata and set `FOE_DATA_DIR` to a persistent disk mount for project files; a database alone does not preserve project files.

## GitHub and Discord bots

See [docs/GITHUB_MCP_AND_BOTS.md](docs/GITHUB_MCP_AND_BOTS.md) for GitHub tools and the separate Python/Node.js bot runtime. The bot runner can cap a launch at 20 hours, but it must run on a host that stays awake. A free Render web service cannot guarantee continuous bot uptime.

## Docker sandbox and security

Foe Engine can run project-specific commands inside an isolated sandbox with networking disabled, capped resources, dropped Linux capabilities, and a read-only container root. Only the selected project folder is writable. The sandbox is not a replacement for reviewing commands and generated code.

Foe is an early-stage project. The local Compose setup mounts the Docker socket so Foe can request sandbox containers; Docker socket access is powerful and should only be used on a machine you control. Keep the service private, review generated code before running it, and never enable `FOE_ALLOW_HOST_COMMANDS=true` on a public/shared deployment. See [SECURITY.md](SECURITY.md) and [docs/SANDBOX.md](docs/SANDBOX.md).

## Tests

```sh
python -m pip install -r requirements.txt pytest
pytest -q
```

## License

MIT. See [LICENSE](LICENSE).
