# Agent Execution Guide for Capability: content.extract_url

## CRITICAL INSTRUCTIONS - READ CAREFULLY
1. You are acting as an autonomous execution worker for a CEO acquisition task.
2. DO NOT enter plan mode.
3. DO NOT search, explore, inspect, or modify files across other repositories or parent directories.
4. DO NOT attempt to write or transcribe subtitles yourself.
5. Use the provided runner script to extract content:

```bash
./capabilities/content.extract_url/run --url "<URL>" --output-dir "<TEMP_DIR>"
```

Extraction may download audio and run local speech recognition, which takes several minutes. Run the command in the foreground until it exits. Do not background the command.

6. When extraction succeeds, inspect `<TEMP_DIR>/result.json` (or read its fields).
7. Format and write the final result strictly into the file path specified in your task's `MANAGED RESULT CONTRACT` (e.g. `managed-result.json`):

```json
{
  "schema_version": 1,
  "job_id": "<job_id from MANAGED RESULT CONTRACT>",
  "attempt_id": "<attempt_id from MANAGED RESULT CONTRACT>",
  "resource_id": "<resource_id from MANAGED RESULT CONTRACT>",
  "summary": "Extracted transcript from source URL",
  "operations": [
    {
      "op": "upsert_content",
      "content": "<full extracted transcript from result.json>"
    },
    {
      "op": "upsert_summary",
      "summary": "<concise summary of the transcript>",
      "basis": "source_content"
    },
    {
      "op": "upsert_evidence",
      "method": "content.extract_url",
      "details": "Extracted via local subtitle/ASR pipeline"
    }
  ]
}
```

8. Rules:
- Do NOT place `managed-result.json` inside git or the repository. Write it to the EXACT path provided in `MANAGED RESULT CONTRACT`.
- Do NOT modify `resources/**` directly in the CEO git workspace.
- Do NOT call CEO Server APIs directly.
- The task is complete once `managed-result.json` is written and verified.

