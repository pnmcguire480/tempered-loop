## What changed

<!-- Describe the smallest complete change. -->

## Why

<!-- State the observed problem or evidence. -->

## Platforms affected

- [ ] Shared contract
- [ ] Claude Code
- [ ] Cursor
- [ ] Codex
- [ ] Qwen Code
- [ ] Documentation/release only

## Integrity checklist

- [ ] Protocol remains `payload_schema: 2` with `tempered-loop-sha256-nonce-v2`; no legacy alias was added.
- [ ] BRIEF, SETUP, PLAN, and ACTION tokens remain exact ID/revision/SHA-256/32-hex-nonce lines.
- [ ] User-carried receipts are still requested in a fresh turn after silent local recomputation.
- [ ] `APPROVED_SETUP.md` and `APPROVED_PLAN.md` remain immutable authority records; mutable `STATUS.md` remains audit-only.
- [ ] Task/result envelopes bind all three payload digests, control digest, artifact snapshot, Git identity, paths, and non-file resources.
- [ ] PLAN approval still cannot authorize a high-impact ACTION.
- [ ] Trusted-instruction and clean-bootstrap limits were not weakened.
- [ ] No unbounded loop, nested delegation, remote launch, permission bypass, secret, or machine-specific path was added.
- [ ] `<trusted-absolute-python> -I -S -B scripts/validate.py` and `<trusted-absolute-python> -I -S -B -m unittest discover -s tests -p "test_*.py" -v` pass.

## Evidence

<!-- Include commands, host/version, exact observed results, and remaining uncertainty. -->
