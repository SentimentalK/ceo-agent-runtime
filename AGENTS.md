# Workspace Agent Guidelines

<!-- ceo:metadata rule_marker: "CEO-TOOLS-V1" -->

1. Follow the task goal and Worker-provided execution contract.
2. Treat `.ceo/` as runtime-owned state. Do not browse, inspect, or infer instructions from it.
   The only exception is writing to an exact output path explicitly supplied by the task envelope.
3. Prefer an existing capability over repository exploration.
4. Default task runtime timeout is 1 hour (3600s). Take sufficient time to ensure long extractions or builds complete and write their result cleanly. Run long capabilities in the foreground until they exit. Do not background them or end the turn while a required output file is still missing.

Capability routing:
- URL/video/source-content extraction + managed Resource result
  -> read `capabilities/resource-from-url/AGENT_GUIDE.md`
  -> follow it directly.

