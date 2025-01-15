import os
import re
from typing import Tuple

import requests
import json
import time

import aiohttp
import discord
from dotenv import load_dotenv
import emoji


# functions
def get_text_with_diacritics(text: str) -> str:
    """
    for a given Czech text returns the text with added diacritics
    calls NLP FI MUNI api
    """
    data = {"call": "diacritics",
            "lang": "cs",
            "output": "json",
            "text": text.replace(';', ',')  # very important!!! if semicolon not replaced by comma, json can't read it
            }
    uri = "https://nlp.fi.muni.cz/languageservices/service.py"
    response = requests.post(uri, data=data, timeout=10000)
    response.raise_for_status()  # raises exception when not a 2xx response
    byte_data = response.content
    output = json.loads(str(byte_data, 'utf-8'))["text"]
    return output


def remove_emojis(content: str) -> Tuple[str, list[emoji.EmojiMatch], list[int]]:
    """
    Remove emojis from the given text and store the info about emoji for future use.
    Return text without emojis.
    """
    emojis = list(emoji.analyze(content))               # get all emojis from the text
    emoji_matches = [item[1] for item in emojis]        # EmojiMatch objects
    positions = [emoji_match.start for emoji_match in emoji_matches]    # indices of emojis in the text
    content_without_emojis = ""
    for i in range(len(content)):
        if i not in positions:
            content_without_emojis += content[i]
    return content_without_emojis, emoji_matches, positions


def insert_emojis(content_without_emojis: str, emoji_matches: list[emoji.EmojiMatch], positions: list[int]) -> str:
    """
    Into text, which was strip off emojis, insert the emojis to their original places.
    Return text with emojis again.
    """
    # adjust positions to insert the emojis into the text without emojis
    positions = [position - positions.index(position) for position in positions]

    content_with_emojis_again = ""
    for i in range(len(content_without_emojis)):
        if i in positions:
            content_with_emojis_again += emoji_matches.pop(0).emoji
        content_with_emojis_again += content_without_emojis[i]

        # handle the case the emoji is the last character in the original text
        if i + 1 == len(content_without_emojis) and len(positions) != 0:
            content_with_emojis_again += emoji_matches.pop(0).emoji

    return content_with_emojis_again


# end of functions
# --------------------------------------------------------------------
# global variables and setup

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

intents = discord.Intents.all()
client = discord.Client(intents=intents)

users_to_be_corrected = ["janmaly"]


# end of global variables and setup
# --------------------------------------------------------------------
# code execution

@client.event
async def on_ready():
    print(f'bot_{client.user.name} has connected to Discord!')


@client.event
async def on_message(message):
    # prevents recursive calls from the bot itself
    if message.author == client.user:
        return

    if message.author.name in users_to_be_corrected:
        # diacritics api cannot handle emojis, so they have to be returned and then inserted again
        content, emoji_matches, positions = remove_emojis(message.content)

        if len(content) >= 1000:            # handle too long texts for the diacritics api takes max. 1000 chars
            parts = []
            while len(content) >= 1000:
                # a bit more clever split looking for approximately the end of a sentence
                split_index = re.search("\\. ", content[800:]).span()[1]
                parts.append(content[:split_index])
                content = content[split_index:]
            parts.append(content)

            text_with_diacritics = ""
            for part in parts:
                text_with_diacritics += (get_text_with_diacritics(part))
                time.sleep(0.5)   # without the pause, we get an error arising from too many requests
        else:
            text_with_diacritics = get_text_with_diacritics(content)

        text_with_diacritics_and_emojis_again = insert_emojis(text_with_diacritics, emoji_matches, positions)

        response = f"{message.author.name} píše:" + os.linesep + text_with_diacritics_and_emojis_again
        await message.delete()
        await message.channel.send(response)


client.run(TOKEN)
