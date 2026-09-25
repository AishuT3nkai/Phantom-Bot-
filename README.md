# Phantom Bot

Full Discord music bot powered by discord.py, Wavelink and Lavalink v4.

## Music

- /play
- /pause
- /resume
- /skip
- /stop
- /queue
- /shuffle
- /volume
- /leave
- /favorite
- /unfavorite
- /favorites

The player renders a dynamic image card from the current track artwork. The old card is deleted and a fresh card is posted every 60 seconds, so the progress bar advances without filling the channel with old cards.

Favorites are stored separately for every user and server. Use /favorites @user to view another member's collection. The message listener also supports @username. when the member name matches.

## Stack

Python 3.12, discord.py 2.x, Wavelink 3, Lavalink v4, YouTube Source, LavaSrc, SQLite and Pillow.

Lavalink v4 requires Java 17+.

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
