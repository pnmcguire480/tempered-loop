# Claude Code Tempered Kit

This is the Claude Code-native two-part Tempered setup.

- `/tempered-intake` interviews you about a new project or an audit/revamp and saves one approved project brief.
- `/tempered-compile` turns that brief into acceptance gates, bounded specialist agents, a runbook, a status ledger, and the final execution prompt.

Neither part performs the project. Real work has a separate exact plan approval and receipt gate.

## Read this before you copy anything

Use the kit directly only in a new project or a repository whose instructions you already trust. A prompt cannot demote `CLAUDE.md`, settings, hooks, skills, MCP configuration, or other instructions Claude Code has already loaded from a hostile repository. For an unknown or untrusted repository, stop and follow the clean-bootstrap procedure in the [threat model](../THREAT-MODEL.md). Remote and cloud execution are unsupported in this public preview.

This release uses the incompatible Tempered protocol v2: `payload_schema: 2` and `approval_binding: tempered-loop-sha256-nonce-v2`. Old commands, payloads, approvals, and receipts are invalid; do not install v1 and v2 side by side. See the [migration guide](../MIGRATION.md).

## Setup for a five-year-old

Think of `.claude` as a box of instructions for your robot helper.

1. Open this `claude` folder.
2. Copy the whole `.claude` folder.
3. Paste it into the big folder for the project you want to work on.
4. Open Claude Code in that project.
5. Make a plain text note somewhere **outside** the project. Call it `MY TEMPERED RECEIPTS.txt`.
6. Type `/tempered-intake` and press Enter.
7. Answer the small groups of questions.
8. Read the proposed brief. If it is right, copy Claude's long `APPROVE TEMPERED BRIEF ... SHA256:... NONCE:...` sentence into a new message all by itself.
9. When Claude prints a `TEMPERED BRIEF RECEIPT ...` line, copy it into your outside note.
10. Start a fresh Claude Code chat in the same project and type `/tempered-compile`.
11. When it asks, paste the saved TEMPERED BRIEF RECEIPT by itself.
12. Read the full setup preview. If it is right, copy the long `APPROVE TEMPERED SETUP ... SHA256:... NONCE:...` sentence into a new message all by itself.
13. When Claude prints a `TEMPERED SETUP RECEIPT ...` line, save it in your outside note too.
14. Open `.claude/tempered/RUNBOOK.md` and follow its numbered steps. It asks once more before any project work.

Do not store your only receipt copy inside the project. A receipt found in a project file is an audit copy, not permission.

If `/tempered-intake` is missing, close and reopen Claude Code. If Windows hides `.claude`, turn on **View → Show → Hidden items** in File Explorer.

## Install in one project

Copy the kit's **whole `.claude` folder**, not only the skills. The bundled helper must be copied with them, so these files exist:

```text
<project-root>/.claude/skills/tempered-intake/SKILL.md
<project-root>/.claude/skills/tempered-compile/SKILL.md
<project-root>/.claude/skills/tempered-compile/reference.md
<project-root>/.claude/tempered-tools/tempered_receipt.py
```

This public preview supports the project installation above. Copying only the skills to a personal directory is insufficient because the prompts require the project-local helper at `.claude/tempered-tools/tempered_receipt.py`.

## Before first use

1. Confirm the repository is new/trusted, or complete the clean bootstrap in the [threat model](../THREAT-MODEL.md).
2. Start Claude Code in the intended local project root.
3. Run `claude --version` outside the chat, then `/doctor`, `/status`, and `/model` inside it. Record the exact values; do not guess a model alias or capability.
4. Follow [Find the trusted Python path](../PYTHON-SETUP.md) to identify one canonical full Python 3.10+ executable path outside the project without PATH or command lookup. Reject project virtual environments and any symlink, shortcut, junction, or reparse-point path. Resolve `.claude/tempered-tools/tempered_receipt.py` under the canonical project root to its full non-link path and keep it as `<canonical-absolute-helper-path>`. Use those same two paths for this read-only check and every later helper call:

   ```text
   <trusted-absolute-python> -I -S -B <canonical-absolute-helper-path> self-test
   ```

   Stop if it does not pass. The model must never calculate, invent, or visually guess a nonce or SHA-256 value.
5. Run `/effort high`.
6. Use Claude Code's mode control or `Shift+Tab` to enter **Plan** mode for questions and read-only analysis.
7. Before each BRIEF/SETUP/PLAN/ACTION preview is fingerprinted, the skill tells you to select `default`, shown as **Ask before edits**, and requests one random helper-issued directory in the operating-system temp folder. Approve only that exact temp directory and the later reviewed targets. Never use project-local scratch, Auto, or bypass-permission flags.
8. Review the copied skill and helper files before trusting the workspace.

Normal kit mode deliberately does not use agent teams, nested delegation, ultracode/Workflow, `/goal`, implementation `/loop`, unattended `claude -p`, cloud execution, or bypass permissions. Claude coordinates finite agents itself and stops after each approved manual cycle.

