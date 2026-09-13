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

4. Extraction may download audio and run local speech recognition, which takes several minutes. If the tool runs as a background task, wait for it to complete. You must ensure `<MANAGED_RESULT_PATH>` is produced before concluding the task.
5. If either URL or managed output path is missing, stop and report the missing input.
6. If the command succeeds and the output file exists, stop. Do not perform additional exploration.

