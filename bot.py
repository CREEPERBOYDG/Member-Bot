import os
import threading
import asyncio
import requests
import aiohttp

from flask import Flask, request, redirect
import discord
from discord import app_commands
from dotenv import load_dotenv

# ------------------ LOAD ENV ------------------ #
load_dotenv()

CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
BOT_TOKEN = os.getenv("BOT_TOKEN")
REDIRECT_URI = os.getenv("REDIRECT_URI")
API = "https://discord.com/api"

# ------------------ PERSISTENT STORAGE ------------------ #
# Render persistent disk path
PERSISTENT_PATH = "users.txt"

# Ensure the folder exists
os.makedirs(os.path.dirname(PERSISTENT_PATH), exist_ok=True)

# ------------------ FLASK APP ------------------ #
app = Flask(__name__)

@app.route("/")
def login():
    return redirect(
        f"{API}/oauth2/authorize"
        f"?client_id={CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}"
        f"&response_type=code"
        f"&scope=identify%20guilds.join"
    )

@app.route("/callback")
def callback():
    code = request.args.get("code")
    if not code:
        return "No code provided."

    data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI
    }

    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    token = requests.post(f"{API}/oauth2/token", data=data, headers=headers).json()

    if "access_token" not in token:
        return f"OAuth Error: {token}"

    access_token = token["access_token"]

    user = requests.get(
        f"{API}/users/@me",
        headers={"Authorization": f"Bearer {access_token}"}
    ).json()

    user_id = user["id"]

    # Append to persistent users.txt
    with open(PERSISTENT_PATH, "a") as f:
        f.write(f"{user_id}:{access_token}\n")

    return "Authorization successful!"

# Optional route to view authorized users (for debug)
@app.route("/users")
def show_users():
    if os.path.exists(PERSISTENT_PATH):
        with open(PERSISTENT_PATH, "r") as f:
            return "<br>".join(f.read().splitlines())
    return "No users yet."

# ------------------ RUN FLASK ------------------ #
def run_flask():
    port = int(os.environ.get("PORT", 10000))  # Render assigns PORT automatically
    app.run(host="0.0.0.0", port=port)

# ------------------ DISCORD BOT ------------------ #
intents = discord.Intents.default()

class MyClient(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()
        print("Commands synced!")

client = MyClient()

@client.event
async def on_ready():
    print(f"Logged in as {client.user}")

@client.tree.command(
    name="join",
    description="Join all authorized users to a specified server"
)
@app_commands.describe(server_id="The ID of the server to join")
async def join(interaction: discord.Interaction, server_id: str):
    await interaction.response.defer()
    added = 0

    try:
        with open(PERSISTENT_PATH, "r") as f:
            users = [line.strip() for line in f if line.strip()]

        async with aiohttp.ClientSession() as session:
            tasks = []

            for line in users:
                user_id, access_token = line.split(":")
                url = f"{API}/guilds/{server_id}/members/{user_id}"
                headers = {"Authorization": f"Bot {BOT_TOKEN}"}
                json_data = {"access_token": access_token}

                tasks.append(session.put(url, json=json_data, headers=headers))

            responses = await asyncio.gather(*tasks, return_exceptions=True)

            for resp in responses:
                if isinstance(resp, Exception):
                    print(resp)
                elif resp.status in (200, 201):
                    added += 1
                else:
                    print(await resp.text())

        await interaction.followup.send(
            f"Attempted to add {added} users to server {server_id}"
        )

    except FileNotFoundError:
        await interaction.followup.send("No authorized users found.")

# ------------------ START SERVICES ------------------ #
if __name__ == "__main__":
    # Run Flask in a separate thread
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    # Run Discord bot
    client.run(BOT_TOKEN)
