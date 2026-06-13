from datetime import datetime, timedelta, timezone
from database import Database

class RateLimiter:
    def __init__(self, db: Database):
        self.db = db
    
    def check_rate_limit(self, session_id: str) -> tuple[bool, str]:
        # Check 10 seconds limit
        since_10s = datetime.now(timezone.utc) - timedelta(seconds=10)
        count_10s = self.db.get_message_count(session_id, since_10s)
        
        if count_10s >= 5:
            return False, "Rate limit exceeded: Maximum 5 messages per 10 seconds"
        
        # Check 1 hour limit
        since_1h = datetime.now(timezone.utc) - timedelta(hours=1)
        count_1h = self.db.get_message_count(session_id, since_1h)
        
        if count_1h >= 100:
            return False, "Rate limit exceeded: Maximum 100 messages per hour"
        
        return True, ""
    
    def validate_content(self, content: str) -> tuple[bool, str]:
        blocked_mentions = ['@everyone', '@here']
        
        for mention in blocked_mentions:
            if mention in content.lower():
                return False, f"Message cannot contain {mention}"
        
        return True, ""
