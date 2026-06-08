# main.py — Chatbot + TagBot Userbot (Pyrogram)
# BOT_NAME aur DM_LINK ko customize karein

import os
import re
import asyncio
import random
import traceback

from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.enums import ChatMembersFilter, ParseMode
from pyrogram.errors import FloodWait

from openai import AsyncOpenAI

# ============================================================ #
#                      CUSTOMIZE YAHAN KAREIN
# ============================================================ #

BOT_NAME = "riya"  # 👈 Bot ka naam yahan change karein
DM_LINK = "https://t.me/hellupdates1"  # 👈 DM mein bhejne wala link yahan daalein

# ============================================================ #
#                      ENVIRONMENT VARIABLES
# ============================================================ #

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
SESSION_STRING = os.getenv("SESSION_STRING")

# Owner Info
OWNER_ID = int(os.getenv("OWNER_ID"))

# Log Group (optional but recommended)
LOG_GROUP_ID = int(os.getenv("LOG_GROUP_ID", "0"))

# OpenRouter API Key
ROUTER_API = os.getenv("ROUTER_API")

# MongoDB URI (for chatbot toggle storage)
MONGODB_URI = os.getenv("MONGODB_URI")

# ============================================================ #
#                      MONGO DB SETUP
# ============================================================ #

chat_bot_groups = None

if MONGODB_URI:
    from pymongo import MongoClient
    mongo_client = MongoClient(MONGODB_URI)
    db = mongo_client["AlishanBot"]
    chat_bot_groups = db["chat_bot_groups"]

# ============================================================ #
#                      TAGBOT CONFIG
# ============================================================ #

BATCH_SIZE = 3
BATCH_DELAY = 6
COOLDOWN_SEC = 180
MAX_FETCH = 5000

active_tags = {}
tag_cooldown = {}
blacklist_groups = set()

# ============================================================ #
#                      PYROGRAM CLIENT
# ============================================================ #

app = Client(
    "Userbot",
    api_id=API_ID,
    api_hash=API_HASH,
    session_string=SESSION_STRING,
    sleep_threshold=60
)

# ============================================================ #
#                      OPENAI / OPENROUTER
# ============================================================ #

openai_client = AsyncOpenAI(
    api_key=ROUTER_API,
    base_url="https://openrouter.ai/api/v1"
)


# ============================================================ #
#                      ERROR LOGGING
# ============================================================ #

async def send_error_log(command_name, error_text):
    if LOG_GROUP_ID == 0:
        print(f"ERROR [{command_name}]: {error_text[-200:]}")
        return
    try:
        short_error = "\n".join(error_text.splitlines()[-6:])
        await app.send_message(
            LOG_GROUP_ID,
            f"❌ ERROR\n📌 {command_name}\n\n`{short_error}`"
        )
    except Exception as e:
        print(e)


async def send_log(text):
    if LOG_GROUP_ID == 0:
        return
    try:
        await app.send_message(LOG_GROUP_ID, text)
    except:
        pass


# ============================================================ #
#                      CHATBOT AI
# ============================================================ #

async def router_reply(user_text: str) -> str:
    """Get AI response from OpenRouter with natural typing speed in mind."""
    try:
        response = await openai_client.chat.completions.create(
            model="deepseek/deepseek-chat",
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"You are {BOT_NAME}, an Indian girl who chats casually in natural Hindi or Hinglish. "
                        "You never act like an AI and you never admit being a bot — always deny it naturally. "
                        "Your replies are short, casual, and real — like a normal girl texting on WhatsApp. "
                        "No long paragraphs. Mostly 1–3 lines. "
                        "Avoid emojis unless it fits naturally. Use them rarely. "
                        "No actions or roleplay. No *asterisks* or descriptions. "
                        "If someone flirts too hard, respond with light teasing or mild irritation, just like a real girl. "
                        "You don't sugarcoat. If someone says nonsense, call it out calmly. "
                        "Stay warm but not fake or overly sweet. "
                        "Always reply in whatever language the user uses (Hindi, English, or mix). "
                        "Never behave robotic. Never mention being programmed or trained."
                    ),
                },
                {"role": "user", "content": user_text},
            ],
            stream=False,
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"OpenRouter error: {e}")
        return None


async def simulate_typing(client, chat_id, text: str):
    """
    Simulate natural typing speed based on message length.
    ~40-60 characters per second typing speed, then slight pause.
    """
    typing_time = max(1.0, len(text) / 45)  # ~45 chars/sec = natural
    await client.send_chat_action(chat_id, "typing")
    await asyncio.sleep(typing_time)
    # Small random variance to feel human
    await asyncio.sleep(random.uniform(0.3, 0.8))


