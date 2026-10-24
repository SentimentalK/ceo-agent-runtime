# discord.channel

Reads messages in a Discord channel. Adds reactions. Deletes messages. The user posts items in the default channel for the agent to process.

## Run

```bash
capabilities/discord.channel/run read [--limit N] [--after <MESSAGE_ID>] [--unhandled]
capabilities/discord.channel/run react <MESSAGE_ID> [--emoji ✅]
capabilities/discord.channel/run delete <MESSAGE_ID>
```

Add `--channel <CHANNEL_ID>` before the command to use a different channel.

## Output

JSON on stdout. `read` gives messages from oldest to newest: `id`, `timestamp`, `author`, `content`, `attachments`, `embeds`, `reactions`.

On failure: `{"ok": false, "error": "..."}` and a non-zero exit code.

## Rules

1. To get new items, run `read --unhandled`. This skips messages that already have a reaction from the bot.
2. When you complete an item, add `✅` to its message.
3. If you cannot complete an item, add `❌`. Tell the user why.
4. Delete a message only when the user tells you to delete it.
5. Do not show the bot token in output or files.

## Setup (one time, by the user)

1. Go to <https://discord.com/developers/applications>. Click **New Application**.
2. Open **Bot**. Click **Reset Token**. Copy the token.
3. On the **Bot** page, enable **Message Content Intent**.
4. Open **OAuth2 → URL Generator**. Select scope `bot`. Select these permissions: View Channels, Read Message History, Add Reactions, Manage Messages.
5. Open the generated URL. Add the bot to your server.
6. In Discord, enable **Settings → Advanced → Developer Mode**. Right-click the channel. Click **Copy Channel ID**.
7. Write `.env` at the repository root:

```bash
DISCORD_BOT_TOKEN=<token>
DISCORD_DEFAULT_CHANNEL_ID=<channel id>
```
