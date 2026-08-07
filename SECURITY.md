# Security policy

Tempered Loop is an experimental workflow kit, not a security sandbox. The installed host's permissions, filesystem isolation, network controls, and human review remain the enforcement boundary.

Read [THREAT-MODEL.md](THREAT-MODEL.md) before testing an unfamiliar repository. A prompt cannot neutralize instructions the host already loaded as trusted, and a receipt is not an unforgeable signature.

## Report a vulnerability privately

Do not publish a working approval bypass, receipt replay, credential exposure, path escape, destructive-action path, or prompt-injection exploit in a public issue before maintainers have had a reasonable chance to review it.

Use GitHub's private vulnerability reporting feature for this repository. If that feature is unavailable, open a minimal issue that says a private security report is needed without including exploit details or sensitive data.

Include:

- affected platform and files;
- host/version/provider surface;
- exact preconditions;
- minimal non-sensitive reproduction steps;
- expected and observed behavior;
- impact and suggested mitigation, if known.

## Never include

- API keys, access tokens, cookies, credentials, or private keys;
- personal, regulated, or production data;
- private repository contents or URLs;
- destructive payloads targeting systems you do not own.

## Supported versions

Security fixes are applied to the latest release and the default branch. Host behavior changes quickly, so older tags may retain obsolete capability assumptions.

## Scope

Security-relevant findings include approval/receipt bypass, digest ambiguity or circularity, path traversal, symlink/junction escape, cross-project writes, unsafe permission escalation, secret exposure, prompt-injection authority inversion, stale task-envelope acceptance, PLAN-to-ACTION authority confusion, and uncontrolled remote execution.
