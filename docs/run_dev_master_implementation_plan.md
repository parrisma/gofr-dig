# run-dev-master.sh implementation plan

Date: 2026-02-19

## Preconditions

- Workspace layout (host): /home/gofr/devroot contains sibling repos:
  - gofr-dig
  - gofr-doc
  - gofr-np
  - gofr-iq
- Docker is available on the host.
- The gofr-dig checkout includes lib/gofr-common with docker/Dockerfile.dev.

## Baseline

1) Record baseline test status for gofr-dig

- Run ./scripts/run_tests.sh with no flags and confirm it passes.

DONE 2026-02-19: 611 passed

## Implementation steps

2) Update lib/gofr-common/scripts/run-dev-master.sh behavior

- Change workspace root resolution:
  - Default workspace root to current working directory.
  - Add --workspace-root to override.
- Change container/image naming:
  - Container name becomes gofr-dev-master.
  - Image name becomes gofr-dev-master:latest.
- Change image build policy:
  - If the image is missing locally, build it automatically.
  - Build must use:
    - Dockerfile: gofr-dig/lib/gofr-common/docker/Dockerfile.dev
    - Context: gofr-dig/lib/gofr-common
- Change mounts:
  - Mount these repos as rw into /home/gofr/devroot/<repo>:
    - gofr-dig
    - gofr-doc
    - gofr-np
    - gofr-iq
  - Provide /home/gofr/devroot/gofr-common by mounting:
    - host: <workspace_root>/gofr-dig/lib/gofr-common
    - container: /home/gofr/devroot/gofr-common
  - Mount gofr-secrets volume into each repo at /home/gofr/devroot/<repo>/secrets.
  - Keep docker socket mount and group-add behavior.
- Keep uid/gid behavior:
  - Run container as host uid:gid when it differs from 1000:1000.
- Networking:
  - Ensure the primary network exists (default gofr-test-net, configurable via --network).
  - Connect container to gofr-net after start.
- Output and error handling:
  - Fail fast if required repos are missing from workspace root.
  - Emit clear cause + recovery messages.
  - Do not truncate logs.

DONE 2026-02-19

3) Validate the script locally (manual verification)

- From /home/gofr/devroot:
  - Run the updated run-dev-master.sh.
  - Confirm the container starts and is running.
  - Exec into the container and verify:
    - /home/gofr/devroot/gofr-dig is present and writable
    - /home/gofr/devroot/gofr-doc is present and writable
    - /home/gofr/devroot/gofr-np is present and writable
    - /home/gofr/devroot/gofr-iq is present and writable
    - /home/gofr/devroot/gofr-common exists and points to the mounted source
    - docker CLI can run (docker info) when socket is mounted

4) Commit/push changes in gofr-common

- Commit the change inside the lib/gofr-common git repo.
- Push to gofr-common origin.

5) Update gofr-dig submodule pointer

- Stage the updated submodule pointer in gofr-dig.
- Commit and push to gofr-dig origin.

## Post-change validation

6) Run gofr-dig full test suite again

- Run ./scripts/run_tests.sh and confirm the suite passes.

## Rollback plan

- If the updated script breaks expected workflows:
  - Revert the gofr-common commit (new follow-up commit, no history rewriting).
  - Update gofr-dig submodule pointer back to the prior commit (new follow-up commit).

## Completion criteria

- The master container can be launched from /home/gofr/devroot.
- It auto-builds gofr-dev-master:latest from the specified gofr-common Dockerfile.dev when missing.
- It mounts the selected repos as rw and mounts gofr-common source at /home/gofr/devroot/gofr-common.
- gofr-secrets is mounted into each selected repo secrets directory.
- Docker CLI works in-container when docker.sock is mounted.
- gofr-dig tests pass before and after.
