# Qwen3.8 Max Tempered Kit

This kit installs two user-invoked Qwen Code commands:

- `/tempered:intake` interviews you for either a new project or an audit/revamp and produces an approved project brief.
- `/tempered:compile` converts that brief into project-specific agents, acceptance gates, a runbook, and the final bounded execution prompt.

The compiler deliberately stops before executing the project.

## Read this before you copy anything

Use the kit directly only in a new project or a repository whose instructions you already trust. A prompt cannot demote `QWEN.md`, `AGENTS.md`, commands, agents, settings, review rules, MCP configuration, or other instructions Qwen Code has already loaded from a hostile repository. For an unknown or untrusted repository, stop and use the clean-root procedure in the [threat model](../THREAT-MODEL.md). Remote and cloud execution are unsupported in this public preview.

This release uses the incompatible Tempered protocol v2: `payload_schema: 2` and `approval_binding: tempered-loop-sha256-nonce-v2`. Legacy v1 commands, payloads, approvals, and receipts are invalid; do not install both versions side by side. See the [migration guide](../MIGRATION.md).

## Tiny-kid setup

Think of the `.qwen` folder as a little instruction box for Qwen Code. Think of a preview as a practice drawing: Qwen makes it in the computer's temporary drawer, shows it to you, and only copies it into your project after you say the exact approval sentence.

1. Open this `qwen` folder.
2. Copy the whole `.qwen` folder into the big folder for the project you want to make or fix.
3. Close and reopen Qwen Code in that project.
4. Type `/approval-mode default`. Keep **Ask Permissions** on. Qwen's Plan mode cannot run the little checking tool, so use Plan only when Qwen is talking and thinking without running anything. Never choose Auto-Edit or YOLO.
5. Type `/tempered:intake` and answer the small groups of questions. Qwen first fingerprints the helper with a separate built-in hash check, then uses it. Approve only the exact helper and temporary-file requests it explains. The temporary path must be outside your project; if Qwen cannot use or clean that exact place, stop.
6. Qwen puts the exact brief in that temporary drawer, locks its fingerprint, checks it, and shows every byte. Nothing in your project is written yet.
7. Read the brief. If it is right, copy the whole exact `APPROVE TEMPERED BRIEF ... SHA256:... NONCE:...` sentence into a new message with no extra words. Qwen checks the same complete marker-wrapped temporary copy again, copies those exact bytes into `PROJECT_BRIEF.md`, compares them byte-for-byte, and cleans the temporary drawer.
8. Save the `TEMPERED BRIEF RECEIPT ...` somewhere outside the project, such as your private notes. Start a fresh Qwen Code chat in the same project and type `/tempered:compile`.
9. When asked, paste that saved receipt in a new message. Qwen repeats the temporary-preview checks for the setup. Read every proposed file. If it is right, send the exact `APPROVE TEMPERED SETUP ... SHA256:... NONCE:...` sentence alone. Save the new `TEMPERED SETUP RECEIPT ...` outside the project too.
10. Open `.qwen/tempered/RUNBOOK.md` and follow it one step at a time. It repeats the safe preview pattern for the execution PLAN and any dangerous ACTION: temporary copy, fingerprint, display, exact approval, and recheck. A PLAN is copied and compared before cleanup. In v0.1.0 an ACTION permits only a best-effort single chat-handoff delivery labeled `NOT EXECUTED`; Qwen never runs the high-impact action, and human idempotency remains required.
11. If you correct a preview or say `STOP`, Qwen must clean the old temporary copy and make a fresh nonce before showing another. If cleanup fails, the run stops and tells you the leftover path.

If the commands do not appear, restart Qwen Code and make sure `.qwen` is at the top of the project. If Windows does not show dot-folders, use **View > Show > Hidden items** in File Explorer.

## Why this is a Qwen Code setup

The Tempered workflow needs a host that can inspect files, run tools, create separate agent contexts, persist goals, and enforce permissions. A raw `qwen3.8-max` chat can discuss the roles, but it cannot provide the same real orchestration.

## Install in one project — recommended

Copy the kit's **whole `.qwen` folder** into the root of the project you want to create or audit. The bundled helper must be copied with the commands:

```text
<project-root>/.qwen/commands/tempered/intake.md
<project-root>/.qwen/commands/tempered/compile.md
<project-root>/.qwen/tempered-tools/tempered_receipt.py
```

Project commands are easy to review, can be version-controlled, and override same-named personal commands.

## Personal installation

This public preview supports project installation only. A personal command copy by itself is insufficient because the prompts require the project-local helper at `.qwen/tempered-tools/tempered_receipt.py`. Copy and review the whole adapter folder separately for each trusted project. Do not place credentials in the commands, helper, or generated project files.

## Use

