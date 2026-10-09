# Foe — Your Own Personal AI Assistant

**Foe is your private AI assistant and software helper.** Ask it anything, calculate, write, take notes, research the web, manage files, build code, and run commands — from an app you own and control.

## Your assistant can

- **Answer questions** — general knowledge, explanations, study help, how-tos, ideas and advice.
- **Calculate** — math, percentages, unit conversions (length, weight, temperature, data, cooking) and date math.
- **Utilities** — strong passwords, UUIDs, hashes, base64, JSON formatting, word counts, coin flips, dice and more.
- **Write things** — emails, essays, stories, plans, plus ready-made code templates.
- **Work with files** — list, read, create and search files in a private assistant workspace (or your own projects).
- **Notes & todos** — say `note ...`, `todo ...`, `show my notes`, `show my todos`, `done 1`.
- **Web research** — say `search the web for ...` and Foe reads pages and cites sources.
- **Run things** — say `run ...` to execute commands in an isolated sandbox.
- **Code help** — explain code, debug errors, starter projects in Python, JS, HTML and more.
- **Remember** — save up to 500 personal memories; Foe reuses them in future chats.
- **Chat history** — conversations are saved; reopen or delete them from the sidebar.
- **GitHub & bots** — import repos, commit edits, and launch Discord bots (see below).

## Zero-setup start (built-in brain, no login, no keys)

Foe ships with a built-in **Foe Brain**, so it works instantly with no Google login, no Ollama download, and no API keys. Perfect for your own private assistant on hardware you control.

Requires Python 3.11+:

```sh
git clone https://github.com/kere0ne/Foe.git
cd Foe
python -m venv .venv
# macOS/Linux
source .venv/bin/activate
# Windows PowerShell: .venv\\Scripts\\Activate.ps1
python -m pip install -r requirements.txt
FOE_DEMO_MODE=true uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000 and ask: **"What can you do?"**

Try: `calculate 15% of 240` · `convert 5 miles to km` · `make me a password` · `note buy milk` · `search the web for ...` · `create a file hello.py` · `run python --version`

> `FOE_DEMO_MODE=true` (aliases: `FOE_NO_AUTH`, `FOE_SINGLE_USER`) skips Google sign-in and serves one private local account. Only use it on a machine you control — never expose that mode to the public internet.

## Upgrade to a full AI model (optional)

Foe Brain handles everyday tasks instantly. For deeper open-ended reasoning and coding, connect a full model — Foe upgrades automatically and Foe Brain stays as fallback.

**Option A — Ollama on your computer (free, private).** Requires Docker Desktop (or Engine + Compose). The first launch downloads the model (minutes, multiple GB):

```sh
docker compose up --build
```

Then open http://localhost:8000. Ollama runs as a separate local container on a private network; model files and project data persist in Docker volumes.

The default model is `qwen2.5-coder:7b`. To choose another, create a `.env` file:

```dotenv
OLLAMA_MODEL=qwen2.5-coder:7b
FOE_PORT=8000
```

Restart Compose after changing the model. Larger models can be smarter but need more RAM/VRAM.

**Option B — Existing Python/Ollama setup.** Requires Python 3.11+ and an Ollama server:

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
ollama pull qwen2.5-coder:7b
AI_PROVIDER=ollama OLLAMA_BASE_URL=http://localhost:11434 OLLAMA_MODEL=qwen2.5-coder:7b uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000.

Foe is your own software, not a newly trained frontier model. Local model quality and speed depend on the model you download and your computer's memory, CPU, and GPU.

## Hosted website versus your own model

The public Render deployment is only the web app; its free instance does not include the resources to run a large language model. For a truly API-key-free model, run Foe and Ollama on your own PC with the Compose setup above. To use a model from the hosted website, configure a reachable model endpoint and protect it with authentication; never expose an unauthenticated Ollama server to the public internet.

Optional hosted providers are configurable in Render using `AI_PROVIDER`, `AI_FALLBACK_PROVIDERS`, and the provider-specific keys. Hosted providers may charge money or enforce quotas.

## Google sign-in and persistent storage

For a shared or hosted deployment, Foe uses Google OAuth. Follow [docs/GOOGLE_AUTH_SETUP.md](docs/GOOGLE_AUTH_SETUP.md) to configure Google OAuth and persistent database/storage. For a local install, Docker volumes persist project data. On Render, set `DATABASE_URL` for durable account/session/project metadata and set `FOE_DATA_DIR` to a persistent disk mount for project files; a database alone does not preserve project files.

For a purely personal install on your own machine, `FOE_DEMO_MODE=true` skips Google sign-in entirely (see above).

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
