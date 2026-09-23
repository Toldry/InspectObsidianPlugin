# Inspect Obsidian Plugins

This repository contains evaluation tasks using [Inspect AI](https://inspect.ai-evals.github.io/inspect_ai/), focusing on evaluating AI models on Obsidian plugin development and testing.

## Setup

Ensure you have Python and [Docker](https://www.docker.com/) installed, then install the required dependencies:

```bash
pip install inspect_ai
```

Build the sandbox Docker image:

```bash
docker compose build
```
*(Alternatively, build directly via Docker: `docker build -t daylio-eval .`)*

## Available Tasks

### 1. SWE Daylio Popout Bug Fix (`src/swe_daylio_popout.py`)
A software engineering (SWE) benchmark task that evaluates an AI agent's ability to diagnose and fix a specific bug in the `ObsidianDaylioPlugin`. The agent is given a sandboxed environment and the issue description, and must develop its own fix and tests. During evaluation, hidden reference tests are applied to verify the fix.

**Note**: This task requires [Docker](https://www.docker.com/) to be installed and running on your system. A custom Docker image (`Dockerfile` / `compose.yaml`) pre-bakes the target repository, commit state, and npm dependencies directly into the sandbox with network access disabled (`network_mode: none`) for safe and deterministic execution.

**Build sandbox:**
```bash
docker compose build
```

**To run:**
```bash
inspect eval src/swe_daylio_popout.py --model google/gemini-3.6-flash
```
*(You can replace the model string with your preferred supported model).*
