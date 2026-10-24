# Agent Runtime

This repository contains reusable capabilities. The user and CEO agents use them.

## Capabilities

| ID | Use it to | Guide |
|---|---|---|
| `content.extract_url` | Get the text, subtitles, or transcript of a URL (YouTube, Bilibili, WeChat Channels). | `capabilities/content.extract_url/AGENT_GUIDE.md` |
| `video.generate_subtitles` | Make SRT and VTT subtitles for a local video file. Put the subtitles into an MP4. | `capabilities/video.generate_subtitles/AGENT_GUIDE.md` |
| `document.pptx_to_md` | Convert a PPTX file to Markdown, with OCR of images. | `capabilities/document.pptx_to_md/AGENT_GUIDE.md` |
| `discord.channel` | Read messages in a Discord channel. Add a reaction to a message. Delete a message. | `capabilities/discord.channel/AGENT_GUIDE.md` |

## Rules

1. Before you start, run `git pull`.
2. Read the table above. If a capability does the task, use it. Do not write new code for the same task.
3. Read the guide of a capability before you run it.
4. If you write code that you can use again, make it a capability:
   1. Make the folder `capabilities/<domain>.<action>/`.
   2. Put an executable `run` and an `AGENT_GUIDE.md` in the folder. Add `setup` if the capability needs dependencies.
   3. Add one row to the table above.
   4. Test the capability.
   5. Commit and push.
5. If you change a capability, run its tests. Then commit and push.
6. Put temporary files in `temp/<task-name>/` at the repository root. When the task is complete, delete your folder. Do not delete other folders in `temp/`.
7. Keep credentials in `.env` at the repository root. Do not commit credentials.
8. Write guides in ASD-STE100 style: short sentences, one instruction in each sentence, imperative verbs.
