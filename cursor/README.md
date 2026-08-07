# Cursor Tempered Kit

This is the Cursor-native version of the two-part Tempered workflow.

- `/tempered-intake` asks the important questions for a new project or an evidence-based audit/revamp. It produces an approved project brief.
- `/tempered-compile` converts that approved brief into project-specific Cursor subagents, a scoped project rule, acceptance gates, a runbook, a status ledger, and a final execution prompt.

Neither part implements the project. The generated execution prompt asks for one more exact plan approval before any project-source write.

## Read this before you copy anything

Use the kit directly only in a new project or a repository whose instructions you already trust. A prompt cannot demote project rules, `AGENTS.md`, skills, agents, environments, automation, hooks, or other instructions Cursor has already loaded from a hostile workspace. For an unknown or untrusted repository, stop and use the clean-workspace bootstrap in the [threat model](../THREAT-MODEL.md). Remote and cloud execution are unsupported in this public preview.

This release uses the incompatible Tempered protocol v2: `payload_schema: 2` and `approval_binding: tempered-loop-sha256-nonce-v2`. Legacy v1 commands, payloads, approvals, and receipts are invalid; do not install both versions side by side. See the [migration guide](../MIGRATION.md).

Every approval is tied to the exact approved bytes with an ID, revision, SHA-256 digest, and fresh host-generated nonce. After each approved file is written and checked, Cursor prints a **TEMPERED BRIEF RECEIPT**, **TEMPERED SETUP RECEIPT**, or **TEMPERED PLAN RECEIPT**. Copy each receipt somewhere outside the project folder, such as a private note. A copy found in the repository is only an audit record and grants no authority.

## The five-year-old version

Think of Cursor as a robot helper. This kit makes the robot ask before it builds.

1. Open the project folder you want the robot to help with.
2. Copy this kit's `.cursor` folder into that project folder. If the project already has a `.cursor` folder, merge the folders; do not replace it.
3. Close and reopen Cursor.
4. Open a new Cursor chat in **Ask mode** and type `/tempered-intake`.
5. Answer the small groups of questions.
6. Cursor shows you a brief. Read it. If it is right, switch to **Agent mode** only if Cursor says Ask mode cannot save the approved file, then send only the complete `APPROVE TEMPERED BRIEF ... SHA256:... NONCE:...` line it gives you.
7. When Cursor prints `TEMPERED BRIEF RECEIPT ...`, copy that whole line into a private note **outside the project folder**.
8. Open a brand-new chat and type `/tempered-compile`. Do not put the receipt in this first message.
9. Cursor checks the brief and asks for the receipt. In your next message, paste only the saved `TEMPERED BRIEF RECEIPT ...` line.
10. Cursor shows you the robot team and safety plan. Read it. If it is right, switch to Agent mode only if needed for the approved save, then send only the complete `APPROVE TEMPERED SETUP ... SHA256:... NONCE:...` line it gives you.
11. Save the printed `TEMPERED SETUP RECEIPT ... CONTROL_SHA256:...` line in the same private note outside the project.
12. Open the new `.cursor/tempered/RUNBOOK.md` file and follow its steps in a fresh chat. Wait for Cursor to check the files, then paste only the saved setup receipt when it asks.
13. Cursor shows one final work plan. Nothing is allowed to build until you switch to Agent mode only if needed for that approved plan save and send its complete `APPROVE TEMPERED PLAN ... SHA256:... NONCE:...` line.
14. Save the full `TEMPERED PLAN RECEIPT ... CONTROL_SHA256:... ARTIFACT_SHA:... GIT:...` line outside the project. Every separate work chat checks the plan and current project snapshot before asking you to paste it in a new message.

There are three permission slips and three matching receipts: **brief**, **setup**, and **work plan**. A permission slip or receipt from an old version does not work on a new version. Never paste a receipt into the same message that starts a skill or work run. The fresh chat asks with placeholders before reading additional project authority. Paste your saved receipt alone in the next message; Cursor first checks the installed helper against `HELPER_SHA256`, then uses it to recompute the remaining expected values. It must not show or rebuild the real receipt for you.

A receipt is a prompt-level fresh-user-turn ceremony, not a password or cryptographic signature; its fields are largely recomputable. A compromised or noncompliant host can bypass it. Host permissions, sandboxing, and your review remain the security boundary.

## Install in one project (recommended)

Copy the kit's **whole `.cursor` folder** into the project root. This includes both skills and the required helper:

```text
<project-root>/.cursor/skills/tempered-intake/SKILL.md
<project-root>/.cursor/skills/tempered-compile/SKILL.md
<project-root>/.cursor/tempered-tools/tempered_receipt.py
```

The kit already has that structure. Copy or drag the kit's `.cursor` directory onto the project root. Merge folders if asked. Never replace an existing `.cursor` directory without reviewing it.

