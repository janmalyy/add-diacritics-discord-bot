import os
import re
from typing import Tuple
import requests
import json
import time
import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
import emoji
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading


# functions and classes
def get_text_with_diacritics(text: str) -> str:
    """
    For a given Czech text, returns the text with added diacritics
    Calls NLP FI MUNI API.
    """
    data = {
        "call": "diacritics",
        "lang": "cs",
        "output": "json",
        "text": text.replace(';', ',')  # Very important! If semicolon not replaced, JSON can't parse it.
    }
    uri = "https://nlp.fi.muni.cz/languageservices/service.py"
    response = requests.post(uri, data=data, timeout=10000)
    response.raise_for_status()  # Raises exception when not a 2xx response
    byte_data = response.content
    output = json.loads(byte_data.decode('utf-8'))["text"]  # Parse JSON response
    return output


def remove_emojis(content: str) -> Tuple[str, list[emoji.EmojiMatch], list[int]]:
    """
    Remove emojis from the given text and store the info about emoji for future use.
    Return text without emojis.
    """
    emojis = list(emoji.analyze(content))  # Get all emojis from the text
    emoji_matches = [item[1] for item in emojis]  # EmojiMatch objects
    positions = [emoji_match.start for emoji_match in emoji_matches]  # Indices of emojis in the text
    content_without_emojis = ""
    for i in range(len(content)):
        if i not in positions:
            content_without_emojis += content[i]
    return content_without_emojis, emoji_matches, positions


def insert_emojis(content_without_emojis: str, emoji_matches: list[emoji.EmojiMatch], positions: list[int]) -> str:
    """
    Into text, which was stripped of emojis, insert the emojis to their original places.
    Return text with emojis again.
    """
    # Adjust positions to insert the emojis into the text without emojis
    positions = [position - positions.index(position) for position in positions]

    content_with_emojis_again = ""
    for i in range(len(content_without_emojis)):
        if i in positions:
            content_with_emojis_again += emoji_matches.pop(0).emoji
        content_with_emojis_again += content_without_emojis[i]

        # Handle the case the emoji is the last character in the original text
        if i + 1 == len(content_without_emojis) and len(positions) > 1:
            content_with_emojis_again += emoji_matches.pop(0).emoji

    return content_with_emojis_again


class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(b'OK')


def run_health_check_server():
    server_address = ('', 8000)
    httpd = HTTPServer(server_address, HealthCheckHandler)
    httpd.serve_forever()


# end of functions and classes
# --------------------------------------------------------------------
# global variables and setup

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

bot = commands.Bot(command_prefix="!", intents=discord.Intents.all())
# (Bot vs. Client? Use Bot, it is a subclass of Client with extensions, for example for slash commands)

users_to_be_corrected = []


# end of global variables and setup
# --------------------------------------------------------------------
# code execution

@bot.event
async def on_ready():
    print(f'bot_{bot.user.name} has connected to Discord!')
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s).")
    except Exception as e:
        print(e, "There is a problem syncing the bot commands!!!")


@bot.tree.command(name="add_me")
async def add_me(interaction: discord.Interaction):
    name = interaction.user.name
    if name not in users_to_be_corrected:
        users_to_be_corrected.append(name)
        await interaction.response.send_message(
            f"Hi {interaction.user.name}, you have been added to be checked for diacritics.", ephemeral=True)
    else:
        await interaction.response.send_message(
            f"Hey {interaction.user.name}, you have been **already** added to be checked for diacritics. No need to "
            f"repeat this.", ephemeral=True)


@bot.tree.command(name="remove_me")
async def remove_me(interaction: discord.Interaction):
    name = interaction.user.name
    if name in users_to_be_corrected:
        users_to_be_corrected.remove(name)
        await interaction.response.send_message(
            f"Hi {interaction.user.name}, you have been removed from checking for diacritics.", ephemeral=True)
    else:
        await interaction.response.send_message(
            f"Hi {interaction.user.name}, you could not be removed from checking for diacritics since you were not "
            f"added here. ", ephemeral=True)


@bot.event
async def on_message(message):
    # Prevents recursive calls from the bot itself
    if message.author == bot.user:
        return

    if message.author.name in users_to_be_corrected:
        # Diacritics API cannot handle emojis, so they have to be returned and then inserted again
        content, emoji_matches, positions = remove_emojis(message.content)

        try:
            if len(content) >= 1000:  # Handle too long texts for the diacritics API takes max. 1000 chars
                parts = []
                while len(content) >= 1000:
                    # A bit more clever split looking for approximately the end of a sentence
                    split_index = re.search("\\. ", content[800:]).span()[1]
                    parts.append(content[:split_index])
                    content = content[split_index:]
                parts.append(content)

                text_with_diacritics = ""
                for part in parts:
                    text_with_diacritics += get_text_with_diacritics(part)
                    time.sleep(0.5)  # Without the pause, we get an error arising from too many requests
            else:
                text_with_diacritics = get_text_with_diacritics(content)

            text_with_diacritics_and_emojis_again = insert_emojis(text_with_diacritics, emoji_matches, positions)

            response = f"{message.author.name} píše:" + os.linesep + text_with_diacritics_and_emojis_again
            await message.delete()
            await message.channel.send(response)

        except json.JSONDecodeError:
            await message.channel.send(
                f"Ups:( Sorry, we were not able to parse your input, {message.author.name}."
                f" *This message will soon disappear.*", delete_after=4)
        except Exception as e:
            await message.channel.send(
                f"{message.author.name}, an error occurred while processing your message: {str(e)}"
                f" *This message will soon disappear.*", delete_after=4)


if __name__ == '__main__':
    # Start health check server in a separate thread
    health_check_thread = threading.Thread(target=run_health_check_server)
    health_check_thread.daemon = True
    health_check_thread.start()

    # Run the Discord bot
    bot.run(TOKEN)
