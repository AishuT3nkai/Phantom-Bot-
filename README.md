# Phantom Bot

Full Discord music bot powered by discord.py, Wavelink 3 and Lavalink v4.

## Playback
- /play — search, URL or playlist
- /search — multi-source search with result selection
- /pause /resume /skip /previous /stop /leave
- /seek /replay /volume
- /queue /remove /move /jump /clear /shuffle
- /repeat off|song|queue
- /filter off|nightcore|bassboost|8d|karaoke
- /autoplay
- /247
- /history

## Personal music data
- /favorite /unfavorite
- /favorites @user
- @username. public favorite lookup
- /playlist_save
- /playlist_load
- /playlists
- /playlist_delete

Favorites and playlists are separated by user and server. Other members can view another member's favorites, but they cannot edit that member's collection.

## Sources

The Lavalink/LavaSrc stack is configured for a broad source set including YouTube/YouTube Music, SoundCloud and multiple metadata providers such as Spotify, Apple Music, Deezer, Tidal, Qobuz, Yandex Music, VK Music and JioSaavn. Additional Lavalink plugins are configured for sources including TikTok and Mixcloud.

Source availability depends on the upstream platform and plugin. Some services provide metadata that is resolved to a playable mirror rather than direct audio.

## Now-playing card

The current track artwork is used as the card background. The card shows title, artist, requester, playback state, duration and a progress bar. The old card is deleted before a refreshed card is posted, preventing a channel from filling with stale cards.

## Stack

Python 3.12, discord.py 2.x, Wavelink 3, Lavalink v4, SQLite and Pillow.

Wavelink provides native queue history, queue modes, seeking, autoplay and audio filters. See the current Wavelink API for the supported Player, Queue and Filters interfaces.

## Setup

Copy .env.example to .env and set the bot token. Keep the Lavalink password identical in .env and lavalink/application.yml.

Docker:

docker compose up -d --build

Normal Python:

pip install -r requirements.txt
java -jar Lavalink.jar
python main.py

Required Discord permissions include View Channel, Send Messages, Attach Files, Connect, Speak and Read Message History.

Enable Message Content and Server Members intents in the Discord Developer Portal.

Never commit .env or a real bot token.