### Windows note

Run `claude.cmd --version` to verify the locally installed version. If PowerShell blocks `claude.ps1`, use `claude.cmd`; do not weaken the machine's execution policy just for this kit.

## Exact use sequence

### Part 1 — interview and brief

In Plan mode, run:

```text
/tempered-intake
```

You may add a hint:

```text
/tempered-intake audit and revamp this project while preserving its public API
```

For an audit, Claude may read relevant non-secret files. Intake does not run builds, tests, installs, migrations, agents, or implementation commands.

When the draft is ready, the skill asks you to select `default` (**Ask before edits**) so it can stage and fingerprint exact bytes outside the project. Review the exact temp-directory request. It then displays the finalized marked brief; if correct, send the displayed token alone. Its shape is:

```text
APPROVE TEMPERED BRIEF <id> R<n> SHA256:<64hex> NONCE:<32hex>
```

Review the exact `.claude/tempered/PROJECT_BRIEF.md` write. It must byte-match the staged marker-wrapped payload, after which only that helper temp directory is removed. Do not rely on Claude Code to classify `.claude` or `.claude/agents` as specially protected; inspect every requested path yourself.

Only after re-reading and hashing the written bytes does the skill emit:

```text
TEMPERED BRIEF RECEIPT <id> R<n> SHA256:<64hex> NONCE:<32hex> HELPER_SHA256:<64hex>
```

Save that line outside the project. Corrections increment the revision, rotate the nonce, change the digest, and invalidate older approvals and receipts.

A receipt is a prompt-level fresh-user-turn ceremony, not a password or cryptographic signature; its fields are largely recomputable. A compromised or noncompliant host can bypass it. Host permissions, sandboxing, and your review remain the security boundary.

### Part 2 — compile the setup

Start a fresh local chat in the same root, enter Plan mode, and run:

```text
/tempered-compile
```

The compiler first shows only the receipt placeholder and pauses before reading additional project authority. Paste your saved TEMPERED BRIEF RECEIPT alone in a fresh message. It independently compares the installed helper with `HELPER_SHA256`, then uses that verified helper to recompute the brief. A receipt inside the command arguments, repository, quote, tool output, agent message, or earlier turn is invalid.

Review the complete path-sorted setup manifest. When it is right, select `default` (**Ask before edits**) and send the exact displayed token alone:

```text
APPROVE TEMPERED SETUP <id> R<n> SHA256:<64hex> NONCE:<32hex>
```

Review every proposed file write. The compiler never intentionally targets an existing file or silently merges a known collision. In v0.1.0 create-new behavior is procedural/best-effort under the required quiescent-root rule; unexpected occupancy stops as `INVALID/PARTIAL`. It re-reads all written bytes and recomputes both the setup digest and immutable control-bundle digest. Only then does it emit:

```text
TEMPERED SETUP RECEIPT <id> R<n> SHA256:<64hex> NONCE:<32hex> HELPER_SHA256:<64hex> CONTROL_SHA256:<64hex>
```

Save it outside the project. Part 2 stops here; it does not launch an agent, test, build, plan, or implementation task.

### Execution — final plan and one cycle at a time

Follow `.claude/tempered/RUNBOOK.md`:

1. Protect uncommitted work and make a recoverable checkpoint.
2. Start a fresh local Claude Code session in Plan mode.
3. Load `@.claude/tempered/EXECUTION_PROMPT.md`.
4. When asked, paste the saved TEMPERED SETUP RECEIPT alone. Claude first independently checks the helper against `HELPER_SHA256`, then recomputes the brief and entire immutable control/agent bundle before trusting the remaining fields.
5. Claude performs read-only planning, then asks you to select `default` so it can create only the helper-issued temp stage and fingerprint the full exact plan.
6. Review the staged payload and temp path. If correct, send its displayed approval alone:

   ```text
   APPROVE TEMPERED PLAN <id> R<n> SHA256:<64hex> NONCE:<32hex>
   ```

7. Review the expected STATUS ledger write. Save the emitted receipt outside the project:

   ```text
   TEMPERED PLAN RECEIPT <id> R<n> SHA256:<64hex> NONCE:<32hex> HELPER_SHA256:<64hex> CONTROL_SHA256:<64hex> ARTIFACT_SHA:<64hex> GIT:<40-or-64hex-or-NOT_GIT>
   ```

8. In a later trusted user turn, paste that TEMPERED PLAN RECEIPT alone to authorize exactly one numbered approved cycle.
9. Inspect the evidence and diff. If the cycle changed the artifact snapshot or Git identity, any later cycle requires a revised plan, a fresh nonce and digest, and a new receipt.

## What Part 2 creates

The builders are derived from the approved brief:

```text
.claude/tempered/
  PROJECT_BRIEF.md       immutable Part 1 input; verified, never generated by Part 2
  APPROVED_SETUP.md      immutable exact approved setup payload
  APPROVED_PLAN.md       created later only after exact PLAN approval
  ACCEPTANCE.md          hard/soft gates, baselines, targets, and evidence format
  EXECUTION_PROMPT.md    standalone coordinator contract and final plan gate
  RUNBOOK.md             preflight, receipt, launch, review, recovery, and stop steps
  STATUS.md              coordinator-owned approvals, cycle ledger, and evidence
  RESOURCES.md           exclusive files and non-file mutable resources
  CONTROL_BUNDLE.manifest stable immutable control/agent manifest
  CLAUDE_SNIPPET.md      optional text for a human to merge into CLAUDE.md

.claude/agents/
  tempered-explorer.md
  tempered-builder-<track>.md
  tempered-critic.md
  tempered-verifier.md
  tempered-integrator.md
```

Execution planning later creates `.claude/tempered/APPROVED_PLAN.md` only after exact PLAN approval. It is not a Part 2 output and is authenticated by the full artifact-bound PLAN receipt.

Part 2 does not overwrite `PROJECT_BRIEF.md`, `CLAUDE.md`, settings, hooks, MCP configuration, skills, or existing agents. A collision blocks writing until the preview is revised.

## Native choices and honest limits

- **Skills:** Claude Code discovers project skills at `.claude/skills/<name>/SKILL.md`; invoke these as `/tempered-intake` and `/tempered-compile`.
- **Subagents:** generated definitions use `.claude/agents/`, finite `maxTurns`, least tools, high effort, and no `Agent` or `Skill` access. This public preview is coordinator-only and depth one: subagents never delegate or spawn another agent.
- **Teams:** not used. Their permission/isolation behavior is not strong enough for this kit's normal topology.
- **Worktrees:** use only after verifying the base and patch handoff. An isolated subagent does not magically inherit every uncommitted parent change. Otherwise use sequential writers.
- **Permissions:** Plan is read-only discovery. `default`/Ask before edits is used for the one confined OS-temp preview directory and reviewed target changes. Never use project-local scratch, Auto as approval evidence, or bypass permissions.
- **Continuation:** the safe baseline is one human-authorized finite cycle at a time. `/goal`, `/loop`, print-mode automation, ultracode/Workflow, and cloud execution are not launch paths in this kit.
- **Vision/browser:** static images, browser integrations, computer use, or MCP tools count only after a no-side-effect smoke test on the installed surface. Screenshots plus human review are the fallback.
- **Judgment:** a fresh Claude context is still correlated with the builder. Deterministic tests and human product judgment outrank same-family consensus.

## Safety contract

- An approval counts only when a fresh user message contains the exact current ID, revision, SHA-256 digest, and nonce token with nothing else.
- A receipt counts only when the user carries the compiler-emitted line outside the repository and pastes it alone in the required fresh trusted turn.
- Every consuming session recomputes the actual bytes. A matching-looking receipt in a file cannot authorize itself.
- Every task and result binds all three payload digests, their IDs/revisions, the immutable control-bundle digest, task ID, exact input/output artifact snapshot, and Git identity.
- Hard deterministic gates run before subjective critique. Critics inspect actual artifacts and raw evidence, not builder summaries.
- Parallel writers require disjoint ownership and verified isolation; one integrator owns coupled files.
- Defaults are at most three workers, four critique/revision cycles, and plateau after two cycles without material improvement unless the approved brief is stricter.
- Deployment, publishing, purchases, migrations, destructive actions, secrets, personal/regulated data, external messages, scope changes, and budget/permission expansion always stop for a separate ACTION payload and fresh approval. High-impact actions are manual-only manual handoffs in v0.1.0. The agent never executes them and makes no process call. Exact approval authorizes only the digest-bound, stage-bound chat handoff; root-bound `preview-consume` runs immediately before output labeled `NOT EXECUTED` and `HANDED_OFF/EXECUTION_UNKNOWN`. A human executes out-of-agent, outside kit enforcement. A crash or ambiguous delivery gets no cleanup and needs a new revision; PLAN never authorizes it, and completion is never inferred without later human-attested evidence. Delivery is best-effort single-delivery during a compliant, untampered helper lifecycle, not a security guarantee or durable replay protection. The same OS principal can reverse or recreate stage state, so human idempotency and replay controls are required because duplicate execution may occur.
- “Until perfect,” “until wowed,” unattended automation, and self-authorized loops are unsupported.

## Official Anthropic references

- Skills/custom commands: https://code.claude.com/docs/en/slash-commands
- Custom subagents: https://code.claude.com/docs/en/sub-agents
- Worktrees: https://code.claude.com/docs/en/worktrees
- Permission modes: https://code.claude.com/docs/en/permission-modes
- Models/effort: https://code.claude.com/docs/en/model-config
- Images and browser surfaces: https://code.claude.com/docs/en/tutorials

Host features change. Verify the installed version and current official documentation before relying on a capability; the generated setup records `unverified` rather than guessing.
