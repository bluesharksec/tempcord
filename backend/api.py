from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict
import aiohttp
import uuid
from datetime import datetime, timedelta, timezone
import re

from config import Config
from database import Database
from bot import init_bot, bot
from rate_limiter import RateLimiter
from cleanup import CleanupService

app = FastAPI()
config = Config()
db = Database(config.DATABASE_PATH)
rate_limiter = RateLimiter(db)

# CORS for GitHub Pages
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class CreateSessionRequest(BaseModel):
    guild_id: str
    channel_id: str
    username: str
    avatar_url: str
    turnstile_token: str

class SendMessageRequest(BaseModel):
    session_id: str
    content: str

class GuildResponse(BaseModel):
    id: str
    name: str
    icon: str | None

class ChannelResponse(BaseModel):
    id: str
    name: str

# Background cleanup task
cleanup_service = None

@app.on_event("startup")
async def startup_event():
    global cleanup_service
    # Start bot
    await init_bot(config).start(config.DISCORD_TOKEN)
    
    # Start cleanup service
    cleanup_service = CleanupService(db)
    asyncio.create_task(cleanup_service.run())

@app.on_event("shutdown")
async def shutdown_event():
    if cleanup_service:
        cleanup_service.stop()
    if bot:
        await bot.close()

async def verify_turnstile(token: str) -> bool:
    async with aiohttp.ClientSession() as session:
        data = {
            'secret': config.TURNSTILE_SECRET,
            'response': token
        }
        async with session.post('https://challenges.cloudflare.com/turnstile/v0/siteverify', 
                               data=data) as resp:
            result = await resp.json()
            return result.get('success', False)

def validate_username(username: str) -> tuple[bool, str]:
    username_lower = username.lower()
    
    for blocked in config.BLOCKED_USERNAMES:
        if blocked in username_lower:
            return False, f"Username cannot contain '{blocked}'"
    
    if len(username) < 2 or len(username) > 32:
        return False, "Username must be between 2 and 32 characters"
    
    if not re.match(r'^[\w\s\-]+$', username):
        return False, "Username can only contain letters, numbers, spaces, and hyphens"
    
    return True, ""

def validate_avatar_url(url: str) -> tuple[bool, str]:
    if not url.startswith('https://'):
        return False, "Avatar URL must use HTTPS"
    
    extension = url.split('.')[-1].lower().split('?')[0]
    if extension not in config.ALLOWED_IMAGE_EXTENSIONS:
        return False, f"Avatar URL must end with: {', '.join(config.ALLOWED_IMAGE_EXTENSIONS)}"
    
    return True, ""

def validate_guild_access(guild_id: str) -> tuple[bool, str]:
    if not bot:
        return False, "Bot not ready"
    
    if int(guild_id) not in bot.guilds_cache:
        return False, "Bot not in this server"
    
    return True, ""

def validate_channel_access(guild_id: str, channel_id: str) -> tuple[bool, str]:
    if not bot:
        return False, "Bot not ready"
    
    channels = bot.channels_cache.get(int(guild_id), {})
    if int(channel_id) not in channels:
        return False, "Channel not accessible"
    
    return True, ""

@app.get("/guilds", response_model=List[GuildResponse])
async def get_guilds():
    if not bot:
        raise HTTPException(status_code=503, detail="Bot not ready")
    
    return bot.get_available_guilds()

@app.get("/channels/{guild_id}", response_model=List[ChannelResponse])
async def get_channels(guild_id: str):
    if not bot:
        raise HTTPException(status_code=503, detail="Bot not ready")
    
    valid, error = validate_guild_access(guild_id)
    if not valid:
        raise HTTPException(status_code=403, detail=error)
    
    return bot.get_channels_for_guild(int(guild_id))

@app.post("/create-session")
async def create_session(request: CreateSessionRequest):
    # Verify captcha
    if not await verify_turnstile(request.turnstile_token):
        raise HTTPException(status_code=400, detail="Invalid captcha")
    
    # Validate username
    valid, error = validate_username(request.username)
    if not valid:
        raise HTTPException(status_code=400, detail=error)
    
    # Validate avatar URL
    valid, error = validate_avatar_url(request.avatar_url)
    if not valid:
        raise HTTPException(status_code=400, detail=error)
    
    # Validate guild access
    valid, error = validate_guild_access(request.guild_id)
    if not valid:
        raise HTTPException(status_code=403, detail=error)
    
    # Validate channel access
    valid, error = validate_channel_access(request.guild_id, request.channel_id)
    if not valid:
        raise HTTPException(status_code=403, detail=error)
    
    # Create webhook
    try:
        webhook_id, webhook_token = await bot.create_webhook(
            int(request.channel_id),
            request.username,
            request.avatar_url
        )
    except PermissionError:
        raise HTTPException(status_code=403, detail="Bot cannot create webhook in this channel")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create webhook: {str(e)}")
    
    # Create session
    session_id = str(uuid.uuid4())
    expires_at = datetime.now(timezone.utc) + timedelta(hours=config.SESSION_LIFETIME_HOURS)
    
    success = db.create_session(
        session_id, request.guild_id, request.channel_id,
        str(webhook_id), webhook_token, request.username,
        request.avatar_url, expires_at
    )
    
    if not success:
        await bot.delete_webhook(webhook_id, webhook_token)
        raise HTTPException(status_code=500, detail="Failed to create session")
    
    return {
        "session_id": session_id,
        "expires_at": expires_at.isoformat()
    }

@app.post("/send-message")
async def send_message(request: SendMessageRequest):
    # Get session
    session = db.get_session(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Check expiration
    expires_at = datetime.fromisoformat(session['expires_at'])
    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=403, detail="Session expired")
    
    # Validate content
    valid, error = rate_limiter.validate_content(request.content)
    if not valid:
        raise HTTPException(status_code=400, detail=error)
    
    # Check rate limits
    valid, error = rate_limiter.check_rate_limit(request.session_id)
    if not valid:
        raise HTTPException(status_code=429, detail=error)
    
    # Send message
    try:
        await bot.send_via_webhook(
            int(session['webhook_id']),
            session['webhook_token'],
            request.content,
            session['username'],
            session['avatar_url']
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send message: {str(e)}")
    
    # Log message for rate limiting
    db.log_message(request.session_id)
    
    return {"success": True, "message": "Message sent successfully"}

@app.get("/session/{session_id}")
async def get_session(session_id: str):
    session = db.get_session(session_id)
    if not session:
        return {"valid": False}
    
    expires_at = datetime.fromisoformat(session['expires_at'])
    is_valid = expires_at > datetime.now(timezone.utc)
    
    return {
        "valid": is_valid,
        "expires_at": session['expires_at']
    }
