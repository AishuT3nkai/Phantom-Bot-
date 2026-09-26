import os
import tempfile
from pathlib import Path

with tempfile.TemporaryDirectory() as tmp:
    os.environ["PHANTOM_DB_PATH"] = str(Path(tmp) / "phantom.db")

    import database
    database.init_db()

    from music_core import Music
    from advanced_music import AdvancedMusic
    from search_music import SearchMusic

    class DummyBot:
        def add_view(self, view):
            self.view = view

        def get_cog(self, name):
            return None

    bot = DummyBot()
    music = Music(bot)
    assert hasattr(music, "restore_saved")
    assert hasattr(music, "recover_voice")
    assert hasattr(AdvancedMusic(bot), "playlist_load")
    assert hasattr(SearchMusic(bot), "multi_search")

    settings = database.get_settings(123456789)
    assert settings == (75, 100, None, 0, 0)

    database.set_setting(123456789, "stay_24_7", 1)
    assert database.get_settings(123456789)[4] == 1

for filename in ("music_core.py", "advanced_music.py", "search_music.py"):
    source = Path(filename).read_text(encoding="utf-8")
    assert "\\\\n" not in source, f"literal escaped newline found in {filename}"

print("Phantom smoke checks passed.")
