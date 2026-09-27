import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import discord.voice_client
import bot


class Tests(unittest.IsolatedAsyncioTestCase):
    def test_queries(self):
        self.assertEqual(bot.validate_query('اغنية'), 'ytsearch1:اغنية')
        self.assertEqual(bot.validate_query('https://youtu.be/abc'), 'https://youtu.be/abc')
        for q in ['https://127.0.0.1/a', 'file:///etc/passwd', 'https://youtube.com.evil.test/a', 'https://youtube.com:123/a']:
            with self.assertRaises(ValueError): bot.validate_query(q)

    def test_commands_and_dave(self):
        names = {c.name for c in bot.bot.tree.get_commands()}
        self.assertEqual(len(names), 15)
        self.assertTrue({'play','help','pause','resume','stop','queue','loop','remove'} <= names)
        self.assertTrue(discord.voice_client.has_dave)
        for command in bot.bot.tree.get_commands(): command.to_dict(bot.bot.tree)

    async def test_voice_access(self):
        g = SimpleNamespace(id=42, voice_client=SimpleNamespace(channel=1))
        i = SimpleNamespace(guild=g, user=SimpleNamespace(voice=SimpleNamespace(channel=2)))
        with self.assertRaises(ValueError): bot.session(i)
        i.user.voice.channel = 1
        self.assertIs(bot.session(i).guild, g)

    async def test_worker_advance_and_stop(self):
        class Voice:
            def is_connected(self): return True
            def play(self, source, after): self.after = after
            def stop(self):
                if hasattr(self, 'after'): self.after(None)
        voice = Voice()
        s = bot.Session(SimpleNamespace(voice_client=voice))
        s.text = SimpleNamespace(send=AsyncMock(return_value=SimpleNamespace(edit=AsyncMock(), id=1)))
        s.queue.extend([bot.Track('one','https://youtu.be/1',1), bot.Track('two','https://youtu.be/2',1)])
        with patch.object(bot, 'extract', return_value={'url':'https://example.com/audio'}), patch.object(bot.discord, 'FFmpegPCMAudio'), patch.object(bot.discord, 'PCMVolumeTransformer'):
            s.start()
            for _ in range(100):
                if s.panel: break
                await asyncio.sleep(.005)
            self.assertEqual(s.current.title, 'one')
            voice.after(None)
            for _ in range(100):
                if s.current and s.current.title == 'two' and s.panel: break
                await asyncio.sleep(.005)
            self.assertEqual(s.current.title, 'two')
            await s.stop()
            self.assertIsNone(s.current)
            self.assertFalse(s.queue)
            self.assertIsNone(s.task)
            self.assertIsNone(s.panel)

    async def test_stop_during_load(self):
        s = bot.Session(SimpleNamespace(voice_client=None))
        s.queue.append(bot.Track('one', 'https://youtu.be/1', 1))
        started = asyncio.Event()
        async def slow(*args):
            started.set()
            await asyncio.Event().wait()
        with patch.object(bot.asyncio, 'to_thread', new=slow):
            s.start()
            await started.wait()
            self.assertIsNotNone(s.current)
            await s.stop()
        self.assertIsNone(s.current)
        self.assertFalse(s.queue)

if __name__ == '__main__': unittest.main()
