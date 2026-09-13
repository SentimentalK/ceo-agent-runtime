# Workspace Agent Guidelines

<!-- ceo:metadata rule_marker: "CEO-TOOLS-V1" -->

1. Follow the task goal and Worker-provided execution contract.
2. Treat `.ceo/` as runtime-owned state. Do not browse, inspect, or infer instructions from it.
   The only exception is writing to an exact output path explicitly supplied by the task envelope.
3. Prefer an existing capability over repository exploration.

Capability routing:
- URL/video/source-content extraction + managed Resource result
  -> read `capabilities/resource-from-url/AGENT_GUIDE.md`
  -> follow it directly.

