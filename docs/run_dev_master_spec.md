# run-dev-master.sh specification

Date: 2026-02-19

## Objective

Provide a single "master" development container launcher script that can be executed from a workspace directory that sits above multiple GOFR repos (e.g. /home/gofr/devroot), and mounts selected repos as read-write so cross-project consistency work can be performed inside one container.

The script must build and run a container image using:

- lib/gofr-common/docker/Dockerfile.dev

## Non-goals

- No changes to production compose stacks.
- No attempt to run the GOFR services inside the dev container by default.
- No additional UX beyond what is required to build/run the master dev container.

## Current issues (motivation)

The existing lib/gofr-common/scripts/run-dev-master.sh currently:

- Derives PROJECT_ROOT from the script location (inside lib/gofr-common), which is not the intended multi-repo workspace root.
- Uses gofr-dig-dev:latest naming and a gofr-dig oriented container name.
- Mount paths assume sibling repos under PROJECT_ROOT, which does not match how PROJECT_ROOT is computed.

## Desired behavior

### 1) Workspace root resolution

- The script is intended to be run from the workspace root directory above all repos.
- Default WORKSPACE_ROOT is the current working directory.
- The script supports an explicit --workspace-root argument to override the default.

Validation:

- WORKSPACE_ROOT must contain the expected repo directories (see repo list below). If any are missing, the script must fail fast with a clear error and a recovery message.

### 2) Repos to mount as read-write

The script mounts the following repos as rw:

- gofr-dig
- gofr-doc
- gofr-np
- gofr-iq

Mount points inside the container:

- /home/gofr/devroot/gofr-dig
- /home/gofr/devroot/gofr-doc
- /home/gofr/devroot/gofr-np
- /home/gofr/devroot/gofr-iq

### 3) gofr-common source availability in the container

The gofr-common dev image expects /home/gofr/devroot/gofr-common.

Assumption (confirmed):

- There is NOT necessarily a sibling /home/gofr/devroot/gofr-common repo checkout.
- Each repo contains lib/gofr-common within its tree.

Therefore, the script must mount a canonical gofr-common source directory to:

- /home/gofr/devroot/gofr-common

Canonical source chosen:

- /home/gofr/devroot/gofr-dig/lib/gofr-common

Rationale:

- The script itself lives under that path in this workspace and can reliably locate the Dockerfile/build context.

### 4) Image build and runtime

Build inputs:

- Dockerfile: lib/gofr-common/docker/Dockerfile.dev
- Build context: lib/gofr-common (so COPY docker/entrypoint-dev.sh works)

Build policy:

- If the required dev image does not exist locally, the script must build it automatically.

Image naming:

- Image name: gofr-dev-master:latest
- Container name: gofr-dev-master

### 5) Docker networking

- The script ensures a primary network exists (default gofr-test-net; override via --network).
- The script also connects the container to gofr-net (for Vault/other shared services).

### 6) Secrets volume handling

- A shared docker volume named gofr-secrets is ensured/created.

The volume must be mounted into each selected repo at:

- /home/gofr/devroot/<repo>/secrets

Specifically:

- /home/gofr/devroot/gofr-dig/secrets
- /home/gofr/devroot/gofr-doc/secrets
- /home/gofr/devroot/gofr-np/secrets
- /home/gofr/devroot/gofr-iq/secrets

### 7) Docker socket access

- If /var/run/docker.sock exists on the host, mount it into the container and add the container user to the docker group (as per the gofr-common dev image entrypoint).

### 8) Host UID/GID

- The script will continue to run the container as the host uid:gid when it differs from 1000:1000 to avoid ownership problems on bind mounts.

### 9) Logging and output

- Errors must include a cause and a recovery hint.
- The script must not truncate logs.

## Assumptions

- The host has Docker available and can build images.
- The workspace root contains the four repos listed above.
- gofr-dig contains lib/gofr-common with docker/Dockerfile.dev present.

## Open questions

None pending for this spec.

## Acceptance criteria

- Running the script from /home/gofr/devroot starts a container named gofr-dev-master.
- If the image is missing, it is built from lib/gofr-common/docker/Dockerfile.dev.
- All listed repos are accessible in the container under /home/gofr/devroot and are writable.
- gofr-common is accessible at /home/gofr/devroot/gofr-common and is writable.
- gofr-secrets is mounted at /home/gofr/devroot/<repo>/secrets for all selected repos.
- The container is attached to gofr-test-net and gofr-net.
