# Validation record

Local prerelease validation was run on 2026-08-06 before packaging. The checks are dependency-free. The pinned GitHub Actions workflow is configured to repeat them with Python 3.10 and 3.12 on Ubuntu, Windows, and macOS; this record does not claim those hosted runs passed until the published checks report success.

## Run it locally

From the extracted repository root, first follow [Find the trusted Python path](PYTHON-SETUP.md) to identify one user/host-known canonical absolute Python 3.10+ executable outside the project root. Do not resolve it through PATH or command lookup, do not use a project virtual environment, and reject any path component or final target that is a symlink, junction, or reparse point. Use that same path everywhere below as `<trusted-absolute-python>`.

### Helper safety ceilings

The helper fails closed before unbounded reads or path expansion. These are support ceilings, not performance targets: 33554432 bytes and 500000 LF lines per canonical payload; 33554432 bytes and 100000 blocks per setup/control manifest; 8388608 bytes and 100000 paths per paths-list input; 500000 total path components per list; 4096 UTF-8 bytes and 128 components per normalized relative path; 100000 aggregate scanned directory entries and 16777216 aggregate entry-name bytes per operation; 67108864 bytes for other bounded direct reads; 1073741824 logical bytes per hashed or snapshotted file; and 17179869184 logical bytes across one snapshot. Sparse-file logical size counts. Inventory these sizes before staging and report a clear fail-closed manual/high-impact or unsupported-limit stop instead of retrying or silently omitting files.

```text
<trusted-absolute-python> -I -S -B scripts/validate.py
<trusted-absolute-python> -I -S -B -m unittest discover -s tests -p "test_*.py" -v
```

Then self-test the adapter you intend to install, for example:

```text
<trusted-absolute-python> -I -S -B qwen/.qwen/tempered-tools/tempered_receipt.py self-test
```

Each successful validator run prints a SHA-256 digest of the complete frozen public-file manifest. That digest changes whenever any public byte changes, so the release/CI output—not a self-referential value in this file—is the authoritative run record.

## What the static checks cover

- The exact public-file manifest; unexpected or missing files fail.
- No symlinks, junctions, reparse points, unsupported filesystem objects, Unicode-NFC aliases, or case-folded release-path collisions.
- Strict UTF-8 without BOM, LF-only text, a final LF, balanced Markdown fences, and resolving local links.
- No likely secrets, private machine paths, internal launch language, or executable legacy identifiers.
- Native skill/command frontmatter and disabled implicit invocation for Codex's gated skills.
- Exact Tempered protocol-v2 schema, binding, approval lines, and BRIEF/SETUP/PLAN receipt grammars.
- The trusted-instruction/clean-bootstrap boundary, immutable setup and plan records, status non-authority, artifact-bound launch checks, separate ACTION authority, all-three-digest task/result envelopes, depth-one dispatch, exclusive non-file resources, evidence redaction, and finite ceiling fallback.
- Four byte-identical bundled helpers.

## Adversarial helper tests

The tests exercise:

- 128-bit operating-system CSPRNG nonce shape and uniqueness sampling;
- exact-byte SHA-256 and zero-one-field payload verification;
- rejection of payload mutation, duplicate digest fields, BOM, CRLF, and missing final LF;
- exact manual-save byte comparison;
- order-independent, length-prefixed artifact snapshots and content-drift detection;
- rejection of absolute, drive, UNC/backslash, dot, traversal, shell-expansion, alternate-data-stream, Windows-device, trailing-dot/space, prefix-collision, symlink/junction/reparse, existing-target, and Unicode/case-alias paths;
- confined root-bound preview create/finalize/remove behavior, ACTION-stage consume/replay rejection during a compliant helper lifecycle, and process-crash persistence after an observed successful consume return; and
- mutation fixtures proving that legacy schema/binding/name changes and removal of load-bearing semantic controls make validation fail.

## What this does not prove

Static validation does not prove that:

- a model will obey the prompts;
- a particular installed host/version/account exposes or enforces a documented permission, agent, worktree, vision, browser, persistence, or ceiling feature;
- a repository is trustworthy;
- a receipt is an unforgeable user signature;
- generated code is correct, secure, accessible, fast, or high quality; or
- using multiple agents outperforms a simpler workflow.

The host sandbox, permissions, operating-system controls, source-control protection, and human review remain the enforcement boundary. See [THREAT-MODEL.md](THREAT-MODEL.md).

## First live-host smoke test

1. Use a new disposable project. Do not use an unfamiliar repository in place.
2. Copy exactly one adapter's complete hidden folder, including `tempered-tools`.
3. Restart the host and confirm both entry points are discovered.
4. Run the bundled helper `self-test`.
5. Run Part 1 on a tiny harmless example. Confirm it stops at the exact BRIEF preview.
6. Approve the exact candidate and confirm a receipt appears only after exact-byte write verification.
7. Save the receipt outside the project, start a fresh session, and invoke Part 2 without the receipt in the invocation.
8. Confirm Part 2 issues a placeholder-only receipt challenge before reading additional project authority, checks the received `HELPER_SHA256` independently, and only then recomputes the brief.
9. Stop at the setup preview unless you intentionally want to test setup materialization.

Record the host version, surface, selected/effective model, permission posture, observed ceiling behavior, and every deviation. A documentation claim is not proof that the current installation behaves the same way.