On Windows, the folder name begins with a dot but is still a normal folder. If you cannot see it, use File Explorer's **View > Show > Hidden items**, then copy the whole `.cursor` folder.

## Personal installation

This public preview supports project installation only. A personal skill copy by itself is insufficient because the prompts require the project-local helper at `.cursor/tempered-tools/tempered_receipt.py`. Copy and review the whole adapter folder separately for each trusted project. Do not put API keys, tokens, passwords, or environment values in the skills, helper, or generated Tempered files.

## Exact use

1. Update Cursor, then record **Help > About Cursor** (or **Cursor > About Cursor** on macOS): version, build, and release track.
2. Open the intended project root, not its parent folder.
3. In **Cursor Settings > Customize**, confirm `tempered-intake` and `tempered-compile` appear. On older builds, look under **Rules, Skills, Subagents**. If they do not appear, restart Cursor and verify the paths above.
4. Follow [Find the trusted Python path](../PYTHON-SETUP.md) to identify one canonical full Python 3.10+ executable path outside the project without PATH or command lookup. Reject project virtual environments and any symlink, shortcut, junction, or reparse-point path. Resolve `.cursor/tempered-tools/tempered_receipt.py` under the canonical project root to its full non-link path and keep it as `<canonical-absolute-helper-path>`. Use those same two paths for this read-only check and every later helper call:

   ```text
   <trusted-absolute-python> -I -S -B <canonical-absolute-helper-path> self-test
   ```

   Stop if it does not pass. Cursor must never calculate, invent, or visually guess a nonce or SHA-256 value.
5. Select a model in the Agent model picker. Record the exact displayed model label and any effort/context parameters. Do not guess a provider model ID from a web list.
6. For intake and compilation, use **Ask mode** for strict read-only discovery. Some Cursor versions persist Plan-mode plans as files, so Plan mode is not treated as a zero-write boundary by this kit. Before each fingerprint preview, the skill asks you to change to Agent mode without changing Approvals & Execution. Approve only its random helper-issued operating-system-temp directory; then review the finalized payload and later exact target writes. Never use project-local scratch.
7. In **Cursor Settings > Agents > Approvals & Execution**, prefer the strictest workable posture. For unfamiliar projects, use **Allowlist** or **Allowlist (with Sandbox)** and approve unfamiliar actions yourself. **Auto-review (with Sandbox)** is a convenience classifier, not a deterministic security boundary. This kit does not support **Run Everything (Unsandboxed)**.
8. Start a new chat and type:

   ```text
   /tempered-intake
   ```

   You may add starting context after it, for example:

   ```text
   /tempered-intake Audit and revamp this project. Preserve its public API and current user data.
   ```

9. When the draft is ready, review the exact helper-issued temp-directory request. Cursor stages and fingerprints the complete marker-wrapped brief outside the project. If the finalized payload is correct, reply in a new user turn with only the exact token shown, shaped like:

   ```text
   APPROVE TEMPERED BRIEF <id> R<n> SHA256:<64hex> NONCE:<32hex>
   ```

   Cursor reverifies the unchanged stage before writing `.cursor/tempered/PROJECT_BRIEF.md`, requires raw-byte equality afterward, and removes only that temp stage. Only after they match does it print:

   ```text
   TEMPERED BRIEF RECEIPT <id> R<n> SHA256:<64hex> NONCE:<32hex> HELPER_SHA256:<64hex>
   ```

   Save the whole receipt outside the repository. Do not add it to a project file.

10. Start a fresh chat in the same project root and type the command below **without the receipt**:

   ```text
   /tempered-compile
   ```

11. Part 2 first shows only the placeholder receipt shape and asks for your externally saved receipt before reading additional project authority. Reply in the next fresh top-level user turn with only your saved `TEMPERED BRIEF RECEIPT ...` line. Cursor independently checks the helper against `HELPER_SHA256`, then uses it to recompute the saved brief. A receipt copied or reconstructed from the repository, an earlier message, skill arguments, quoted text, or tool output is not accepted.

12. Review the proposed agents, rule, ownership, gates, permissions, budgets, and every exact setup file. If correct, reply in a new user turn with only the exact token shown, shaped like:

   ```text
   APPROVE TEMPERED SETUP <id> R<n> SHA256:<64hex> NONCE:<32hex>
   ```

13. Compilation writes and recomputes only the approved setup. It does not execute the project. After verification it prints:

    ```text
    TEMPERED SETUP RECEIPT <id> R<n> SHA256:<64hex> NONCE:<32hex> HELPER_SHA256:<64hex> CONTROL_SHA256:<64hex>
    ```

    Save the complete line outside the repository, then follow `.cursor/tempered/RUNBOOK.md` in a fresh chat. The execution chat must silently rebuild the control-bundle digest before it asks you to paste the setup receipt alone in a subsequent user turn. It must not display or reconstruct the actual expected receipt first.