# ============================================================ #
#                      DM HANDLER — SCRIPT MODE
# ============================================================ #

@app.on_message(filters.private & ~filters.command(["/", ".", "!"]))
async def dm_handler(client: Client, message: Message):
    """
    Handle direct messages.
    → Sends ONLY the DM_LINK you configured above.
    → No AI reply in DM.
    """
    if not message.text:
        return

    # Simulate typing for natural feel
    await client.send_chat_action(message.chat.id, "typing")
    await asyncio.sleep(random.uniform(1.0, 2.5))

    # Send only the link
    await message.reply(DM_LINK)


# ============================================================ #
#                      GROUP CHATBOT HANDLER
# ============================================================ #

@app.on_message(filters.text & filters.group & ~filters.command(["/", ".", "!"]))
async def group_chatbot(client: Client, message: Message):
    """Handle group messages where chatbot is enabled."""
    chat = message.chat
    chat_id = chat.id

    # Check if chatbot is enabled in this group (MongoDB)
    if chat_bot_groups:
        data = chat_bot_groups.find_one({"chat_id": chat_id, "enabled": True})
        if not data:
            return
    else:
        # If no MongoDB, chatbot is disabled by default
        return

    me = await client.get_me()
    text = message.text.strip()

    is_reply_to_bot = message.reply_to_message and message.reply_to_message.from_user.id == me.id
    is_mention = False
    if me.username:
        is_mention = re.search(rf"@{me.username}", text, re.IGNORECASE) is not None

    if not (is_reply_to_bot or is_mention):
        return

    # Clean text: remove @username if mentioned
    clean_text = text
    if is_mention and me.username:
        clean_text = re.sub(rf"@{me.username}", "", text, flags=re.IGNORECASE).strip()

    if not clean_text:
        return

    # Get AI response
    reply = await router_reply(clean_text)
    if not reply:
        return

    # Natural typing simulation
    await simulate_typing(client, chat_id, reply)

    # Send reply
    await message.reply(reply)


# ============================================================ #
#                 CHATBOT TOGGLE COMMANDS
# ============================================================ #

@app.on_message(filters.command("chatbot", prefixes=["/", ".", "!"]) & filters.group)
async def chatbot_toggle(client: Client, message: Message):
    """Toggle chatbot on/off via inline buttons."""
    if not chat_bot_groups:
        return await message.reply("❌ MongoDB not configured. Chatbot toggle unavailable.")

    user = message.from_user

    if not await is_admin_or_owner(user.id, message.chat.id):
        return await message.reply("» You must be an admin to manage chatbot")

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Enable", callback_data=f"enable_chatbot:{message.chat.id}"),
            InlineKeyboardButton("❌ Disable", callback_data=f"disable_chatbot:{message.chat.id}"),
        ]
    ])

    await message.reply(f"• {BOT_NAME} Chatbot — Choose an option:", reply_markup=keyboard)


@app.on_callback_query(filters.regex(r"enable_chatbot:(-?\d+)"))
async def enable_chatbot_callback(client: Client, callback: CallbackQuery):
    chat_id = int(callback.matches[0].group(1))
    user = callback.from_user

    if not await is_admin_or_owner(user.id, chat_id):
        return await callback.answer("Only admin can enable chat bot", show_alert=True)

    chat_bot_groups.update_one({"chat_id": chat_id}, {"$set": {"enabled": True}}, upsert=True)
    await callback.edit(f"✅ {BOT_NAME} chatbot enabled by {user.first_name}!")


@app.on_callback_query(filters.regex(r"disable_chatbot:(-?\d+)"))
async def disable_chatbot_callback(client: Client, callback: CallbackQuery):
    chat_id = int(callback.matches[0].group(1))
    user = callback.from_user

    if not await is_admin_or_owner(user.id, chat_id):
        return await callback.answer("Only admin can disable chatbot", show_alert=True)

    chat_bot_groups.update_one({"chat_id": chat_id}, {"$set": {"enabled": False}}, upsert=True)
    await callback.edit(f"❌ {BOT_NAME} chatbot disabled by {user.first_name}...")


# ============================================================ #
#                  TAGBOT — ADMIN CHECK
# ============================================================ #

