import sqlite3
from pathlib import Path

DB_PATH = Path("phantom.db")

def init_db():
    with sqlite3.connect(DB_PATH) as db:
        db.execute("""CREATE TABLE IF NOT EXISTS favorites (
            user_id INTEGER NOT NULL, guild_id INTEGER NOT NULL, track_id TEXT NOT NULL,
            title TEXT NOT NULL, author TEXT NOT NULL, uri TEXT, artwork TEXT,
            duration INTEGER DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, guild_id, track_id))""")
        db.execute("""CREATE TABLE IF NOT EXISTS settings (
            guild_id INTEGER PRIMARY KEY, default_volume INTEGER DEFAULT 75,
            max_queue INTEGER DEFAULT 100, dj_role_id INTEGER,
            autoplay INTEGER DEFAULT 0, stay_24_7 INTEGER DEFAULT 0)""")

def add_favorite(user_id, guild_id, track):
    with sqlite3.connect(DB_PATH) as db:
        db.execute("""INSERT OR REPLACE INTO favorites
            (user_id,guild_id,track_id,title,author,uri,artwork,duration)
            VALUES (?,?,?,?,?,?,?,?)""",
            (user_id,guild_id,track.identifier,track.title,track.author,track.uri,track.artwork,track.length))

def remove_favorite(user_id, guild_id, track_id):
    with sqlite3.connect(DB_PATH) as db:
        db.execute("DELETE FROM favorites WHERE user_id=? AND guild_id=? AND track_id=?",
                   (user_id,guild_id,track_id))

def get_favorites(user_id, guild_id):
    with sqlite3.connect(DB_PATH) as db:
        return db.execute("""SELECT title,author,uri,artwork,duration,track_id
            FROM favorites WHERE user_id=? AND guild_id=? ORDER BY created_at DESC""",
            (user_id,guild_id)).fetchall()

def get_settings(guild_id):
    with sqlite3.connect(DB_PATH) as db:
        row = db.execute("""SELECT default_volume,max_queue,dj_role_id,autoplay,stay_24_7
            FROM settings WHERE guild_id=?""",(guild_id,)).fetchone()
        if row is None:
            db.execute("INSERT OR IGNORE INTO settings(guild_id) VALUES(?)",(guild_id,))
            return (75,100,None,0,0)
        return row
