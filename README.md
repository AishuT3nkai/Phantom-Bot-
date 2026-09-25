# Phantom Bot

Full Discord music bot built with discord.py, Wavelink 3 and Lavalink 4.

## Playback

- /play — song, URL or playlist
- /search — searches multiple configured sources and lets the user select a result
- /join / /leave
- /pause / /resume / /skip / /previous / /stop
- /queue / /clear / /remove / /move / /jump / /shuffle
- /seek / /replay / /volume
- /repeat off|song|queue
- /filter off|nightcore|bassboost|8d|karaoke
- /autoplay
- /247
- /restore
- /history

## Personal music data

Favorites and playlists are separated by user and server.

- /favorite / /unfavorite
- /favorites @user
- @username. or a Discord mention followed by a period for public favorite lookup
- /playlist_save / /playlist_load / /playlists / /playlist_delete
- /playlist_export / /playlist_import

Other members can view another user's favorites, but only the owner can edit their own favorites.

## Music sources

The Lavalink stack is configured for YouTube and YouTube Music, SoundCloud, Bandcamp, Twitch, Vimeo, Nico, plus LavaSrc sources such as Spotify, Apple Music, Deezer, Yandex Music, Tidal, Qobuz, VK Music and JioSaavn. DuncteBot adds additional source managers including TikTok, Mixcloud, Clyp, Reddit, OCRemix, Soundgasm and Pixeldrain.

Some services are metadata sources that are mirrored to another playable source. TikTok support is included through the DuncteBot source plugin, but that upstream plugin documents TikTok as unstable, so TikTok availability can change without a bot-side code change.

## Reliability

- Persistent SQLite history and queue state
- Queue restoration with /restore
- Automatic restoration for guilds with 24/7 enabled
- Voice websocket recovery
- Track exception fallback search
- Track-stuck recovery
- Persistent now-playing card refreshed every 15 seconds
- Old music card is deleted before the refreshed card is posted
- Queue size limit configurable with /maxqueue
- DJ role support with Manage Server fallback
- GitHub Actions syntax and Python compile validation

## Deployment

Set DISCORD_TOKEN and the Lavalink password in .env.

For Docker Compose, the database is stored in ./data so container recreation does not remove saved music history, favorites or playlists.

Lavalink 4.2.2, YouTube Source 1.18.2, LavaSrc 4.8.3 and DuncteBot 1.7.1 are pinned in the configuration.