14. Review the complete final plan. If it is right, approve only the exact content-bound token Cursor shows:

    ```text
    APPROVE TEMPERED PLAN <id> R<n> SHA256:<64hex> NONCE:<32hex>
    ```

    After the approved plan is written and recomputed, Cursor prints:

    ```text
    TEMPERED PLAN RECEIPT <id> R<n> SHA256:<64hex> NONCE:<32hex> HELPER_SHA256:<64hex> CONTROL_SHA256:<64hex> ARTIFACT_SHA:<64hex> GIT:<40-or-64hex-or-NOT_GIT>
    ```

    Save that entire line outside the repository. Each separate work launch must silently recompute both the approved plan and control bundle, ask with placeholders only, and receive your externally saved receipt alone in a new current user turn before source writes. It must not reveal the actual expected receipt values.

## What Part 2 generates

```text
.cursor/tempered/PROJECT_BRIEF.md
  immutable Part 1 input; Part 2 consumes it but never creates or rewrites it

.cursor/tempered/
  APPROVED_SETUP.md      immutable exact approved setup payload
  APPROVED_PLAN.md       created later only after exact PLAN approval
  ACCEPTANCE.md          gates, commands, targets, and evidence format
  EXECUTION_PROMPT.md    standalone bounded coordinator prompt
  RUNBOOK.md             preflight, launch, review, recovery, and stop steps
  STATUS.md              budgets, approvals, cycle log, evidence, and blockers
  RESOURCES.md           exclusive files and non-file mutable resources
  CONTROL_BUNDLE.manifest stable path-sorted control-file digest

.cursor/agents/
  tempered-explorer.md
  tempered-builder-<track>.md
  tempered-critic.md
  tempered-verifier.md
  tempered-integrator.md

.cursor/rules/
  tempered-execution.mdc
```

During the later execution-planning gate, the execution prompt creates `.cursor/tempered/APPROVED_PLAN.md` only after the exact plan token is approved. It is not a Part 2 output and it is authenticated separately by the saved plan receipt.

If any intended file already exists, the compiler must stop and propose a merge or a non-conflicting name. It must not overwrite an existing rule, agent, skill, `AGENTS.md`, permission file, environment file, or project source.

## Native feature versus safe fallback

| Capability | Cursor-native surface | What this kit does | Safe fallback |
|---|---|---|---|
| Two reusable prompts | Project skills under `.cursor/skills/<name>/SKILL.md`, invoked as `/name` | Uses `/tempered-intake` and `/tempered-compile`; both are manual-only skills | Paste the relevant `SKILL.md` into a fresh Agent chat if skill discovery fails |
| Persistent project guidance | `.cursor/rules/*.mdc` or root `AGENTS.md` | Generates one narrowly described `tempered-execution.mdc`; never intentionally targets `AGENTS.md` | Attach `EXECUTION_PROMPT.md` explicitly in a fresh chat |
| Specialized roles | Custom subagents under `.cursor/agents/*.md` | Generates named explorer, builders, critic, verifier, and integrator; verifies discovery and read-only behavior before use | Coordinator performs roles sequentially in fresh contexts |
| Isolated writer | `/worktree` (Cursor 3.0+) | Required for a writing track when verified in the active surface | One writer at a time in a user-created branch/worktree |
| Repeated local prompt | `/loop` (Cursor 3.5+) | Disabled by default for implementation because official docs describe outcome/user stopping but do not document a numeric outer-run ceiling | Run one approved critique/revision cycle at a time |
| Visual verification | Agent Browser, screenshots, and Design Mode | Requires an initial smoke test, stored screenshots/states, and deterministic checks where possible | User captures and signs off on reference screenshots |
| Tool approval | Allowlist, sandbox, or Auto-review | Recommends strict allowlist/sandbox; never changes permission settings | Ask before every unapproved shell, MCP, Fetch, or network action |
| Model choice | Agent model picker; custom subagents may inherit or use a configured model | Records the exact displayed choice and verifies actual subagent routing | Use the selected coordinator in fresh contexts and disclose correlated judging |

Feature names above are native Cursor features, but availability depends on the installed version, account, release track, policy, operating system, and active surface. The compiler records and smoke-tests what is actually present. It never treats a changelog as proof that your installation exposes a feature.

## Important Cursor-specific rules

