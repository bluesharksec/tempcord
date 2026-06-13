import discord
from discord import Webhook, AsyncWebhookAdapter
import aiohttp
from typing import List, Dict
import asyncio

class DiscordBot(discord.Client):
    def __init__(self, config):
        intents = discord.Intents.default()
        intents.message_content = False
        intents.guilds = True
        super().__init__(intents=intents)
        self.config = config
        self.guilds_cache = {}
        self.channels_cache = {}
    
    async def on_ready(self):
        print(f'Bot logged in as {self.user}')
        await self.cache_guilds()
    
    async def cache_guilds(self):
        for guild in self.guilds:
            self.guilds_cache[guild.id] = {
                'id': str(guild.id),
                'name': guild.name,
                'icon': str(guild.icon.url) if guild.icon else None
            }
            await self.cache_channels(guild)
        
        print(f"Cached {len(self.guilds_cache)} guilds")
    
    async def cache_channels(self, guild: discord.Guild):
        channels = {}
        for channel in guild.channels:
            if isinstance(channel, discord.TextChannel):
                permissions = channel.permissions_for(guild.me)
                if permissions.send_messages and permissions.view_channel:
                    channels[channel.id] = {
                        'id': str(channel.id),
                        'name': channel.name,
                        'type': 'text'
                    }
        self.channels_cache[guild.id] = channels
    
    async def create_webhook(self, channel_id: int, name: str, avatar_url: str = None) -> tuple[str, str]:
        channel = self.get_channel(channel_id)
        if not channel:
            raise ValueError(f"Channel {channel_id} not found")
        
        permissions = channel.permissions_for(channel.guild.me)
        if not permissions.manage_webhooks:
            raise PermissionError("Bot doesn't have permission to manage webhooks")
        
        webhook = await channel.create_webhook(name=name, avatar=avatar_url)
        return str(webhook.id), webhook.token
    
    async def delete_webhook(self, webhook_id: int, webhook_token: str):
        try:
            async with aiohttp.ClientSession() as session:
                webhook = Webhook.from_url(
                    f"https://discord.com/api/webhooks/{webhook_id}/{webhook_token}",
                    session=session
                )
                await webhook.delete()
        except Exception as e:
            print(f"Error deleting webhook {webhook_id}: {e}")
    
    async def send_via_webhook(self, webhook_id: int, webhook_token: str,
                               content: str, username: str, avatar_url: str):
        async with aiohttp.ClientSession() as session:
            webhook = Webhook.from_url(
                f"https://discord.com/api/webhooks/{webhook_id}/{webhook_token}",
                session=session
            )
            await webhook.send(content=content, username=username, avatar_url=avatar_url)
    
    def get_available_guilds(self) -> List[Dict]:
        return list(self.guilds_cache.values())
    
    def get_channels_for_guild(self, guild_id: int) -> List[Dict]:
        return list(self.channels_cache.get(guild_id, {}).values())

bot = None

def init_bot(config):
    global bot
    bot = DiscordBot(config)
    return bot
