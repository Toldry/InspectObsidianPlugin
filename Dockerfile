FROM node:20

# Create and set working directory
WORKDIR /repo

# Initialize repo, fetch ONLY the target commit (no future commits or tags), and install dependencies
RUN mkdir -p /repo && cd /repo && \
    git init && \
    git remote add origin https://github.com/Toldry/ObsidianDaylioPlugin.git && \
    git fetch --depth 1 origin 91887ba8fae8068ff3f02e37c62d565221a8ee48 && \
    git checkout -b main FETCH_HEAD && \
    git remote remove origin && \
    git config user.email "agent@example.com" && \
    git config user.name "Agent" && \
    npm install && \
    git reset --hard
