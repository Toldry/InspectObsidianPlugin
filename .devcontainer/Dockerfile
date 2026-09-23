# Dev container image. Root-only setup lives here because the container runs
# with no-new-privileges, which disables sudo at runtime.
FROM mcr.microsoft.com/devcontainers/base:ubuntu-24.04

RUN apt-get update \
    && apt-get install -y --no-install-recommends zstd unzip \
    && rm -rf /var/lib/apt/lists/*

# Pre-create the Claude Code config dir so the named volume mounted over it
# inherits vscode ownership on first use.
RUN mkdir -p /home/vscode/.claude \
    && chown -R vscode:vscode /home/vscode/.claude

# Claude Code managed settings, applied only inside this container: sessions
# start in auto mode here while the host keeps its own default (Manual).
COPY managed-settings.json /etc/claude-code/managed-settings.json