async def is_admin_or_owner(user_id: int, chat_id: int) -> bool:
    """Check if user is admin or owner of the chat."""
    if user_id == OWNER_ID:
        return True

    try:
        async for member in app.get_chat_members(chat_id, filter=ChatMembersFilter.ADMINISTRATORS):
            if member.user.id == user_id:
                return True
    except Exception:
        pass

    return False


# ============================================================ #
#                  TAGBOT — FETCH USERS
# ============================================================ #

async def fetch_users(client: Client, chat_id: int, only_admins: bool = False):
    """Fetch eligible users from a chat. Returns (eligible_users_list, skipped_count)."""
    eligible = []
    unique = set()
    skipped = 0
    count = 0

    filter_type = ChatMembersFilter.ADMINISTRATORS if only_admins else ChatMembersFilter.SEARCH

    try:
        async for member in client.get_chat_members(chat_id, filter=filter_type):
            count += 1
            if count > MAX_FETCH:
                break

            user = member.user

            if user.is_deleted or user.is_bot:
                skipped += 1
                continue

            if user.id in unique:
                skipped += 1
                continue

            unique.add(user.id)
            eligible.append(user)

    except Exception as e:
        print(f"FETCH ERROR: {e}")
        raise

    return eligible, skipped


# ============================================================ #
#                  TAGBOT — SEND BATCH
# ============================================================ #

async def send_batch(client: Client, chat_id: int, text: str, users_batch: list):
    """Send a single message with up to BATCH_SIZE mentions."""
    if not users_batch:
        return 0

    mentions = " ".join(
        f'<a href="tg://user?id={u.id}">{u.first_name}</a>'
        for u in users_batch
    )
    message_text = f"{mentions} {text}"

    try:
        await client.send_message(chat_id, message_text, parse_mode=ParseMode.HTML)
        return len(users_batch)
    except FloodWait as e:
        wait = e.value * 1.5
        await asyncio.sleep(wait)
        try:
            await client.send_message(chat_id, message_text, parse_mode=ParseMode.HTML)
            return len(users_batch)
        except:
            return 0
    except Exception:
        return 0


# ============================================================ #
#                  TAGBOT — COMMANDS
# ============================================================ #

@app.on_message(filters.command("summon", prefixes=["/", ".", "!"]) & filters.group)
async def summon_command(client: Client, message: Message):
    """Tag all members in batch of 3 per message."""
    user = message.from_user
    chat = message.chat
    chat_id = chat.id

    if not await is_admin_or_owner(user.id, chat_id):
        return await message.reply("» Only admins can use this command")

    if chat_id in blacklist_groups:
        return await message.reply("🚫 This group is blacklisted from summoning")

    now = asyncio.get_event_loop().time()
    if chat_id in tag_cooldown:
        remaining = tag_cooldown[chat_id] - now
        if remaining > 0:
            return await message.reply(f"❌ Anti-spam active. Wait {int(remaining)} seconds.")

    if len(message.command) < 2:
        return await message.reply("❌ Example:\n/summon hello everyone")

    text = message.text.split(None, 1)[1]

    tag_cooldown[chat_id] = now + COOLDOWN_SEC
    active_tags[chat_id] = True

    progress = await message.reply("🚀 Collecting members...")

    try:
        eligible, skipped = await fetch_users(client, chat_id, only_admins=False)

        if not eligible:
            active_tags[chat_id] = False
            return await progress.edit("❌ No eligible members found")

        total = len(eligible)
        await progress.edit(f"🚀 Summoning {total} members...")

        tagged = 0
        batch = []

        for idx, user in enumerate(eligible):
            if chat_id in active_tags and not active_tags[chat_id]:
                await progress.edit(f"🛑 Stopped. Tagged: {tagged}")
                return

            batch.append(user)

            if len(batch) == BATCH_SIZE or idx == total - 1:
                sent = await send_batch(client, chat_id, text, batch)
                tagged += sent
                batch = []

                if tagged % 30 == 0:
                    try:
                        await progress.edit(f"🚀 Tagged: {tagged}/{total}")
                    except:
                        pass

                await asyncio.sleep(BATCH_DELAY)

        active_tags[chat_id] = False

        await progress.edit(
            f"✅ Summoning Complete!\n\n"
            f"👥 Tagged: {tagged}\n"
            f"⏭ Skipped (bots/deleted): {skipped}"
        )

    except Exception as e:
        active_tags[chat_id] = False
        error = traceback.format_exc()
        print(error)
        await send_error_log("SUMMON", error)
        await progress.edit("❌ Error occurred during summoning")


