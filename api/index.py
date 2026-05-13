import os

from skill_scout.server import create_app

# Vercel serverless is ephemeral; keep SQLite in /tmp by default.
app = create_app(os.getenv("SKILL_SCOUT_DB", "/tmp/skill_scout.db"))

