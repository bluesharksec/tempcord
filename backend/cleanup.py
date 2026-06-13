import asyncio
from datetime import datetime, timezone
from database import Database
from bot import bot

class CleanupService:
    def __init__(self, db: Database):
        self.db = db
        self.running = True
    
    async def run(self):
        while self.running:
            try:
                await self.cleanup_expired_sessions()
                await asyncio.sleep(60)  # Run every minute
            except Exception as e:
                print(f"Cleanup error: {e}")
                await asyncio.sleep(60)
    
    async def cleanup_expired_sessions(self):
        expired_sessions = self.db.get_expired_sessions()
        
        for session in expired_sessions:
            try:
                # Delete webhook from Discord
                if bot and not bot.is_closed():
                    await bot.delete_webhook(
                        int(session['webhook_id']),
                        session['webhook_token']
                    )
                
                # Delete from database
                self.db.delete_session(session['session_id'])
                
                print(f"Cleaned up expired session: {session['session_id']} "
                      f"(expired at {session['expires_at']})")
                
            except Exception as e:
                print(f"Error cleaning up session {session['session_id']}: {e}")
    
    def stop(self):
        self.running = False
