FROM node:20

# Create and set working directory
WORKDIR /repo

# Upstream commit the task starts from, and the SHA of the evaluation base commit
# built on top of it (upstream + env.patch). The commit is created with a fixed
# identity and date, so its SHA is deterministic; the build fails if it drifts.
# Keep BASE_COMMIT in sync with `base_commit` in src/swe_daylio_popout.py.
ARG UPSTREAM_REPO=https://github.com/Toldry/ObsidianDaylioPlugin.git
ARG UPSTREAM_COMMIT=91887ba8fae8068ff3f02e37c62d565221a8ee48
ARG BASE_COMMIT=b15fd4c01336c8688029ad790c78ec16078f92bc

# Environment-only changes applied on top of upstream (test mock stubs; no fix code)
COPY env.patch /tmp/env.patch

# Initialize repo, fetch ONLY the upstream commit (no future commits or tags),
# commit env.patch as the evaluation base, and install dependencies
RUN mkdir -p /repo && cd /repo && \
    git init && \
    git remote add origin "$UPSTREAM_REPO" && \
    git fetch --depth 1 origin "$UPSTREAM_COMMIT" && \
    git checkout -b main FETCH_HEAD && \
    git remote remove origin && \
    sed -i 's/\r$//' /tmp/env.patch && \
    git apply /tmp/env.patch && \
    rm /tmp/env.patch && \
    git add -A && \
    GIT_AUTHOR_NAME="User" GIT_AUTHOR_EMAIL="user@example.com" \
    GIT_COMMITTER_NAME="User" GIT_COMMITTER_EMAIL="user@example.com" \
    GIT_AUTHOR_DATE="2026-08-22T16:31:34+02:00" GIT_COMMITTER_DATE="2026-08-22T16:31:34+02:00" \
    git commit -q -m "test: extend Obsidian API test mock" && \
    test "$(git rev-parse HEAD)" = "$BASE_COMMIT" && \
    git config user.email "user@example.com" && \
    git config user.name "User" && \
    npm install && \
    git reset --hard