1. Confirm the repository is new/trusted, or complete the clean bootstrap in the [threat model](../THREAT-MODEL.md).
2. Start Qwen Code in the intended project root.
3. Run `/doctor` and resolve environment/authentication errors.
4. Follow [Find the trusted Python path](../PYTHON-SETUP.md) to identify one canonical full Python 3.10+ executable path outside the project without PATH or command lookup. Reject project virtual environments and any symlink, shortcut, junction, or reparse-point path. Resolve `.qwen/tempered-tools/tempered_receipt.py` under the canonical project root to its full non-link path and keep it as `<canonical-absolute-helper-path>`. Use those same two paths for every helper call. Before Qwen uses the project helper, compute those exact helper bytes' SHA-256 with an independent native host primitive or the same trusted absolute interpreter and record it as `helper_sha256`; then run:

   ```text
   <trusted-absolute-python> -I -S -B <canonical-absolute-helper-path> self-test
   ```

   Stop if the independent hash cannot be produced or the check does not pass. The approved BRIEF and SETUP bind that exact helper digest; each fresh session compares it before invoking the project helper. This catches accidental drift or a mixed kit, not a compromised host. Qwen must never calculate, invent, or visually guess a nonce or SHA-256 value.
5. Run `/model`. As of **2026-08-06**, the exact official ID is `qwen3.8-max`. Alibaba documents access through **Personal Token Plan**, **Team Token Plan**, and **Model Studio pay-as-you-go**; it is absent from **Coding Plan**. Require `/model` to show that exact ID. If it is unavailable, stop and fix the route; do not relabel another model or the former preview name as Qwen3.8 Max.
6. Require `modelFallbacks` to be absent or empty. A fallback list is allowed only when you explicitly approve a same-family list, and every result must record the effective model that actually ran.
7. Use `/effort high` for intake/compilation; use `xhigh` for the execution run only when the additional usage fits the approved budget.
8. Use `/approval-mode plan` only for conversation and logical planning that run no shell command. Switch deliberately to `/approval-mode default` with Ask Permissions for each exact helper, temporary-file, repository-read, hash, or approved write request. Never use Auto-Edit or YOLO.
9. Invoke `/tempered:intake` and answer the questions. You may add a hint, for example:

   `/tempered:intake audit and revamp the project in the current directory; preserve its public API`

10. Qwen uses helper `preview-create --root <canonical-project-root> ...`, a structured exact-byte write, root-bound `preview-finalize`, and root-bound direct-stage `verify-payload` to build and display the BRIEF in a disclosed operating-system temp stage outside that root. Every later staged command receives and revalidates the same canonical root. No project artifact or source file may exist yet. Review it; if correct, send only `APPROVE TEMPERED BRIEF <id> R<n> SHA256:<64hex> NONCE:<32hex>`. Qwen must reverify the unchanged stage, copy its exact bytes into the new target, compare raw bytes, and run root-bound `preview-remove` before emitting the receipt.
11. Save the `TEMPERED BRIEF RECEIPT ...` outside the repository. Start a fresh Qwen Code session in the same project root and invoke `/tempered:compile`. Part 2 asks with a placeholder before reading additional project authority. After you send the saved receipt alone, it independently checks `HELPER_SHA256` and only then recomputes the brief; it never trusts a repository copy by itself.
12. Compilation repeats the same temp-only preview lifecycle for the exact path-sorted SETUP manifest. Each file block is `@@FILE <VERIFY_EXISTING-or-WRITE_NEW> <path>`, `@@BYTES <decimal>`, exact bytes, then `@@END <path>`; the byte count makes marker-looking file content inert. `VERIFY_EXISTING` binds the approved brief and installed helper without rewriting them; `WRITE_NEW` binds generated files. Review topology, permissions, ownership, gates, and budget. If correct, send only `APPROVE TEMPERED SETUP <id> R<n> SHA256:<64hex> NONCE:<32hex>`. Save the full emitted receipt outside the repository; it ends with `CONTROL_SHA256:<64hex>`.
13. Follow `.qwen/tempered/RUNBOOK.md` to prepare the execution PLAN. Plan mode is for no-shell thinking only; use Default/Ask Permissions for its exact reads, hashes, helper calls, and temp staging. Present the saved setup receipt only when requested. Approve only with `APPROVE TEMPERED PLAN <id> R<n> SHA256:<64hex> NONCE:<32hex>`, then save the full artifact-bound PLAN receipt outside the repository. The launcher runs one authenticated local cycle at a time; the compiler itself never starts the project.

If the commands do not appear in slash-command completion after copying them, restart Qwen Code. If generated agents are not visible, check `/agents manage` and restart before running the project.

The v2 receipt lines are exactly:

