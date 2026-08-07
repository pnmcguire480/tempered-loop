# Threat model

Tempered Loop is a workflow harness, not a security boundary. The host sandbox, permission controls, operating-system account, source-control protections, and human review are the real boundaries.

## The rule that matters most

A prompt cannot demote instructions that its host has already loaded as trusted instructions. Treat an untrusted repository as data, never as an active agent workspace.

If an unfamiliar repository contains `CLAUDE.md`, `AGENTS.md`, `QWEN.md`, project rules, skills, agents, settings, hooks, MCP configuration, or similar host instructions, opening that repository normally may activate them before Tempered Loop can inspect them. Telling the model to "ignore" those files does not reliably make them inert.

Use one of these trust modes:

1. **New empty project** — create a new empty folder, install one Tempered Loop adapter, then begin.
2. **Trusted in place** — use the repository normally only when you own it or have already reviewed its host instructions and configuration.
3. **Unfamiliar or hostile** — do not open the target as the active agent workspace. Inspect a sanitized, read-only snapshot from a separate clean bootstrap folder.

If you cannot establish one of those modes, stop. Tempered Loop does not make an untrusted repository safe merely by being copied into it.

## Clean bootstrap for an unfamiliar repository

Clean bootstrap refusal rule: stop and use non-agent static inspection when target instruction discovery cannot be proven disabled.

The safe pattern is the same on every host:

1. Make a new empty folder outside the target repository.
2. Install exactly one Tempered Loop adapter in that empty folder.
3. Start the host in the empty folder and verify which instructions, tools, settings, and integrations it loaded.
4. Use a person or trusted external static tool to make a read-only snapshot of the target's relevant source files. Exclude secrets, credentials, private data, dependency caches, build output, host instruction files, hooks, settings, MCP configuration, and executable automation.
5. Copy that snapshot into the clean root as inert read-only data. Do not mount it, cross a filesystem/device boundary, or make the target repository the active workspace; nested mounts are unsupported in v0.1.0.
6. Run intake as an audit and record how the snapshot was produced, what was excluded, and why it is trusted as data.
7. Review the resulting plan yourself before applying any recommendation to the real repository.

Do not ask the agent running inside the target repository to sanitize that same repository. By then, target instructions may already be active.

### Claude Code

Start Claude Code in the clean folder. Confirm that target `CLAUDE.md`, `AGENTS.md`, `.claude/settings*`, hooks, skills, agents, and MCP configuration were not loaded. Inspect only the sanitized read-only snapshot. If you cannot observe that separation, this mode is unsupported.

### Cursor

Open a new Cursor window on the clean folder. Confirm the target project's rules, agents, skills, environments, automations, hooks, and integrations are not active. Do not open the target as the workspace until those files have been reviewed outside the agent session.

### Codex

Start Codex with the clean folder as the working directory and a read-only or workspace-limited sandbox. Confirm no target `AGENTS.md` chain or target configuration applies. Treat the sanitized snapshot as data. Stop if target instructions become operative.

### Qwen Code

Start Qwen Code in the clean folder. Confirm target `QWEN.md`, `AGENTS.md`, commands, agents, settings, hooks, review rules, and integrations were not loaded. Use Plan/Ask posture and inspect only the sanitized read-only snapshot.

## What the protocol protects

Protocol v2 binds each approved BRIEF, SETUP, PLAN, and high-impact ACTION to exact bytes, an ID, a revision, a SHA-256 digest, and a fresh nonce. Fresh sessions recompute the current artifact before accepting a user-carried receipt. This helps expose stale, copied, or modified approval material in a compliant run.

Receipts are not passwords or unforgeable signatures. Their fields are largely recomputable from approved repository files. The authority signal is the host observing the receipt in a fresh current-user turn and refusing to reconstruct it itself. A malicious or noncompliant host can bypass that prompt-level ceremony.

It does **not** protect against a compromised host, malicious executable tools, stolen user messages, unsafe operating-system permissions, a model ignoring its prompt, or a user approving content they did not review.

## Preview scratch boundary

Digest-bound approval needs a deterministic tool to read the exact candidate and path lists before the project target may be written. The helper therefore creates one random private preview directory in the operating-system temporary directory for each active revision. No project-local staging fallback is allowed. The host uses a structured file-write channel, never shell interpolation or redirection. Only the fixed candidate, path-list, and digest-input filenames are allowed, and the helper finalizes only the reserved digest field. After approval, the target must match the staged bytes exactly before the helper removes only its own fixed entries without recursive deletion.

This scratch file is a bounded exception to the no-preapproval-project-write rule, not a cryptographic enclave. Operating-system administrators, malware, a compromised host, or unsafe temp-directory permissions can still observe or change it. Exclude secrets and regulated data from previews. If the exact temp path cannot be separately approved, confined outside the project, re-read, verified, and removed, stop. A failed cleanup is reported with its exact path rather than hidden.

## Other expected risks

