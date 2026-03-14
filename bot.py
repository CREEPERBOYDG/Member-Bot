import os
import threading
import asyncio
import requests
import aiohttp
import json

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

OWNER_ID = 1458374465879543927

# ------------------ STORAGE ------------------ #
USERS_FILE = "users.json"

def load_users():
    if not os.path.exists(USERS_FILE):
        return {}

    try:
        with open(USERS_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f)

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

    token = requests.post(
        f"{API}/oauth2/token",
        data=data,
        headers=headers
    ).json()

    if "access_token" not in token:
        return f"OAuth Error: {token}"

    access_token = token["access_token"]

    user = requests.get(
        f"{API}/users/@me",
        headers={"Authorization": f"Bearer {access_token}"}
    ).json()

    user_id = user["id"]

    users = load_users()

    # Prevent duplicates
    if user_id not in users:
        users[user_id] = access_token
        save_users(users)

    return "Authorization successful!"

# Debug route
@app.route("/users")
def show_users():
    users = load_users()
    return "<br>".join(users.keys()) if users else "No users yet."

# ------------------ RUN FLASK ------------------ #
def run_flask():
    port = int(os.environ.get("PORT") or 10000)
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

# ------------------ JOIN COMMAND ------------------ #
@client.tree.command(
    name="join",
    description="Join authorized users to a server"
)
@app_commands.describe(
    server_id="Server ID to join",
    amount="How many members to add"
)
async def join(interaction: discord.Interaction, server_id: str, amount: int):

    # Owner protection
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message(
            "You cannot use this command.",
            ephemeral=True
        )
        return

    await interaction.response.defer()

    users = load_users()

    if not users:
        await interaction.followup.send("No authorized users.")
        return

    added = 0

    async with aiohttp.ClientSession() as session:

        for user_id, access_token in list(users.items())[:amount]:

            url = f"{API}/guilds/{server_id}/members/{user_id}"

            headers = {
                "Authorization": f"Bot {BOT_TOKEN}"
            }

            json_data = {
                "access_token": access_token
            }

            try:
                async with session.put(url, json=json_data, headers=headers) as resp:

                    if resp.status in (200, 201):
                        added += 1

            except Exception as e:
                print(e)

            # Rate limit protection
            await asyncio.sleep(0.7)

    await interaction.followup.send(
        f"Added **{added} members** to server `{server_id}`"
    )

# ------------------ START SERVICES ------------------ #
if __name__ == "__main__":

    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    client.run(BOT_TOKEN)
