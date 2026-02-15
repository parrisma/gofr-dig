# Trivy Remediation Options

Source report: [artifacts/trivy-report.json](../artifacts/trivy-report.json)

## Current Risk Snapshot
- Policy result: `fail`
- Severity counts: `HIGH=18`, `CRITICAL=0`
- Unique fail reasons in report: 13

## Priority 1 (Most impact, lowest risk)
1. Rebuild on latest base image digest
   - Target finding: `CVE-2026-0861` (`libc-bin`, `libc6`, currently no fix in your image)
   - Action: update base image tag/digest and rebuild regularly (scheduled rebuilds).
   - Why: OS CVEs are usually cleared by distro package refreshes first.

2. Move `pyright[nodejs]` out of runtime dependencies
   - Targets likely affected: Node.js vulnerabilities (`tar`, `glob`, `@isaacs/brace-expansion`).
   - Action: keep `pyright[nodejs]` only in dev/test dependency groups, not `[project].dependencies` for production image builds.
   - Why: removes Node package tree from production image attack surface.

3. Update direct Python packages with fixed versions
   - `urllib3` → `2.6.3`
   - `cryptography` → `46.0.5`
   - `python-multipart` → `0.0.22`
   - `wheel` → `0.46.2` (if present in runtime image)

## Priority 2 (Compatibility-aware updates)
4. Resolve `starlette` vulnerability (`CVE-2025-62727`)
   - Current: `starlette==0.45.3`
   - Fixed: `0.49.1`
   - Action: upgrade `fastapi` + `starlette` together to a compatible pair, then run full regression.
   - Why: direct `starlette` bump can break FastAPI compatibility if versions mismatch.

5. Update transitive Python dependency `jaraco.context`
   - Target finding: `CVE-2026-23949`
   - Action: identify parent package pulling it in (`uv tree`), then bump parent to version that includes `jaraco.context>=6.1.0`.

## Priority 3 (Policy and process hardening)
6. Add temporary risk-acceptance workflow for no-fix CVEs
   - Applies to: `CVE-2026-0861` until distro fix is available.
   - Action: keep `ignore_unfixed=false` for default policy, but allow explicit time-bound exception list with owner + expiry for blocked releases.

7. Add CI diff gate for vulnerability trend, not only fail/pass
   - Action: fail on new HIGH/CRITICAL increases and report delta vs previous baseline.
   - Why: prevents regressions while remediation work is ongoing.

8. Deduplicate repeated findings before ticketing
   - Some CVEs appear multiple times across targets/packages.
   - Action: create tickets by unique tuple `(CVE, package_name)` to avoid duplicated work.

## Suggested Execution Order
1. Base image refresh + rebuild.
2. Remove runtime Node dependency footprint (`pyright[nodejs]` from prod deps).
3. Upgrade direct Python packages (`urllib3`, `cryptography`, `python-multipart`, `wheel`).
4. FastAPI/Starlette compatibility upgrade.
5. Re-scan and compare counts.

## Definition of Done
- `HIGH=0` or only approved temporary exceptions remain.
- No untracked `no-fix-available` findings.
- Scan policy returns `pass` for release images.
