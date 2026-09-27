"""BURN BOT — Discord music player. Credentials are environment-only."""
import asyncio
import contextlib
import logging
import os
import random
from collections import deque
from dataclasses import dataclass
from urllib.parse import urlparse

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
import yt_dlp

load_dotenv()
OWNER = 202282156418924550
APP_ID = 938531169316769832
MAX_QUEUE = 100
ALLOWED = ('youtube.com', 'youtu.be', 'soundcloud.com')
log = logging.getLogger('burn')


def validate_query(query):
    query = query.strip()
    if not query or len(query) > 500:
        raise ValueError('Enter a song name or supported URL (maximum 500 characters).')
    if '://' in query:
        u = urlparse(query)
        host = (u.hostname or '').lower()
        if u.scheme != 'https' or u.username or u.password or u.port not in (None, 443):
            raise ValueError('Use a public HTTPS YouTube or SoundCloud link.')
        if not any(host == h or host.endswith('.' + h) for h in ALLOWED):
            raise ValueError('Supported links: YouTube and SoundCloud. For Spotify/Apple Music, enter the song and artist name.')
        return query
    return 'ytsearch1:' + query


class QuietLogger:
    def debug(self, *_): pass
    def warning(self, *_): pass
    def error(self, *_): pass


def extract(query):
    with yt_dlp.YoutubeDL({'format': 'bestaudio/best', 'quiet': True,
        'logger': QuietLogger(), 'noplaylist': True, 'socket_timeout': 15,
        'retries': 1, 'extractor_retries': 1, 'js_runtimes': {'node': {}},
        'remote_components': [], 'cachedir': False}) as ydl:
        info = ydl.extract_info(query, download=False)
        if 'entries' in info:
            info = next((x for x in info['entries'] if x), None)
        if not info or not info.get('url'):
            raise ValueError('No playable result found.')
        return info


@dataclass
class Track:
    title: str
    url: str
    requester: int
    duration: int = 0


class Session:
    def __init__(self, guild):
        self.guild = guild
        self.queue = deque()
        self.current = None
        self.loop = 'off'
        self.volume = .7
        self.task = None
        self.done = None
        self.skip = False
        self.text = None
        self.panel = None
        self.lock = asyncio.Lock()
        self.generation = 0

    async def retire_panel(self):
        if self.panel:
            with contextlib.suppress(discord.HTTPException):
                await self.panel.edit(view=None)
            self.panel = None

    def start(self):
        if self.task is None or self.task.done():
            self.task = asyncio.create_task(self.worker())

    async def worker(self):
        try:
            while self.queue:
                track = self.queue.popleft()
                self.current = track
                self.skip = False
                try:
                    info = await asyncio.wait_for(asyncio.to_thread(extract, track.url), 45)
                    voice = self.guild.voice_client
                    if not voice or not voice.is_connected():
                        break
                    self.done = asyncio.Event()
                    event_loop = asyncio.get_running_loop()
                    done = self.done
                    errors = []
                    def after(error):
                        if error:
                            errors.append(error)
                        event_loop.call_soon_threadsafe(done.set)
                    source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(
                        info['url'], before_options='-nostdin -reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
                        options='-vn -loglevel error'), volume=self.volume)
                    try:
                        voice.play(source, after=after)
                    except Exception:
                        source.cleanup()
                        raise
                    await self.retire_panel()
                    with contextlib.suppress(discord.HTTPException):
                        self.panel = await self.text.send(embed=self.embed(), view=Controls(self))
                    await done.wait()
                    if errors:
                        raise RuntimeError('Audio playback failed')
                    if not self.skip:
                        if self.loop == 'track': self.queue.appendleft(track)
                        elif self.loop == 'queue': self.queue.append(track)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    log.warning('Track failed (%s)', type(exc).__name__)
                    with contextlib.suppress(discord.HTTPException):
                        await self.text.send('Could not play this track. It may be unavailable or blocked by the source. Trying the next song.')
                finally:
                    self.current = None
                    self.done = None
            await self.retire_panel()
        finally:
            self.current = None
            if self.queue:
                asyncio.get_running_loop().call_soon(self.start)

    def embed(self):
        t = self.current
        e = discord.Embed(title='🔥 BURN BOT • Now playing', color=0xff5828)
        if t:
            e.description = discord.utils.escape_markdown(t.title[:200])
            e.url = t.url
            e.add_field(name='Requested by', value=f'<@{t.requester}>')
            e.add_field(name='Duration', value=f'{t.duration//60}:{t.duration%60:02}' if t.duration else 'Live / unknown')
        e.add_field(name='Loop', value=self.loop)
        e.add_field(name='Volume', value=f'{round(self.volume*100)}%')
        e.set_footer(text='Owner: @hnooode • /help')
        return e

    async def stop(self, leave=False):
        self.generation += 1
        self.queue.clear()
        self.loop = 'off'
        if self.task and not self.task.done():
            self.task.cancel()
            with contextlib.suppress(asyncio.CancelledError): await self.task
        self.task = None
        if self.guild.voice_client:
            self.guild.voice_client.stop()
            if leave: await self.guild.voice_client.disconnect(force=True)
        self.current = None
        await self.retire_panel()


