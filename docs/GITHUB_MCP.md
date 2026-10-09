# GitHub MCP and Foe

Foe's browser workspace uses GitHub's REST API for token-based repository listing, repository import, and committing edited files. The token is supplied by the browser and is not saved in Foe's database. Use a fine-grained token with access only to the repositories you need; grant **Contents: Read and write** only if you want Foe to import and commit changes.

For a real MCP server in a local IDE, this repository includes `.vscode/mcp.json` for GitHub's official MCP server. Install Docker, open the repo in VS Code, then approve the GitHub MCP server and enter your token when prompted. The official server is a separate local MCP process; the hosted Render app cannot launch a local stdio MCP process on your computer.

Official project: https://github.com/github/github-mcp-server

## Browser integration
1. Open Foe and select **Connect GitHub**.
2. Paste a fine-grained personal access token.
3. Select a repository to import it into a Foe project.
4. Edit files in the workspace. Use **Commit to GitHub** to create a commit on that repository's default branch.

## Computer and terminal execution
A browser cannot directly operate your personal computer. For local execution, run Foe on your own machine with Docker and Ollama using `docker compose up --build`; the sandbox image is built from `sandbox.Dockerfile`. The hosted Render service does not have your computer's files or Docker daemon, so hosted terminal commands are disabled unless a dedicated sandbox runner is configured.

Never set `FOE_ALLOW_HOST_COMMANDS=true` on a public service.