```text
TEMPERED BRIEF RECEIPT <id> R<n> SHA256:<64hex> NONCE:<32hex> HELPER_SHA256:<64hex>
TEMPERED SETUP RECEIPT <id> R<n> SHA256:<64hex> NONCE:<32hex> HELPER_SHA256:<64hex> CONTROL_SHA256:<64hex>
TEMPERED PLAN RECEIPT <id> R<n> SHA256:<64hex> NONCE:<32hex> HELPER_SHA256:<64hex> CONTROL_SHA256:<64hex> ARTIFACT_SHA:<64hex> GIT:<40-or-64hex-or-NOT_GIT>
```

No v1 or legacy receipt is accepted by v2. PLAN approval also does not authorize destructive, production, deploy, publish, purchase, migration, secret-data, network, external-message, permission, scope, or budget effects. Each needs a separate ACTION payload and fresh approval. High-impact actions are manual-only manual handoffs in v0.1.0. The agent never executes them and makes no process call. Exact approval authorizes only the digest-bound, stage-bound chat handoff; root-bound `preview-consume` runs immediately before output labeled `NOT EXECUTED` and `HANDED_OFF/EXECUTION_UNKNOWN`. A human executes out-of-agent, outside kit enforcement. A crash or ambiguous delivery gets no cleanup and needs a new revision; PLAN never authorizes it, and completion is never inferred without later human-attested evidence. Delivery is best-effort single-delivery during a compliant, untampered helper lifecycle, not a security guarantee or durable replay protection. The same OS principal can reverse or recreate stage state, so human idempotency and replay controls are required because duplicate execution may occur.

A receipt is a prompt-level fresh-user-turn ceremony, not a password or cryptographic signature; its fields are largely recomputable. A compromised or noncompliant host can bypass it. Host permissions, sandboxing, and your review remain the security boundary.

## What the temporary preview is allowed to do

For each BRIEF, SETUP, PLAN, or ACTION revision, the helper creates one random stage directory directly under the operating system's temp directory and prints its absolute `candidate.payload` path. POSIX requires its mode-0700 parent; Windows requires a trusted per-user TEMP location because the helper does not prove DACL privacy. Before approval, this disclosed stage is the only writable area. It may contain only the helper sentinel, `candidate.payload`, and the narrowly allowed `proposed-paths.txt`, `snapshot-paths.txt`, or `digest-input.bin` auxiliaries needed for that phase. There may be no project artifact or source write.

Qwen must place exact bytes there with its structured file-write tool. Candidate text, path lists, and digest inputs must never be passed through shell interpolation, redirection, a here-document, an environment variable, command arguments, or an improvised script. Root-bound `preview-finalize` changes the zeroed digest field; for ACTION it also replaces the 32-zero `preview_stage_token` before hashing. Root-bound direct-stage `verify-payload` checks it. After approval Qwen rechecks the unchanged stage. BRIEF, SETUP, and PLAN are copied to their exact target and compared before root-bound `preview-remove`; ACTION consume permits one best-effort terminal chat-handoff delivery and never agent execution. It is not a durable same-principal replay ledger, so human idempotency remains required. A correction or `STOP` cleans the old active stage and rotates the nonce. An ambiguous consumed handoff stage is preserved and disclosed. If temp access or required cleanup is denied, the workflow stops and reports the path.

Inside the project, every authority/control read is root-bound: Qwen supplies the canonical project root and normalized relative path together, and the helper rejects links, aliases, root drift, and non-regular files. A bare absolute project path is not accepted. The only direct absolute path is the helper-issued temp candidate.

## Recommended permission posture

- **Any helper, temp, read, hash, or approved write command:** `/approval-mode default` with Ask Permissions; approve only the exact operation.
- **Logic-only discussion:** `/approval-mode plan`; Qwen Plan runs no shell commands.
- **Critics and explorers:** Plan only if they require no shell; otherwise Default/Ask Permissions with an exact read-only tool allowlist.
- **Destructive actions, production, deployment, publishing, migrations, secrets, external messages, and scope/budget expansion:** always require human approval and a manual-only ACTION handoff; Qwen never executes them in v0.1.0.
- **Auto-Edit and YOLO:** deliberately unsupported by this kit.

## What Part 2 generates

```text
.qwen/tempered/
  PROJECT_BRIEF.md        immutable exact marker-wrapped Part 1 stage
  APPROVED_SETUP.md       immutable exact marker-wrapped approved setup stage
  APPROVED_PLAN.md        exact staged PLAN copied only after approval
  ACCEPTANCE.md
  EXECUTION_PROMPT.md
  RUNBOOK.md
  STATUS.md
  RESOURCES.md
  CONTROL_BUNDLE.manifest
  QWEN_SNIPPET.md

.qwen/agents/
  tempered-explorer.md
  tempered-builder-<track>.md
  tempered-critic.md
  tempered-verifier.md
  tempered-integrator.md
```

