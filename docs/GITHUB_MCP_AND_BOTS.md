# Foe GitHub MCP and bot runtime

## DeepSeek and fallback providers

Set these in the Foe web service's private environment, never in Git:
- `AI_PROVIDER=deepseek`
- `DEEPSEEK_API_KEY` (required)
- `DEEPSEEK_MODEL=deepseek-chat` (optional)
- `AI_FALLBACK_PROVIDERS=openrouter,gemini`
- `OPENROUTER_API_KEY` (optional; OpenRouter's `openrouter/free` route can be rate-limited or unavailable)
- `OPENROUTER_MODEL=openrouter/free` (optional)
- `GEMINI_API_KEY` (optional fallback; may have a small free quota)

Foe tries configured providers in order when a request fails. No provider is unlimited, and fallback providers need their own valid API keys. Rotate any key pasted into chat or committed accidentally.

## Foe's GitHub MCP

This repository includes `github_mcp.py`, a stdio MCP server with repository listing, file tree/read/write, branch creation, and draft pull-request tools.

1. Install MCP dependencies: `python -m pip install -r requirements-mcp.txt`
2. Create a fine-grained GitHub token with access only to the repositories you want Foe to edit. Grant Contents read/write and Pull requests read/write only if needed.
3. Set `GITHUB_TOKEN` in the MCP client's private environment.
4. Configure the MCP client to launch `python /absolute/path/to/Foe/github_mcp.py` with that environment variable.

The token is never stored in this repository. The Foe agent also exposes GitHub tools when a GitHub token is connected in the Foe browser UI. Review changes before merging; MCP-created pull requests are drafts.

## Separate bot runtime (maximum 20 hours per start)

The AI web service and Discord bot processes are separate. The runtime accepts a project file map, installs explicitly listed Python requirements, starts the entrypoint, and terminates the process no later than 72,000 seconds (20 hours) after launch.

### Local setup

```sh
python -m pip install -r requirements.txt
# Set a long random token in your private shell environment first:
# export FOE_BOT_RUNTIME_TOKEN='...'
python bot_runtime.py
```

Then call `POST /bots/start` with `X-Foe-Bot-Token`, JSON fields `name`, `entrypoint`, `files`, optional `requirements`, optional `env`, and `runtime_seconds` (at most 72000). Use `GET /bots`, `GET /bots/{id}/logs`, and `POST /bots/{id}/stop` to manage bots. Put a Discord bot token in the request's `env` map as `DISCORD_TOKEN`; never put it in source code or GitHub.

### Hosting warning

Run the bot runtime as a separate, private service with a persistent worker/host. A free Render web service may sleep, restart, or terminate child processes, so it cannot promise a 20-hour continuous run. Render background workers generally require a paid instance. Do not expose the runtime to untrusted users: it executes supplied Python code and should use a dedicated service and strong secret token. Logs are bounded in memory and are not durable across restarts.
