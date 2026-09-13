# Agent Execution Guide for Capability: resource-from-url

## CRITICAL INSTRUCTIONS - READ CAREFULLY
1. You are acting as an automated, non-interactive execution worker.
2. DO NOT enter plan mode.
3. DO NOT search, explore, inspect, or modify any files across this repository or any workspace.
4. DO NOT attempt to transcribe video or audio subtitles manually.
5. If the CEO task envelope specifies:
   ```markdown
   ## Result Target
   This task requires a managed resource result.
   Upon completing extraction, you MUST write the result JSON to:
   <MANAGED_RESULT_PATH>
   ```
6. Execute the EXACT command specified below using `run_command`:

```bash
./capabilities/resource-from-url/run --url "<URL>" --output "<MANAGED_RESULT_PATH>"
```

7. Once the command finishes execution successfully, exit and stop calling any more tools immediately.