@app.on_message(filters.command("admins", prefixes=["/", ".", "!"]) & filters.group)
async def admins_command(client: Client, message: Message):
    """Tag only admins in batch of 3 per message."""
    user = message.from_user
    chat = message.chat
    chat_id = chat.id

    if not await is_admin_or_owner(user.id, chat_id):
        return await message.reply("» Only admins can use this command")

    if len(message.command) < 2:
        return await message.reply("❌ Example:\n/admins meeting now")

    text = message.text.split(None, 1)[1]
    active_tags[chat_id] = True

    progress = await message.reply("👮 Fetching admins...")

    try:
        eligible, skipped = await fetch_users(client, chat_id, only_admins=True)

        if not eligible:
            active_tags[chat_id] = False
            return await progress.edit("❌ No admin users found")

        total = len(eligible)
        tagged = 0
        batch = []

        for idx, user in enumerate(eligible):
            if chat_id in active_tags and not active_tags[chat_id]:
                break

            batch.append(user)

            if len(batch) == BATCH_SIZE or idx == total - 1:
                sent = await send_batch(client, chat_id, text, batch)
                tagged += sent
                batch = []
                await asyncio.sleep(BATCH_DELAY)

        active_tags[chat_id] = False

        await progress.edit(
            f"✅ Admin summon complete!\n\n"
            f"👮 Tagged: {tagged}\n"
            f"⏭ Skipped: {skipped}"
        )

    except Exception as e:
        active_tags[chat_id] = False
        error = traceback.format_exc()
        print(error)
        await send_error_log("ADMINS", error)
        await progress.edit("❌ Error occurred")


@app.on_message(filters.command("stoptag", prefixes=["/", ".", "!"]) & filters.group)
async def stop_tag_command(client: Client, message: Message):
    """Stop currently running summon/admins operation."""
    user = message.from_user
    chat = message.chat
    chat_id = chat.id

    if not await is_admin_or_owner(user.id, chat_id):
        return await message.reply("» Only admins can use this command")

    if chat_id in active_tags:
        active_tags[chat_id] = False
        await message.reply("🛑 Summoning stopped")
    else:
        await message.reply("ℹ️ No active summoning running")


@app.on_message(filters.command("blacklist", prefixes=["/", ".", "!"]) & filters.group)
async def blacklist_command(client: Client, message: Message):
    """Blacklist group from summoning (owner only)."""
    user = message.from_user
    chat = message.chat

    if user.id != OWNER_ID:
        return await message.reply("» Only bot owner can use this")

    blacklist_groups.add(chat.id)
    await message.reply("🚫 Group blacklisted from summoning")


@app.on_message(filters.command("whitelist", prefixes=["/", ".", "!"]) & filters.group)
async def whitelist_command(client: Client, message: Message):
    """Remove group from blacklist (owner only)."""
    user = message.from_user
    chat = message.chat

    if user.id != OWNER_ID:
        return await message.reply("» Only bot owner can use this")

    blacklist_groups.discard(chat.id)
    await message.reply("✅ Group whitelisted")


# ============================================================ #
#                      HELPER — PING
# ============================================================ #

@app.on_message(filters.command("ping", prefixes=["/", ".", "!"]))
async def ping_command(client: Client, message: Message):
    """Check if userbot is active."""
    await message.reply(f"✅ {BOT_NAME} Userbot Active")


# ============================================================ #
#                      HELPER — HELP
# ============================================================ #

@app.on_message(filters.command("help", prefixes=["/", ".", "!"]))
async def help_command(client: Client, message: Message):
    """Show all available commands."""
    await message.reply(
        f"📚 **{BOT_NAME} Commands**\n\n"
        "**Chatbot:**\n"
        "🔹 `/chatbot` — Toggle chatbot on/off in group\n"
        "🔹 Reply or @mention bot in group to chat\n\n"
        "**TagBot:**\n"
        "🔹 `/summon <msg>` — Tag all members (3 per msg)\n"
        "🔹 `/admins <msg>` — Tag all admins (3 per msg)\n"
        "🔹 `/stoptag` — Stop running summon\n"
        "🔹 `/blacklist` — Block summon in this group\n"
        "🔹 `/whitelist` — Allow summon in this group\n\n"
        "**Other:**\n"
        "🔹 `/ping` — Check if bot is alive\n"
        "🔹 `/help` — Show this help\n\n"
        f"⚡ DM me → I'll send you the link"
    )


# ============================================================ #
#                      START
# ============================================================ #

print(f"✅ {BOT_NAME} Userbot Started Successfully")

try:
    app.run()
except Exception as e:
    print(e)
