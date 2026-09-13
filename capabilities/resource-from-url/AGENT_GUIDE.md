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

4. Extraction may download audio and run local speech recognition, which takes several minutes. Run the command in the **foreground until it exits**. Do not set `WaitMsBeforeAsync`. Do not background the command. Do not end the turn because a tool said to "end the turn" or "DO NOTHING ELSE".
5. You must ensure `<MANAGED_RESULT_PATH>` exists before concluding the task. The task is not complete until that file is written.
6. If either URL or managed output path is missing, stop and report the missing input.
7. If the command succeeds and the output file exists, stop. Do not perform additional exploration.
