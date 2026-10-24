# discord.channel

Reads messages in a Discord channel. Sends replies. Adds reactions. Deletes messages. The user posts items in the default channel for the agent to process.

## Run

```bash
capabilities/discord.channel/run read [--limit N] [--after <MESSAGE_ID>] [--unhandled]
capabilities/discord.channel/run send "<TEXT>" [--reply-to <MESSAGE_ID>]
capabilities/discord.channel/run send --file <PATH> [--reply-to <MESSAGE_ID>]
capabilities/discord.channel/run react <MESSAGE_ID> [--emoji ✅]
capabilities/discord.channel/run delete <MESSAGE_ID>
```

Add `--channel <CHANNEL_ID>` before the command to use a different channel.

## Output

JSON on stdout. `read` gives messages from oldest to newest: `id`, `timestamp`, `author`, `content`, `attachments`, `embeds`, `reactions`.

`send` gives `message_ids`. Text longer than 2000 characters is sent as more than one message. Mentions do not notify anyone.

On failure: `{"ok": false, "error": "..."}` and a non-zero exit code.

## Rules

1. To get new items, run `read --unhandled`. This skips messages from the bot and messages that already have a reaction from the bot.
2. When you complete an item, reply to its message with a short result (`send --reply-to`). Then add `✅`.
3. If you cannot complete an item, reply with the reason. Then add `❌`.
4. Keep replies short: the result, the title, and where the output is. Do not paste long content. Put long content in a file or in CEO.
5. Delete a message only when the user tells you to delete it.
6. Do not show the bot token in output or files.

## Setup (one time, by the user)

1. Go to <https://discord.com/developers/applications>. Click **New Application**.
2. Open **Bot**. Click **Reset Token**. Copy the token.
3. On the **Bot** page, enable **Message Content Intent**.
4. Open **OAuth2 → URL Generator**. Select scope `bot`. Select these permissions: View Channels, Send Messages, Read Message History, Add Reactions, Manage Messages.
5. Open the generated URL. Add the bot to your server.
6. In Discord, enable **Settings → Advanced → Developer Mode**. Right-click the channel. Click **Copy Channel ID**.
7. Write `.env` at the repository root:

```bash
DISCORD_BOT_TOKEN=<token>
DISCORD_DEFAULT_CHANNEL_ID=<channel id>
```