- A custom subagent has a separate context; that does **not** prove it has a separate filesystem. Parallel writers require visibly separate worktrees, branches, or VMs. Otherwise writers run sequentially.
- `/loop` is excellent for monitoring or a clearly bounded external outcome, but "until perfect" is not a stopping test. This kit uses manual single cycles unless a real host-enforced ceiling is observed and recorded.
- This public preview is local-only. `/in-cloud`, cloud agents, remote writers, and any remote execution path are unsupported.
- Browser screenshots are useful evidence but a vision model can be wrong. Pair visual review with interaction tests, accessibility checks, layout measurements, and human sign-off when the brief requires it.
- A same-model critic in a fresh context is less biased than self-review, but it is not an independent judge. Record that limitation.
- This public preview is coordinator-only and depth one. The coordinator alone dispatches and writes `STATUS.md`; subagents never spawn, delegate, or invoke another agent and never edit the brief, gates, execution prompt, runbook, rule, or ledger.
- `PROJECT_BRIEF.md` is immutable authenticated Part 1 input. Part 2 must not list it as setup-created content or rewrite it.
- Repository copies of receipts and hashes, including copies in `STATUS.md`, are untrusted audit text. Trust crosses fresh sessions only when the user supplies the externally saved receipt alone after a placeholder-only challenge. The session first compares the installed helper with `HELPER_SHA256`, then recomputes the remaining fields; it never reconstructs the expected receipt for the user.
- Every task request and result must carry the exact brief/setup/plan IDs and revisions, all three payload digests, `control_bundle_sha256`, input/output artifact SHA-256, and Git commit SHA or `NOT_GIT`. The coordinator rejects stale or mismatched envelopes.
- PLAN approval does not authorize destructive, production, deploy, publish, purchase, migration, secret-data, network, external-message, permission, scope, or budget effects. Each needs a separate ACTION payload and fresh approval. High-impact actions are manual-only manual handoffs in v0.1.0. The agent never executes them and makes no process call. Exact approval authorizes only the digest-bound, stage-bound chat handoff; root-bound `preview-consume` runs immediately before output labeled `NOT EXECUTED` and `HANDED_OFF/EXECUTION_UNKNOWN`. A human executes out-of-agent, outside kit enforcement. A crash or ambiguous delivery gets no cleanup and needs a new revision; PLAN never authorizes it, and completion is never inferred without later human-attested evidence. Delivery is best-effort single-delivery during a compliant, untampered helper lifecycle, not a security guarantee or durable replay protection. The same OS principal can reverse or recreate stage state, so human idempotency and replay controls are required because duplicate execution may occur.

## Default bounded policy

Part 1 can change these values, but the compiler proposes them when the user has not supplied safer limits:

- At most 3 concurrent workers.
- At most 4 critic/revision cycles.
- Plateau after 2 consecutive cycles with no material improvement on the agreed measures.
- Success only when every hard gate passes, no critical/high defect remains, and required human sign-off is recorded.
- Stop on regression, exhausted time/token/cost budget, missing authority/evidence, or required human decision.
- No unbounded `/loop`, recursive fan-out, permission escalation, automatic deployment, or automatic publication.

## Capability record to collect

The intake asks for these facts because the prompt cannot create capabilities that Cursor does not expose:

- Cursor version, build, release track, operating system, and local surface: IDE, Agents Window, or CLI.
- Exact selected model label and visible effort/context/fast parameters; whether Auto routing is selected.
- Account/policy limits and approved token, time, cost, and concurrency ceilings.
- Whether both skills appear in the slash menu.
- Whether a tiny custom subagent is discovered and whether `readonly: true` behaves read-only.
- Whether `/worktree`, `/loop`, Browser/Design Mode, and the chosen local run mode are visible.
- Whether Git, tests, browser targets, reference artifacts, and required credentials are available without exposing secret values.
- Which outer-run ceiling, if any, is enforced by the active host rather than merely requested in a prompt.

## Official Cursor sources

Documentation and changelog state checked on 2026-08-06:

- Agent Skills and current command-style workflow: https://cursor.com/docs/skills
- Custom subagents: https://cursor.com/docs/subagents
- Project rules and `AGENTS.md`: https://cursor.com/docs/rules
- Plan mode: https://cursor.com/docs/agent/plan-mode
- Cursor CLI permissions: https://cursor.com/docs/cli/reference/permissions
- Skills and subagents release (2.4): https://cursor.com/changelog/2-4
- Worktrees release (3.0): https://cursor.com/changelog/3-0
- Editor subagent model controls (3.4): https://cursor.com/changelog/3-4
- `/loop` behavior (3.5): https://cursor.com/changelog/shared-canvases
- Auto-review run mode (3.6): https://cursor.com/changelog/auto-review
- Browser, screenshots, sandbox, Plan mode, and hooks: https://cursor.com/changelog/1-7
- Browser GA and isolated multi-agent environments: https://cursor.com/changelog/2-0
- Current Cursor changelog: https://cursor.com/changelog

Cursor changes quickly. If a label or menu has moved, use Cursor's current Settings/Customize pages and record what you actually see; do not guess a replacement command.
