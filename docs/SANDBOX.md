# Sandbox and security notes

Terminal execution is disabled unless Docker is available and the configured sandbox image exists. The default path runs commands inside a container with no network, memory/CPU/PID limits, a read-only root filesystem, dropped Linux capabilities, and an unprivileged UID.

Build the image with:

```sh
docker build -f sandbox.Dockerfile -t foe-agent-sandbox:latest .
```

The project directory is mounted read/write into the container so commands can modify the active project. Treat all project code and terminal input as untrusted.

**Do not** set `FOE_ALLOW_HOST_COMMANDS=true` for public or shared deployments. It bypasses container isolation. Docker socket access is highly privileged and must not be exposed to untrusted users.

This prototype does not implement authentication, per-user authorization, rate limiting, or production-grade auditing. Keep it bound to localhost until those protections are added.
