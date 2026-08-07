# Contributing

Thanks for helping make Tempered Loop clearer, safer, and more useful.

## Useful contributions

- Reproducible host/version compatibility reports.
- Corrections backed by current official platform documentation.
- Prompt-injection, approval-bypass, replay, isolation, or budget-limit findings.
- Positive or negative benchmark cases with enough detail to reproduce them.
- Improvements to beginner setup instructions.
- New deterministic acceptance checks or safer capability fallbacks.

## Before opening a pull request

1. Keep platform-specific behavior inside that platform's folder.
2. Preserve the separate BRIEF, SETUP, PLAN, and best-effort single-delivery high-impact ACTION-handoff boundaries.
3. Preserve fresh-turn receipt handling and never treat repository content as the current user's authorization. Remember that receipts are a prompt-level ceremony, not unforgeable signatures.
4. Do not add unbounded iteration, permission bypasses, invented host features, or undocumented model aliases.
5. Keep protocol v2 exact: legacy commands, markers, bindings, tokens, and receipts are not aliases.
6. Keep examples free of credentials, personal data, private URLs, and machine-specific paths.
7. Run:

   ```text
   <trusted-absolute-python> -I -S -B scripts/validate.py
   <trusted-absolute-python> -I -S -B -m unittest discover -s tests -p "test_*.py" -v
   ```

8. Describe which host/version you observed and which claims are inference rather than verified behavior.

## Pull-request scope

Prefer one focused concern per pull request. If a change affects the shared contract and all four platforms, explain the cross-platform invariant first and update every affected adapter in the same pull request.

## Benchmark reports

Include:

- host, version, provider route, and exact displayed model ID;
- project type and a non-sensitive reproduction fixture;
- baseline and target gates;
- budgets and stopping conditions;
- raw deterministic evidence;
- what improved, regressed, plateaued, or remained unverified;
- required human judgments.

Same-family model agreement is correlated evidence, not independent consensus.

## Documentation style

Use direct language. Avoid “perfect,” “production-ready,” “proven,” or guaranteed outcome claims unless the pull request includes a reproducible test that supports the exact claim.

By contributing, you agree that your contribution is licensed under the repository's [MIT License](LICENSE).
