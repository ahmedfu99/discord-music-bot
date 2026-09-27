# BURN BOT

music bot that can play music in your channel 

## Status

This is a new replacement implementation, not an edit of your existing source (none was supplied). It has not been deployed or connected to Discord. The exposed token is deliberately excluded. Local verification details are in VALIDATION.md.

## Features

/play query — Arabic/English song search or YouTube/SoundCloud URL (one song per request)
/pause, /resume, /skip, /stop, /leave
/queue page, /nowplaying, /shuffle, /clear, /remove position
/loop mode — off / track / queue
/volume percent — 0–100, default 70
/ping, /help — complete command list and owner contact

Each playing song gets Pause/Resume, Skip, Stop, and Loop buttons. Old controls expire when the song changes. Only members in the bot's voice channel can control playback. Separate queues per server; maximum 100 upcoming tracks. The bot stays connected while idle; /leave disconnects. Queues are in memory and reset on restart. Playback notices are posted in the channel used for /play; command acknowledgments are private.

Spotify and Apple Music links are not playable in this implementation. Use artist + song name instead. YouTube/SoundCloud availability depends on the host, source restrictions, and extractor compatibility. No implementation can honestly guarantee every song URL. Full playlist import is not included.

## Secure setup

1. In Discord Developer Portal → BURN BOT → Bot, reset the exposed token. Do not send the replacement in chat.
2. Copy .env.example to .env on your host and enter the NEW token locally. Never commit .env.
3. Optionally add your Discord SERVER ID to DISCORD_GUILD_ID for fast server-specific slash command registration. This is not the bot or owner ID. Enable Developer Mode in Discord and right-click the server to copy its ID.
4. In Developer Portal → OAuth2 URL Generator, select `bot` and `applications.commands`. Grant View Channels, Send Messages, Embed Links, Connect, and Speak. Use the generated link to authorize BURN BOT in your server. Administrator and Message Content Intent are unnecessary. Ensure channel overrides permit those permissions in music-command and the voice channel.
5. Stop any previous BURN BOT process before starting this replacement. One active instance per token.

## Recommended free hosting candidate

Oracle Cloud Always Free compute VM, in Jeddah (Saudi Arabia West) if available as your home region and with eligible free capacity. This is a geographic starting recommendation, not a measured latency result. Jeddah is listed as an active region, but free shape availability must be checked in the account before creating anything. Home region matters for Always Free eligibility.

Use only an instance explicitly marked Always Free eligible, within the account's storage and compute allowances. Do not assume trial-funded resources remain free. Oracle can reclaim idle free VMs and may have no capacity; there is no guaranteed free 24/7 SLA here. If eligible Jeddah capacity is unavailable, review another nearby eligible home-region option before account creation. Avoid creating paid resources or changing billing unintentionally.

No cloud account or VM has been created by this task. A host account, eligible capacity and access to the VM are required to deploy. Render's free web tier is not an appropriate guaranteed always-on worker solution.

## Run on a Linux VM with Docker Engine and Compose installed

Transfer this folder to the VM, then run inside it:

```sh
cp .env.example .env
chmod 600 .env
nano .env
docker compose up -d --build
docker compose logs --tail=50 -f
```

Docker must be enabled at boot on the VM. The compose restart policy restarts the bot after crashes and host reboots, provided Docker starts and the host remains available. No inbound web port is needed. The VM needs outbound HTTPS/WebSocket access and Discord voice UDP connectivity. Do not expose the bot token through a web endpoint. The Docker image includes FFmpeg, Opus, Node.js for extraction challenges, and discord.py voice/DAVE dependencies.

Update after reviewing dependency releases: change pinned versions in requirements.txt, then rebuild using `docker compose up -d --build`. If YouTube starts failing, check upstream yt-dlp notices; do not bypass access controls or upload private browser cookies to public repositories.

## Local run alternative

Install Python 3.12, Node.js 22, FFmpeg and the Opus runtime. Create a virtual environment, install requirements.txt, populate .env, and run `python bot.py`. Keeping a PC app open does not keep a cloud bot running; the actual host process must stay running.

## Audio and Saudi Arabia

Start with Discord voice-region selection on Automatic. Host location alone does not determine sound quality: Discord's selected voice region, source availability, packet loss and channel bitrate also matter. This bot streams stereo through FFmpeg and Discord's voice encoder. Test from your Saudi connection before choosing a manual voice-region override.

## Live acceptance check

1. Join the Middle East voice channel and run /help in music-command.
2. Run /play with an Arabic name, an English name, a YouTube link and a SoundCloud link.
3. Queue two tracks; verify pause/resume, skip, track/queue looping, queue paging, volume, remove, shuffle, stop and leave.
4. Confirm a member in a different voice channel cannot use playback controls.
5. Restart the container; verify the bot reconnects and note that the old queue clears.
6. If source extraction fails on the cloud host, test another supported source. If all voice playback fails, check Connect/Speak permissions, outbound UDP, FFmpeg and DAVE dependency installation.

## References (checked September 12, 2026)

https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm
https://www.oracle.com/cloud/public-cloud-regions/
https://render.com/docs/free
https://discord.com/blog/bringing-dave-to-all-discord-platforms
https://github.com/Rapptz/discord.py
https://github.com/yt-dlp/yt-dlp
