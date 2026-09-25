import json
import os
import sqlite3
from pathlib import Path

DB_PATH = Path(os.getenv("PHANTOM_DB_PATH", "data/phantom.db"))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

def _db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

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
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(user_id,guild_id,name))""")
        db.execute("""CREATE TABLE IF NOT EXISTS playlist_tracks (
            user_id INTEGER NOT NULL, guild_id INTEGER NOT NULL, name TEXT NOT NULL,
            track_id TEXT NOT NULL, title TEXT NOT NULL, author TEXT NOT NULL,
            uri TEXT, artwork TEXT, duration INTEGER DEFAULT 0,
            added_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(user_id,guild_id,name,track_id))""")
        db.execute("""CREATE TABLE IF NOT EXISTS playback_history (
            guild_id INTEGER NOT NULL, user_id INTEGER, track_id TEXT NOT NULL,
            title TEXT NOT NULL, author TEXT NOT NULL, uri TEXT, artwork TEXT,
            duration INTEGER DEFAULT 0, played_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        db.execute("""CREATE TABLE IF NOT EXISTS queue_state (
            guild_id INTEGER PRIMARY KEY, voice_channel_id INTEGER,
            text_channel_id INTEGER, requester_id INTEGER, requester TEXT,
            current_json TEXT, current_position INTEGER DEFAULT 0,
            queue_json TEXT, saved_at TEXT DEFAULT CURRENT_TIMESTAMP)""")

def _pack(track):
    if not track:
        return None
    return {
        "identifier": str(track.identifier),
        "title": str(track.title),
        "author": str(track.author),
        "uri": getattr(track, "uri", None),
        "artwork": getattr(track, "artwork", None),
        "length": int(getattr(track, "length", 0) or 0),
    }

def add_favorite(user_id, guild_id, track):
    with _db() as db:
        db.execute("""INSERT OR REPLACE INTO favorites
        (user_id,guild_id,track_id,title,author,uri,artwork,duration)
        VALUES (?,?,?,?,?,?,?,?)""",
        (user_id,guild_id,track.identifier,track.title,track.author,
         getattr(track,"uri",None),getattr(track,"artwork",None),
         int(getattr(track,"length",0) or 0)))

def remove_favorite(user_id, guild_id, track_id):
    with _db() as db:
        db.execute("DELETE FROM favorites WHERE user_id=? AND guild_id=? AND track_id=?",
                   (user_id,guild_id,track_id))

def get_favorites(user_id, guild_id):
    with _db() as db:
        return db.execute("""SELECT title,author,uri,artwork,duration,track_id
        FROM favorites WHERE user_id=? AND guild_id=? ORDER BY created_at DESC""",
        (user_id,guild_id)).fetchall()

def get_settings(guild_id):
    with _db() as db:
        row=db.execute("""SELECT default_volume,max_queue,dj_role_id,autoplay,stay_24_7
        FROM settings WHERE guild_id=?""",(guild_id,)).fetchone()
        if row is None:
            db.execute("INSERT OR IGNORE INTO settings(guild_id) VALUES(?)",(guild_id,))
            return (75,100,None,0,0)
        return tuple(row)

def set_setting(guild_id, column, value):
    allowed={"default_volume","max_queue","dj_role_id","autoplay","stay_24_7"}
    if column not in allowed:
        raise ValueError("invalid setting")
    with _db() as db:
        db.execute(
            f"""INSERT INTO settings(guild_id,{column}) VALUES(?,?)
            ON CONFLICT(guild_id) DO UPDATE SET {column}=excluded.{column}""",
            (guild_id,value))

def save_playlist(user_id,guild_id,name,tracks):
    name=name.strip()[:40]
    with _db() as db:
        db.execute("INSERT OR REPLACE INTO playlists(user_id,guild_id,name) VALUES(?,?,?)",
                   (user_id,guild_id,name))
        db.execute("DELETE FROM playlist_tracks WHERE user_id=? AND guild_id=? AND name=?",
                   (user_id,guild_id,name))
        for track in tracks[:500]:
            item=_pack(track)
            db.execute("""INSERT OR REPLACE INTO playlist_tracks
            (user_id,guild_id,name,track_id,title,author,uri,artwork,duration)
            VALUES(?,?,?,?,?,?,?,?,?)""",
            (user_id,guild_id,name,item["identifier"],item["title"],item["author"],
             item["uri"],item["artwork"],item["length"]))

def delete_playlist(user_id,guild_id,name):
    with _db() as db:
        db.execute("DELETE FROM playlist_tracks WHERE user_id=? AND guild_id=? AND name=?",
                   (user_id,guild_id,name))
        db.execute("DELETE FROM playlists WHERE user_id=? AND guild_id=? AND name=?",
                   (user_id,guild_id,name))

def list_playlists(user_id,guild_id):
    with _db() as db:
        return [r[0] for r in db.execute(
            "SELECT name FROM playlists WHERE user_id=? AND guild_id=? ORDER BY name",
            (user_id,guild_id))]

def get_playlist(user_id,guild_id,name):
    with _db() as db:
        return db.execute("""SELECT title,author,uri,artwork,duration,track_id
        FROM playlist_tracks WHERE user_id=? AND guild_id=? AND name=?
        ORDER BY added_at""",(user_id,guild_id,name)).fetchall()

def export_playlist(user_id,guild_id,name):
    rows=get_playlist(user_id,guild_id,name)
    return {"version":1,"name":name,"tracks":[
        {"title":r[0],"author":r[1],"uri":r[2],"artwork":r[3],
         "duration":r[4],"track_id":r[5]} for r in rows]}

def import_playlist(user_id,guild_id,payload):
    if not isinstance(payload,dict) or not isinstance(payload.get("tracks"),list):
        raise ValueError("Invalid playlist file")
    name=str(payload.get("name","")).strip()[:40]
    if not name:
        raise ValueError("Playlist name missing")
    items=[x for x in payload["tracks"][:500] if isinstance(x,dict) and x.get("title")]
    with _db() as db:
        db.execute("INSERT OR REPLACE INTO playlists(user_id,guild_id,name) VALUES(?,?,?)",
                   (user_id,guild_id,name))
        db.execute("DELETE FROM playlist_tracks WHERE user_id=? AND guild_id=? AND name=?",
                   (user_id,guild_id,name))
        for item in items:
            track_id=str(item.get("track_id") or item.get("uri") or len(item))
            db.execute("""INSERT OR REPLACE INTO playlist_tracks
            (user_id,guild_id,name,track_id,title,author,uri,artwork,duration)
            VALUES(?,?,?,?,?,?,?,?,?)""",
            (user_id,guild_id,name,track_id,str(item.get("title","Unknown"))[:500],
             str(item.get("author","Unknown"))[:300],item.get("uri"),item.get("artwork"),
             int(item.get("duration",0) or 0)))
    return name,len(items)

def add_history(guild_id,user_id,track):
    item=_pack(track)
    with _db() as db:
        db.execute("""INSERT INTO playback_history
        (guild_id,user_id,track_id,title,author,uri,artwork,duration)
        VALUES(?,?,?,?,?,?,?,?)""",
        (guild_id,user_id,item["identifier"],item["title"],item["author"],
         item["uri"],item["artwork"],item["length"]))
        db.execute("""DELETE FROM playback_history
        WHERE guild_id=? AND rowid NOT IN
        (SELECT rowid FROM playback_history WHERE guild_id=?
         ORDER BY rowid DESC LIMIT 100)""",(guild_id,guild_id))

def get_history(guild_id,limit=20):
    with _db() as db:
        return db.execute("""SELECT title,author,uri,artwork,duration,track_id,played_at
        FROM playback_history WHERE guild_id=? ORDER BY rowid DESC LIMIT ?""",
        (guild_id,max(1,min(limit,100)))).fetchall()

def save_queue_state(guild_id,voice_channel_id,text_channel_id,requester_id,
                     requester,current,current_position,queue):
    with _db() as db:
        db.execute("""INSERT INTO queue_state
        (guild_id,voice_channel_id,text_channel_id,requester_id,requester,
         current_json,current_position,queue_json)
        VALUES(?,?,?,?,?,?,?,?)
        ON CONFLICT(guild_id) DO UPDATE SET
        voice_channel_id=excluded.voice_channel_id,
        text_channel_id=excluded.text_channel_id,
        requester_id=excluded.requester_id,
        requester=excluded.requester,
        current_json=excluded.current_json,
        current_position=excluded.current_position,
        queue_json=excluded.queue_json,
        saved_at=CURRENT_TIMESTAMP""",
        (guild_id,voice_channel_id,text_channel_id,requester_id,requester,
         json.dumps(_pack(current)),int(current_position or 0),
         json.dumps([_pack(track) for track in queue])))

def load_queue_state(guild_id):
    with _db() as db:
        row=db.execute("""SELECT voice_channel_id,text_channel_id,requester_id,
        requester,current_json,current_position,queue_json
        FROM queue_state WHERE guild_id=?""",(guild_id,)).fetchone()
    if not row:
        return None
    return {
        "voice_channel_id":row[0],
        "text_channel_id":row[1],
        "requester_id":row[2],
        "requester":row[3],
        "current":json.loads(row[4]) if row[4] else None,
        "current_position":int(row[5] or 0),
        "queue":json.loads(row[6]) if row[6] else [],
    }

def clear_queue_state(guild_id):
    with _db() as db:
        db.execute("DELETE FROM queue_state WHERE guild_id=?",(guild_id,))
