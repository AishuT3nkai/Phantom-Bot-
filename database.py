import sqlite3
from pathlib import Path

DB_PATH = Path("phantom.db")

def _db():
    return sqlite3.connect(DB_PATH)

def init_db():
    with _db() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS favorites (
            user_id INTEGER NOT NULL, guild_id INTEGER NOT NULL, track_id TEXT NOT NULL,
            title TEXT NOT NULL, author TEXT NOT NULL, uri TEXT, artwork TEXT,
            duration INTEGER DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, guild_id, track_id))""")
        db.execute("""CREATE TABLE IF NOT EXISTS settings (
            guild_id INTEGER PRIMARY KEY, default_volume INTEGER DEFAULT 75,
            max_queue INTEGER DEFAULT 100, dj_role_id INTEGER,
            autoplay INTEGER DEFAULT 0, stay_24_7 INTEGER DEFAULT 0)""")
        db.execute("""CREATE TABLE IF NOT EXISTS playlists (
            user_id INTEGER NOT NULL, guild_id INTEGER NOT NULL, name TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(user_id,guild_id,name))""")
        db.execute("""CREATE TABLE IF NOT EXISTS playlist_tracks (
            user_id INTEGER NOT NULL, guild_id INTEGER NOT NULL, name TEXT NOT NULL,
            track_id TEXT NOT NULL, title TEXT NOT NULL, author TEXT NOT NULL,
            uri TEXT, artwork TEXT, duration INTEGER DEFAULT 0, added_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(user_id,guild_id,name,track_id))""")

def add_favorite(user_id,guild_id,track):
    with _db() as db:
        db.execute("""INSERT OR REPLACE INTO favorites
        (user_id,guild_id,track_id,title,author,uri,artwork,duration)
        VALUES (?,?,?,?,?,?,?,?)""",
        (user_id,guild_id,track.identifier,track.title,track.author,track.uri,track.artwork,track.length))

def remove_favorite(user_id,guild_id,track_id):
    with _db() as db:
        db.execute("DELETE FROM favorites WHERE user_id=? AND guild_id=? AND track_id=?",(user_id,guild_id,track_id))

def get_favorites(user_id,guild_id):
    with _db() as db:
        return db.execute("""SELECT title,author,uri,artwork,duration,track_id FROM favorites
        WHERE user_id=? AND guild_id=? ORDER BY created_at DESC""",(user_id,guild_id)).fetchall()

def get_settings(guild_id):
    with _db() as db:
        row=db.execute("""SELECT default_volume,max_queue,dj_role_id,autoplay,stay_24_7
        FROM settings WHERE guild_id=?""",(guild_id,)).fetchone()
        if row is None:
            db.execute("INSERT OR IGNORE INTO settings(guild_id) VALUES(?)",(guild_id,))
            return (75,100,None,0,0)
        return row

def set_setting(guild_id,column,value):
    if column not in {"default_volume","max_queue","dj_role_id","autoplay","stay_24_7"}:
        raise ValueError("invalid setting")
    with _db() as db:
        db.execute(f"INSERT INTO settings(guild_id,{column}) VALUES(?,?) ON CONFLICT(guild_id) DO UPDATE SET {column}=excluded.{column}",(guild_id,value))

def save_playlist(user_id,guild_id,name,tracks):
    with _db() as db:
        db.execute("INSERT OR IGNORE INTO playlists(user_id,guild_id,name) VALUES(?,?,?)",(user_id,guild_id,name))
        for t in tracks:
            db.execute("""INSERT OR REPLACE INTO playlist_tracks
            (user_id,guild_id,name,track_id,title,author,uri,artwork,duration)
            VALUES(?,?,?,?,?,?,?,?,?)""",(user_id,guild_id,name,t.identifier,t.title,t.author,t.uri,t.artwork,t.length))

def delete_playlist(user_id,guild_id,name):
    with _db() as db:
        db.execute("DELETE FROM playlist_tracks WHERE user_id=? AND guild_id=? AND name=?",(user_id,guild_id,name))
        db.execute("DELETE FROM playlists WHERE user_id=? AND guild_id=? AND name=?",(user_id,guild_id,name))

def list_playlists(user_id,guild_id):
    with _db() as db:
        return [r[0] for r in db.execute("SELECT name FROM playlists WHERE user_id=? AND guild_id=? ORDER BY name",(user_id,guild_id))]

def get_playlist(user_id,guild_id,name):
    with _db() as db:
        return db.execute("""SELECT title,author,uri,artwork,duration,track_id FROM playlist_tracks
        WHERE user_id=? AND guild_id=? AND name=? ORDER BY added_at""",(user_id,guild_id,name)).fetchall()
