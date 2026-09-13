# Agent Execution Guide for Capability: resource-from-url

## Instructions
1. Do not explore the repository or `.ceo` runtime state.
2. Do not manually transcribe source content.
3. When the task provides:
   - a source URL; and
   - a managed Resource output path,
   run:

```bash
./capabilities/resource-from-url/run --url "<URL>" --output "<MANAGED_RESULT_PATH>"
```

4. If either URL or managed output path is missing, stop and report the missing input.
5. If the command succeeds, stop. Do not perform additional exploration.

