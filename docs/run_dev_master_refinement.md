# run-dev-master.sh review and refinement

Date: 2026-02-19

## Goal (as requested)

You want to run a single "master" dev container from a folder that sits above all GOFR projects, and mount all project folders as read-write so you can review and manage cross-project consistency.

You also want this script to launch an image built from:

- lib/gofr-common/docker/Dockerfile.dev

## What the script does today

File:

- lib/gofr-common/scripts/run-dev-master.sh

Key behaviors:

1) Root/path detection

- SCRIPT_DIR is the directory of the script.
- PROJECT_ROOT is computed as SCRIPT_DIR/..

Given the script lives under lib/gofr-common/scripts, PROJECT_ROOT resolves to:

- .../lib/gofr-common

This matters because the script later assumes PROJECT_ROOT contains sibling repos like gofr-dig, gofr-doc, etc.

2) Container/image identifiers

- CONTAINER_NAME=gofr-dig-dev
- IMAGE_NAME=gofr-dig-dev:latest

This conflicts with the stated goal of using the gofr-common dev Dockerfile. The current image name implies the gofr-dig dev image.

3) Networks and volumes

- Ensures two networks exist: gofr-test-net (default) and gofr-net
- Creates/ensures a docker volume: gofr-secrets

4) Pre-flight checks

- Checks IMAGE_NAME exists.
- Checks gofr-common submodule is initialised under PROJECT_ROOT/lib/gofr-common

In practice, with PROJECT_ROOT pointing at lib/gofr-common already, the submodule check is not meaningful (it checks lib/gofr-common inside lib/gofr-common).

5) Mounts

The docker run includes these mounts:

- -v "$PROJECT_ROOT:/home/gofr/devroot:rw"
- -v ${SECRETS_VOLUME}:/home/gofr/devroot/gofr-dig/secrets:rw
- -v "$PROJECT_ROOT/gofr-doc:/home/gofr/devroot/gofr-doc:rw"
- -v "$PROJECT_ROOT/gofr-dig:/home/gofr/devroot/gofr-dig:rw"
- -v "$PROJECT_ROOT/gofr-iq:/home/gofr/devroot/gofr-iq:rw"
- -v "$PROJECT_ROOT/gofr-np:/home/gofr/devroot/gofr-np:rw"

With PROJECT_ROOT = lib/gofr-common, those sibling repo paths do not exist.

Also note: mounting PROJECT_ROOT to /home/gofr/devroot would mount only gofr-common into the devroot path (not the full multi-project workspace).

6) Environment

The script sets only GOFRDIG_* env vars. If the container is meant to be a cross-project "master" container, these should probably be optional/passthrough, not hard-coded.

## The big mismatches to your desired workflow

1) PROJECT_ROOT calculation is wrong for the intended usage

- You want PROJECT_ROOT to be the directory above all projects.
- Today it resolves to the gofr-common repo root (because the script is inside it).

2) It uses gofr-dig-dev:latest, not the gofr-common dev image

- Your requested Dockerfile.dev builds a gofr-common development image.
- Today it expects a gofr-dig dev image.

3) Secrets volume is only mounted into gofr-dig

- For a cross-project container, you likely want secrets accessible for each project, or a shared mount point with a consistent convention.

## Proposed refinement (minimal, but correct)

### A) Decide the workspace root explicitly

Add a required/strongly recommended option:

- --workspace-root /path/to/parent

Default behavior could be:

- workspace root = current working directory (pwd)

This makes it possible to run the script from a parent folder without relying on the script path.

### B) Use the gofr-common Dockerfile.dev for the image

Build/tag a dedicated image, for example:

- IMAGE_NAME=gofr-dev-master:latest (recommended)

Build command (conceptually):

- docker build -t gofr-dev-master:latest -f lib/gofr-common/docker/Dockerfile.dev lib/gofr-common

This uses the correct build context (the gofr-common repo) so Dockerfile.dev can COPY docker/entrypoint-dev.sh.

### C) Mount the whole workspace root once

The simplest approach that meets your "mount all as rw" goal:

- -v "$WORKSPACE_ROOT:/home/gofr/devroot:rw"

Then inside the container, all sibling repos appear at:

- /home/gofr/devroot/gofr-dig
- /home/gofr/devroot/gofr-doc
- etc.

This avoids needing to enumerate projects in the script.

### D) Secrets mount strategy

You have two plausible patterns:

Pattern 1 (per-project secrets dirs, explicit mounts):

- mount gofr-secrets volume to /home/gofr/devroot/<project>/secrets for each project

Pattern 2 (single shared mount):

- mount gofr-secrets volume once, e.g. /home/gofr/devroot/secrets
- projects refer to it via configuration, or you maintain symlinks per project

The repo currently seems to expect per-project secrets directories. If so, pattern 1 will cause less churn.

### E) Container naming

Current CONTAINER_NAME is gofr-dig-dev, which is misleading.

Recommendation:

- CONTAINER_NAME=gofr-dev-master

### F) Keep docker socket support

The gofr-common dev image installs docker cli and has an entrypoint that attempts to fix docker group permissions when /var/run/docker.sock is mounted.

Keeping docker socket mounting in this master container fits your goal of cross-project management.

## Open questions (please confirm so we do not guess)

1) Workspace root

- Where will you run the script from, and what does the directory layout look like?
  Example:
  - /home/gofr/devroot/
    - gofr-dig/
    - gofr-doc/
    - gofr-np/
    - gofr-iq/

A1 - /home/gofr/devroot/

2) Which projects should be mounted

- Is it "everything under workspace root" (mount root once), or only a fixed set of repos?
Fix set of repos as already defined

3) Secrets strategy

- Do you want gofr-secrets mounted into each project at /home/gofr/devroot/<project>/secrets?
  If yes, list the projects that need secrets.
yes each project already has secrets mounted and we will leave that as is

4) Image build behavior

- Should the script auto-build the image if it does not exist, or fail with a helpful message?
  (Auto-build is convenient but does work on first run.)
yes auto build

5) UID/GID behavior

- Should the master container always run as the host uid/gid (like the script does now), or do you prefer staying 1000:1000 and fixing ownership another way?
host uid/gid

6)

Also ensure that Docker is available from inside the master container.

## Next step

Once you answer the questions above, I can propose a concrete spec for the refined script (what flags exist, what it mounts, what it builds), and then implement it.
