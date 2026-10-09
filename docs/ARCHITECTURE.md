# Foe architecture

- **Frontend:** static HTML, CSS, and JavaScript served by FastAPI.
- **API:** FastAPI routes chat, project/file management, uploads, task planning, terminal requests, and model chat.
- **Local AI:** Ollama runs the selected open model. Docker Compose keeps the model endpoint on a private internal network and persists model weights in a named volume.
- **Persistence:** SQLite stores project metadata and task history; project files live under `FOE_DATA_DIR/projects`. The local Compose configuration persists data in named Docker volumes.
- **Foe Engine coding agent:** Agent mode sends project context to the model and loops through tool calls to inspect, search, and edit files; it can run project commands, builds, tests, and linters, inspect failures, and iterate. The agent reports actions actually returned by tools; users should review generated changes.
- **Command execution:** project commands run in a constrained Docker container with networking disabled, bounded resources, dropped capabilities, and a read-only root filesystem. Only the selected project directory is mounted writable.
- **Provider strategy:** DeepSeek integration has been removed. Ollama is the default local runtime; optional hosted providers remain available only when explicitly configured.

Foe is your own application using an existing open model; it does not train a frontier model from scratch. Model quality and speed depend on your hardware and selected model. The public Render deployment does not have enough free compute to host Ollama alongside the web app; use the local Compose setup for API-key-free local inference.
