# Dev container image. Root-only setup lives here because the container runs
# with no-new-privileges, which disables sudo at runtime.
#
# Everything is installed here (no dev container features, no postCreateCommand)
# so Docker caches each step. Steps are ordered from least to most frequently
# changed: editing a later step only rebuilds the steps after it.
FROM mcr.microsoft.com/devcontainers/base:ubuntu-24.04

# System packages. Ubuntu 24.04's python3 is 3.12, so no Python build is needed.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        zstd unzip python3 python3-venv python3-pip \
    && rm -rf /var/lib/apt/lists/*

# Node.js 20 from NodeSource.
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# GitHub CLI from GitHub's apt repo. Authenticate with `gh auth login` or a
# GH_TOKEN in the --env-file secrets.
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
        -o /etc/apt/keyrings/githubcli-archive-keyring.gpg \
    && chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
        > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends gh \
    && rm -rf /var/lib/apt/lists/*

# Python tooling in a venv owned by vscode, so `pip install` works at runtime
# without root (the system Python is externally managed, PEP 668).
# Pinned so the cached layer and a fresh build install the same version.
ENV PATH=/opt/venv/bin:$PATH
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir inspect_ai==0.3.268 \
    && chown -R vscode:vscode /opt/venv

# Pre-create the Claude Code config dir so the named volume mounted over it
# inherits vscode ownership on first use.
RUN mkdir -p /home/vscode/.claude \
    && chown -R vscode:vscode /home/vscode/.claude

# Claude Code managed settings, applied only inside this container: sessions
# start in auto mode here while the host keeps its own default (Manual).
COPY managed-settings.json /etc/claude-code/managed-settings.json
