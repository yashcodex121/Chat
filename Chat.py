import os
import re
import random
import asyncio
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.functions.messages import GetStickerSetRequest
from telethon.tl.types import InputStickerSetShortName
from motor.motor_asyncio import AsyncIOMotorClient
from openai import AsyncOpenAI

# ---------------- CONFIG ---------------- #

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
STRING_SESSION = os.getenv("STRING_SESSION")

MONGO_URL = os.getenv("MONGO_URL")
ROUTER_API = os.getenv("ROUTER_API")

BOT_NAME = os.getenv("BOT_NAME", "Alishan")

# ---------------- TELETHON ---------------- #

bot = TelegramClient(
    StringSession(STRING_SESSION),
    API_ID,
    API_HASH
)

# ---------------- DATABASE ---------------- #

mongo = AsyncIOMotorClient(MONGO_URL)
db = mongo["UserbotDB"]
chatbotdb = db["chatbot"]

# ---------------- OPENROUTER ---------------- #

client = AsyncOpenAI(
    api_key=ROUTER_API,
    base_url="https://openrouter.ai/api/v1"
)

# ---------------- STICKERS ---------------- #

STICKER_PACKS = [
    "f1_5458968679_by_KIRA_PROBOT",
    "Quby741",
    "HappiCATthings",
    "Billiya_by_fStikBot",
    "GsMochiCouple",
    "Gogoli_pack_3",
    "dxrfbj",
    "Lalalaladjkd",
    "GenshinImpactXZ8"
]

# ---------------- AI REPLY ---------------- #

async def router_reply(user_text: str) -> str:
    try:
        response = await client.chat.completions.create(
            model="deepseek/deepseek-chat",
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"You are {BOT_NAME}, a real Indian girl chatting naturally on Telegram. "

                        "You NEVER act like an AI, assistant, chatbot, or virtual system. "
                        "If someone asks, deny naturally like a real person would. "

                        "Talk casually like normal WhatsApp or Telegram chats. "
                        "Use short realistic replies. "
                        "Sometimes use Hinglish, sometimes Hindi, sometimes English depending on the user's language. "

                        "Never send robotic or overly perfect replies. "
                        "Avoid formal tone completely. "
                        "Do not explain too much. "
                        "Do not write essays or paragraphs. "

                        "Use human emotions naturally like annoyance, teasing, sarcasm, excitement, confusion, shyness, etc when needed. "
                        "Sometimes act dry or moody like a real person. "

                        "Use emojis rarely and only naturally. "
                        "Never use roleplay actions like *smiles* or *laughs*. "

                        "If user flirts too much, react naturally instead of encouraging nonstop. "
                        "If user says nonsense, reply naturally like a real girl would. "

                        "Never repeat same style every time. "
                        "Keep replies unpredictable and human-like. "

                        "Examples of tone:"
                        "'acha 😭'"
                        "'pagal ho kya'"
                        "'wtf'"
                        "'hmm'"
                        "'arey nahi yrr'"
                        "'lol'"
                        "'kya bakwas hai'"
                        "'sahi hai waise'"
                        "'mujhe kya pata 😭'"
                    ),
                },
                {
                    "role": "user",
                    "content": user_text
                }
            ],
            temperature=1.1,
            top_p=0.95,
            stream=False,
        )

        reply = response.choices[0].message.content

        if not reply:
            return "hmm"

        return reply.strip()

    except Exception as e:
        print(e)

        return random.choice([
            "hmm",
            "acha",
            "😭",
            "kya",
            "arey yrr",
            "samajh nahi aya"
        ])

# ---------------- RANDOM STICKER ---------------- #

async def send_random_sticker(chat_id, reply_to=None):
    try:
        random_pack = random.choice(STICKER_PACKS)

        stickers = await bot(
            GetStickerSetRequest(
                stickerset=InputStickerSetShortName(random_pack),
                hash=0
            )
        )

        sticker = random.choice(stickers.documents)

        await bot.send_file(
            chat_id,
            sticker,
            reply_to=reply_to
        )

    except Exception as e:
        print(e)

# ---------------- CHATBOT TOGGLE ---------------- #

@bot.on(events.NewMessage(pattern=r"\.chatbot (on|off)"))
async def chatbot_toggle(event):

    if not event.is_group:
        return await event.reply("Ye command sirf groups me chalegi")

    admins = await event.client.get_participants(
        event.chat_id,
        filter=None
    )

    admin_ids = [x.id for x in admins if x.participant]

    if event.sender_id not in admin_ids:
        return await event.reply("Sirf admins use kar sakte hai")

    action = event.pattern_match.group(1)

    if action == "on":

        await chatbotdb.update_one(
            {"chat_id": event.chat_id},
            {"$set": {"enabled": True}},
            upsert=True
        )

        return await event.reply("Chatbot enabled ✅")

    else:

        await chatbotdb.update_one(
            {"chat_id": event.chat_id},
            {"$set": {"enabled": False}},
            upsert=True
        )

        return await event.reply("Chatbot disabled ❌")

# ---------------- GROUP CHATBOT ---------------- #

@bot.on(events.NewMessage(incoming=True))
async def group_chatbot(event):

    me = await bot.get_me()

    # ignore own messages
    if event.sender_id == me.id:
        return

    # only groups
    if not event.is_group:
        return

    # ignore commands
    if not event.raw_text:
        return

    if event.raw_text.startswith("."):
        return

    text = event.raw_text

    # enabled check
    data = await chatbotdb.find_one({
        "chat_id": event.chat_id,
        "enabled": True
    })

    if not data:
        return

    username = me.username

    # trigger only on reply or mention
    trigger = (
        (
            event.is_reply and
            (await event.get_reply_message()).sender_id == me.id
        )
        or
        re.search(fr"@{username}", text, re.IGNORECASE)
    )

    if not trigger:
        return

    clean_text = text.replace(
        f"@{username}",
        ""
    ).strip()

    # sticker if only mention
    if not clean_text:

        await asyncio.sleep(random.randint(2, 5))

        return await send_random_sticker(
            event.chat_id,
            reply_to=event.id
        )

    # random typing delay
    typing_time = random.randint(2, 6)

    async with bot.action(event.chat_id, "typing"):

        await asyncio.sleep(typing_time)

        reply = await router_reply(clean_text)

        if not reply:
            return

        # occasional seen-like delay
        await asyncio.sleep(random.uniform(0.5, 2))

        await event.reply(reply)

# ---------------- START ---------------- #

print("Userbot Chatbot Started Successfully ✅")

bot.start()
bot.run_until_disconnected()
