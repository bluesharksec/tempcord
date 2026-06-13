import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
    TURNSTILE_SECRET = os.getenv('TURNSTILE_SECRET')
    API_HOST = os.getenv('API_HOST', '0.0.0.0')
    API_PORT = int(os.getenv('API_PORT', 8000))
    
    SESSION_LIFETIME_HOURS = 24
    MAX_MESSAGES_PER_10_SECONDS = 5
    MAX_MESSAGES_PER_HOUR = 100
    
    BLOCKED_USERNAMES = [
        'admin', 'administrator', 'mod', 'moderator',
        'owner', 'discord', 'staff', 'support'
    ]
    
    ALLOWED_IMAGE_EXTENSIONS = ['png', 'jpg', 'jpeg', 'gif', 'webp']
    
    DATABASE_PATH = 'sessions.db'