class Burn(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = False
        super().__init__(command_prefix=commands.when_mentioned, intents=intents,
            application_id=APP_ID, help_command=None, allowed_mentions=discord.AllowedMentions.none())
        self.sessions = {}

    async def setup_hook(self):
        gid = os.getenv('DISCORD_GUILD_ID')
        if gid:
            guild = discord.Object(id=int(gid))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()

    async def on_ready(self):
        await self.change_presence(activity=discord.Game('/play • /help | BURN BOT'))
        log.info('BURN BOT online')

    async def on_voice_state_update(self, member, before, after):
        if member.id == self.user.id and before.channel and not after.channel:
            s = self.sessions.get(member.guild.id)
            if s: await s.stop()


bot = Burn()


def session(i, require_voice=True):
    if not i.guild: raise ValueError('Use this command in the BURN server.')
    s = bot.sessions.setdefault(i.guild.id, Session(i.guild))
    if require_voice:
        channel = getattr(getattr(i.user, 'voice', None), 'channel', None)
        if not channel: raise ValueError('Join a voice channel first. ادخل روم صوتي أولاً.')
        voice = i.guild.voice_client
        if voice and voice.channel != channel:
            raise ValueError('Join my voice channel to control the music.')
    return s


async def reply(i, text):
    if i.response.is_done(): await i.followup.send(text, ephemeral=True)
    else: await i.response.send_message(text, ephemeral=True)


async def action(i, name):
    s = session(i)
    voice = i.guild.voice_client
    if name == 'stop':
        await s.stop()
        return await reply(i, 'Stopped and cleared the queue.')
    if name == 'leave':
        await s.stop(leave=True)
        return await reply(i, 'Disconnected and cleared the queue.')
    if name == 'shuffle':
        random.shuffle(s.queue)
        return await reply(i, 'Queue shuffled.')
    if name == 'clear':
        s.queue.clear()
        return await reply(i, 'Upcoming songs cleared.')
    if not voice or not s.current: raise ValueError('Nothing is playing. Use /play first.')
    if name == 'skip':
        if not s.done: raise ValueError('Track is loading. Use /stop to cancel it.')
        s.skip = True
        voice.stop()
    elif name == 'pause':
        if not voice.is_playing(): raise ValueError('No active playback to pause.')
        voice.pause()
    elif name == 'resume':
        if not voice.is_paused(): raise ValueError('Playback is not paused.')
        voice.resume()
    elif name == 'toggle':
        if voice.is_paused(): voice.resume()
        elif voice.is_playing(): voice.pause()
    elif name == 'loop':
        s.loop = {'off': 'track', 'track': 'queue', 'queue': 'off'}[s.loop]
    await reply(i, f'Loop: {s.loop}' if name == 'loop' else f'{name.capitalize()} ✓')
    if s.panel and name != 'skip':
        with contextlib.suppress(discord.HTTPException): await s.panel.edit(embed=s.embed())


class Controls(discord.ui.View):
    def __init__(self, s):
        super().__init__(timeout=None)
        self.session = s
        for label, name, style in [('Pause / Resume', 'toggle', discord.ButtonStyle.secondary),
            ('Skip', 'skip', discord.ButtonStyle.primary), ('Stop', 'stop', discord.ButtonStyle.danger),
            ('Loop', 'loop', discord.ButtonStyle.secondary)]:
            button = discord.ui.Button(label=label, style=style)
            async def callback(i, name=name):
                try:
                    if not self.session.panel or i.message.id != self.session.panel.id:
                        raise ValueError('This player has expired. Use the latest song message.')
                    await i.response.defer(ephemeral=True)
                    await action(i, name)
                except ValueError as exc: await reply(i, str(exc))
            button.callback = callback
            self.add_item(button)


@bot.tree.command(name='play', description='Play a song name (Arabic/English), YouTube or SoundCloud URL')
@app_commands.guild_only()
async def play(i: discord.Interaction, query: str):
    s = session(i)
    query = validate_query(query)
    await i.response.defer(ephemeral=True)
    generation = s.generation
    async with s.lock:
        if len(s.queue) >= MAX_QUEUE: raise ValueError('Queue is full (100 upcoming songs).')
        info = await asyncio.wait_for(asyncio.to_thread(extract, query), 45)
        if generation != s.generation:
            return await reply(i, 'Request cancelled because playback was stopped.')
        session(i)  # Recheck membership after potentially slow extraction.
        if not i.guild.voice_client:
            channel = i.user.voice.channel
            if not isinstance(channel, discord.VoiceChannel):
                raise ValueError('Use a normal voice channel, not a Stage channel.')
            perms = channel.permissions_for(i.guild.me)
            if not perms.connect or not perms.speak:
                raise ValueError('I need Connect and Speak permissions in your voice channel.')
            await channel.connect(self_deaf=True)
        if generation != s.generation:
            return await reply(i, 'Request cancelled because playback was stopped.')
        t = Track(info.get('title', 'Unknown track'), info['webpage_url'], i.user.id, int(info.get('duration') or 0))
        s.text = i.channel
        s.queue.append(t)
        s.start()
        await reply(i, f'Added: {discord.utils.escape_markdown(t.title[:150])}')


def register_action(name, description):
    async def handler(i: discord.Interaction):
        await i.response.defer(ephemeral=True)
        await action(i, name)
    bot.tree.add_command(app_commands.Command(name=name, description=description, callback=handler))

for name, desc in {'pause':'Pause playback', 'resume':'Resume playback', 'skip':'Skip the current song',
    'stop':'Stop playback and clear the queue', 'leave':'Disconnect from voice and clear the queue',
    'shuffle':'Shuffle upcoming songs', 'clear':'Clear upcoming songs'}.items(): register_action(name, desc)


@bot.tree.command(name='queue', description='Show upcoming songs (10 per page)')
async def queue(i: discord.Interaction, page: app_commands.Range[int, 1, 10] = 1):
    s = session(i, False)
    tracks = list(s.queue)
    lines = [f'{n+1}. {discord.utils.escape_markdown(t.title[:100])}' for n,t in enumerate(tracks) if (page-1)*10 <= n < page*10]
    await reply(i, f'Queue • page {page} • {len(tracks)} upcoming\n' + ('\n'.join(lines) or 'No songs on this page.'))


@bot.tree.command(name='nowplaying', description='Show the current song')
async def nowplaying(i: discord.Interaction):
    s = session(i, False)
    if not s.current: raise ValueError('Nothing is playing.')
    await i.response.send_message(embed=s.embed(), ephemeral=True)


@bot.tree.command(name='loop', description='Loop the current song, entire queue, or turn looping off')
@app_commands.choices(mode=[app_commands.Choice(name=x, value=x) for x in ['off','track','queue']])
async def loop(i: discord.Interaction, mode: app_commands.Choice[str]):
    s = session(i)
    s.loop = mode.value
    await reply(i, f'Loop: {s.loop}')
    if s.panel:
        with contextlib.suppress(discord.HTTPException): await s.panel.edit(embed=s.embed())


@bot.tree.command(name='volume', description='Set volume from 0 to 100 percent')
async def volume(i: discord.Interaction, percent: app_commands.Range[int, 0, 100]):
    s = session(i)
    s.volume = percent/100
    voice = i.guild.voice_client
    if voice and isinstance(voice.source, discord.PCMVolumeTransformer): voice.source.volume = s.volume
    await reply(i, f'Volume: {percent}%')


@bot.tree.command(name='remove', description='Remove an upcoming song by its queue position')
async def remove(i: discord.Interaction, position: app_commands.Range[int, 1, 100]):
    s = session(i)
    if position > len(s.queue): raise ValueError('That queue position does not exist.')
    del s.queue[position-1]
    await reply(i, 'Song removed.')


@bot.tree.command(name='ping', description='Show bot gateway latency')
async def ping(i: discord.Interaction):
    await reply(i, f'Gateway latency: {bot.latency*1000:.0f} ms (not an audio quality measurement).')


@bot.tree.command(name='help', description='List all BURN BOT commands and contact the owner')
async def help_command(i: discord.Interaction):
    e = discord.Embed(title='🔥 BURN BOT • Help', color=0xff5828,
        description='Join a voice channel, then use `/play query`.\nاكتب اسم الأغنية أو رابط يوتيوب أو ساوندكلاود.\n\n' +
        '\n'.join(f'`/{c.name}` — {c.description}' for c in sorted(bot.tree.get_commands(), key=lambda x: x.name)))
    e.add_field(name='Contact the owner', value=f'@hnooode • <@{OWNER}>', inline=False)
    e.set_footer(text='Playback controls work only in the bot’s voice channel. Queue resets on restart.')
    await i.response.send_message(embed=e, ephemeral=True)


@bot.tree.error
async def command_error(i, error):
    original = getattr(error, 'original', error)
    if isinstance(original, ValueError): message = str(original)
    elif isinstance(original, asyncio.TimeoutError): message = 'Source timed out. Try another song or URL.'
    else:
        log.warning('Command failed (%s)', type(original).__name__)
        message = 'Request failed. Check bot permissions or try another source. Contact @hnooode if it continues.'
    await reply(i, message)


if __name__ == '__main__':
    token = os.getenv('DISCORD_TOKEN')
    if not token: raise SystemExit('Set DISCORD_TOKEN in .env or your hosting secret settings.')
    bot.run(token, log_level=logging.INFO)
