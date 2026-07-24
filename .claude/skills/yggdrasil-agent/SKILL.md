---
name: yggdrasil-agent
description: Connect every Claude Code task to the local Yggdrasil cognitive runtime. Use at the start of each substantive user request to create a Run, retrieve cognitive context, record references and important action outcomes, submit feedback, and finish the Run before the final response. Also use when the user asks to inspect or diagnose Yggdrasil tracking.
---

# Yggdrasil Agent Loop

Use the bundled client at:

```bash
python3 "$HOME/.claude/skills/yggdrasil-agent/scripts/yggdrasil_client.py"
```

Default server: `http://127.0.0.1:6061`. Override with `YGGDRASIL_URL`.

## Required Workflow

For every substantive user task:

1. Check the service once:

   ```bash
   python3 "$HOME/.claude/skills/yggdrasil-agent/scripts/yggdrasil_client.py" health
   ```

2. Start a Run before doing substantive work. Pass a concise intent, not the complete prompt:

   ```bash
   python3 "$HOME/.claude/skills/yggdrasil-agent/scripts/yggdrasil_client.py" begin \
     --intent "修复订单查询超时" --domain "database"
   ```

   Save `run.run_id` from the JSON response. Read `context.markdown` and use relevant retrieved knowledge. `begin` automatically records returned node and edge references.

3. Record only important decisions, external observations, and tool outcomes:

   ```bash
   python3 "$HOME/.claude/skills/yggdrasil-agent/scripts/yggdrasil_client.py" record \
     --run-id RUN_ID --event-type action_result \
     --payload '{"action":"pytest","outcome":"passed","tests":63}'
   ```

   Do not record every shell command. Record outcomes that explain how the task was solved.

4. Before the final user response, finish the Run:

   ```bash
   python3 "$HOME/.claude/skills/yggdrasil-agent/scripts/yggdrasil_client.py" finish \
     --run-id RUN_ID --status succeeded \
     --summary "修复引用记录并通过测试" \
     --used-node NODE_ID --result-ref "local://working-tree"
   ```

   Use `failed` only when the attempted task failed. Use `cancelled` when the user stops or replaces the task. A blocked but well-investigated task normally finishes as `succeeded` with the blocker in the summary because the requested investigation completed.

## Failure Handling

- If health or `begin` fails, continue the user's task and state briefly that Yggdrasil tracking is unavailable. Do not loop on retries.
- If a Run was created but a later call fails, attempt `finish --status failed` once.
- Never let observability failure hide or replace the user's requested result.
- Do not create a Run for greetings, acknowledgements, or a request that explicitly disables Yggdrasil tracking.

## Data Safety

- Send summaries and stable references only.
- Never send source file contents, full diffs, complete prompts, environment variables, credentials, tokens, cookies, personal data, or raw command output.
- Keep summaries factual and under 2,000 characters.
- The client recursively redacts sensitive field names and caps payload size, but treat that as a final guardrail rather than permission to send sensitive input.

## Commands

- `health`: verify the runtime.
- `begin`: create Run, retrieve context, and record references.
- `record`: append a correlated Soil event.
- `action`: attach a Yggdrasil Skill execution result to the Run.
- `feedback`: reinforce or weaken one retrieved node or edge.
- `finish`: write the final evaluation event, optionally feedback used references, and close the Run.

Read [references/api-contract.md](references/api-contract.md) only when diagnosing a client/API mismatch.