- Builders and critics using the same model remain correlated; a second opinion is not independent proof.
- Worktrees separate Git files, not ports, databases, caches, credentials, external services, or production state. The generated `RESOURCES.md` must assign those explicitly.
- Tests, builds, package managers, and browsers may execute project code or contact external services.
- Logs and evidence can leak secrets. Store redacted evidence; retain restricted raw evidence only when necessary, with its path and digest recorded.
- Remote/cloud execution is unsupported in this public preview because the kit cannot prove equivalent receipt custody, instruction isolation, and permission enforcement there.
- Nested agent delegation is unsupported. The coordinator may dispatch depth-one specialists only.
- Concurrent top-level Tempered chat/process sessions against one canonical root are unsupported in this public preview. Use exactly one intake/compiler/planner/launcher at a time and wait for its terminal stop plus stage cleanup before opening the next. The helper does not provide a cross-process root lease, so suspected overlap requires a stop and human reconciliation. Depth-one specialists remain inside the single coordinator.
- Multi-file setup materialization is not transactional in public preview v0.1. A crash or byte-normalizing writer can leave partial host controls. The protocol writes host-active definitions last and then fails closed: no receipt, retry, or in-agent cleanup. Close the host and quarantine the exact reported same-attempt files with a trusted out-of-agent tool before starting a wholly new revision.
- High-impact ACTION auto-execution is unsupported in v0.1.0. After approval, the only permitted local tool calls are exact verified-helper binding checks and root-bound `preview-consume`; after consume succeeds there are zero further tool/process/shell/network/credential/preflight/rollback/reconciliation calls. The agent emits one exact chat/output manual handoff labeled `NOT EXECUTED` and `HANDED_OFF/EXECUTION_UNKNOWN`. Consumption provides best-effort single-delivery only during a compliant, untampered helper lifecycle. It is not a durable protected replay ledger: the same operating-system principal can reverse or recreate stage state, so human idempotency and replay control remain required. Human execution occurs outside Tempered Loop observation/enforcement, may be duplicated, and needs later human-attested evidence. Ambiguous handoff delivery is not retried.
- High-impact actions are manual-only manual handoffs in v0.1.0. Zero agent process, shell, network, secret-provider, credential, preflight, side-effect, rollback, or reconciliation calls are permitted. Exact approval authorizes only the digest-bound, stage-bound chat handoff; root-bound `preview-consume` runs immediately before output labeled `NOT EXECUTED` and `HANDED_OFF/EXECUTION_UNKNOWN`. A human executes out-of-agent, outside kit enforcement. A crash or ambiguous delivery gets no cleanup and needs a new revision; PLAN never authorizes it, and never infer completion without later human-attested evidence. Delivery is best-effort single-delivery during a compliant, untampered helper lifecycle, not a security guarantee or durable replay protection. The same OS principal can reverse or recreate stage state, so human idempotency and replay controls are required because duplicate execution may occur.
- A digest proves which bytes were approved, not that a human understood them. Every BRIEF records approval-payload byte, line, and embedded-file ceilings. Exceeding any ceiling blocks approval; summaries, truncation, hidden attachments, and hash-only consent are invalid. The complete payload plus deterministic index and high-risk sections must remain reviewable.
- Public preview v0.1.0 has no helper-mediated atomic `CREATE_NEW` materializer. Path validation immediately before each generic host write cannot close a concurrent create/overwrite race. The root must remain quiescent through verification and receipt; no-overwrite is procedural/best-effort, and any unexpected occupancy/drift after the first write enters `INVALID/PARTIAL` rather than overwriting or cleaning up.
- Helper reads, manifests, paths, directory scans, and snapshots are fail-closed and bounded: 32 MiB/500000 LF lines per payload; 32 MiB/100000 blocks per manifest; 8 MiB/100000 paths/500000 total components per paths list; 4096 UTF-8 bytes/128 components per path; 100000 directory entries/16 MiB entry-name bytes per operation; 64 MiB for other bounded direct reads; 1 GiB logical size per hashed/snapshotted file; and 16 GiB logical size per snapshot. Sparse logical size counts. Larger projects/artifacts require an explicitly reduced inventory or are a manual/high-impact unsupported stop; limits must be surfaced before expensive staging, never worked around by omission.
- Preview scratch is not an enclave. POSIX requires a mode-0700 stage parent. On Windows, TEMP and LOCALAPPDATA-derived location checks establish self-consistency only; they do not verify DACL ownership or secrecy. A trusted per-user TEMP location is a host precondition, shared temporary storage is unsupported, and sensitive raw secrets never belong in staged payloads.
- Low-impact automatic execution is allowed only when the host actually enforces no network, no secrets, no external service, no out-of-root writes, and a bounded local sandbox. It also requires structured argv or verified platform-native literal quoting, canonical cwd, exact stdin/`NONE`, a scrubbed allowlisted environment when supported, a finite timeout, local bounded reversible effects, current snapshot/rollback evidence, and no multi-link/cross-device/mount-ambiguous writable path. On any uncertainty, reclassify the operation as high-impact and route it to the manual ACTION handoff.

## Reporting a security problem

Do not include secrets or a working exploit in a public issue. Follow [SECURITY.md](SECURITY.md).
