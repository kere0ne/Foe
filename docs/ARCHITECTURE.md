# Architecture

Foe Agent is a small local-first application.

- **Frontend:** static HTML, CSS, and JavaScript served by FastAPI.
- **API:** FastAPI routes project management, file operations, uploads, task records, terminal requests, and model chat.
- **Persistence:** SQLite stores project metadata and task history; project files are stored under `FOE_DATA_DIR/projects`.
- **Model provider:** the backend proxies streaming chat requests to an Ollama server configured with `OLLAMA_BASE_URL` and `OLLAMA_MODEL`.
- **Command execution:** by default, terminal commands are sent to a Docker container with network disabled, resource limits, dropped capabilities, and a read-only root filesystem.

Task records currently represent plans only. They do not imply autonomous completion or verified code changes.