Execution planning later creates `.qwen/tempered/APPROVED_PLAN.md` only after exact PLAN approval. It is not a Part 2 output and is authenticated by the artifact-bound PLAN receipt.

`CONTROL_BUNDLE.manifest` is a headerless, path-sorted manifest using the same block grammar, with every verb exactly `VERIFY_EXISTING`. It includes the installed helper, approved brief, immutable generated controls, and generated agents. It excludes itself, mutable `STATUS.md`, and separately receipt-authenticated approved SETUP/PLAN payloads. Its SHA-256 is stored only in the approved authority and receipts. Fresh sessions independently check `helper_sha256`, then use root-bound mechanical setup and bundle verification.

The exact builder tracks and agent models are derived from Part 1. Parallel writers must use isolated worktrees when available; otherwise the generated workflow runs them sequentially. One integrator owns shared or coupled changes.

## Qwen-specific cautions

- This public preview is coordinator-only and depth one. Qwen Code's canonical delegation tool is `agent`; every generated child declares exact frontmatter `disallowedTools: [agent]`. Set `model.maxSubagentDepth: 1` too when the installed build exposes it. A child must never dispatch another agent.
- Every task and result envelope carries all three payload digests, their IDs/revisions, helper and control-bundle digests, artifact snapshot, Git identity, allowed paths, and resource ownership. Stale or incomplete envelopes are rejected.
- The artifact snapshot covers only the complete explicitly listed inventory. For each listed regular file it binds normalized path, regular-file type, portable executable-mode value, and exact bytes; Git identity is separate. Omitted and ignored files are disclosed, not falsely claimed as covered. Unexplained new files or dirty-state drift stop the run.
- Normal approved in-scope outputs become the current state of that one cycle; they do not force a replan halfway through it. Because those bytes/modes changed, any later cycle needs a newly reviewed PLAN, snapshot, and receipt.
- Do not use disposable forks for critical decisions. Fork results are visible in the UI but are not automatically returned to the parent conversation. Forks share the working directory, lack writer isolation, and only further forks—not every other form of work—are prohibited.
- Qwen Code's `/goal` is a persistence controller, not automatically a hard budget ceiling. This kit defaults to one approved cycle at a time. It offers Goal only after state-preservation behavior and an applicable host-enforced ceiling are both observed; the user-carried receipt is never embedded in `/goal` arguments.
- Qwen Code's `/review` is an optional final code-diff gate. Its effort-specific finder and later verification fan-out can be large and can change, so use it only after observing the current call budget and confirming that it fits the approved tokens, time, cost, concurrency, and permissions. It does not replace runtime, screenshot, interaction, performance, or end-to-end testing.
- Native vision availability for a `qwen3.8-max` route may depend on the current service. The generated runbook requires a smoke test and can fall back to an explicitly configured vision-capable critic.
- Remote/cloud execution is unsupported in this public preview, even if the installed Qwen surface exposes it.

## Official references

- Qwen Code custom commands: https://qwenlm.github.io/qwen-code-docs/en/users/features/commands/
- Qwen Code subagents: https://qwenlm.github.io/qwen-code-docs/en/users/features/sub-agents/
- Qwen Code fork behavior update: https://qwenlm.github.io/qwen-code-docs/en/blog/updates/weekly-update-2026-07-23/
- Qwen Code memory and QWEN.md: https://qwenlm.github.io/qwen-code-docs/en/users/features/memory/
- Qwen Code project settings and permissions: https://qwenlm.github.io/qwen-code-docs/en/users/configuration/settings/
- Qwen Code approval modes: https://qwenlm.github.io/qwen-code-docs/en/users/features/approval-mode/
- Qwen Code worktrees: https://qwenlm.github.io/qwen-code-docs/en/users/features/worktree/
- Qwen Code multi-agent review: https://qwenlm.github.io/qwen-code-docs/en/users/features/code-review/
- Qwen Code `/goal`: https://qwenlm.github.io/qwen-code-docs/en/blog/updates/weekly-update-2026-05-21/
- Alibaba model catalog: https://help.aliyun.com/en/model-studio/models
- Qwen Code weekly update, 2026-07-09: https://qwenlm.github.io/qwen-code-docs/en/blog/updates/weekly-update-2026-07-09/
- Qwen Code model and fallback settings: https://qwenlm.github.io/qwen-code-docs/en/users/configuration/settings/
- Coding Plan availability: https://help.aliyun.com/en/model-studio/coding-plan
- Alibaba personal Token Plan: https://help.aliyun.com/en/model-studio/token-plan-personal-overview
- Alibaba Team Token Plan: https://help.aliyun.com/en/model-studio/token-plan-team-overview
