# main.py — Chatbot + TagBot Userbot (Pyrogram)
# Heroku Compatible

import os
import re
import asyncio
import random

from pyrogram import Client, filters, idle
from pyrogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from openai import AsyncOpenAI
from tagbot import register_tagbot

# ============================================================ #
#                      CUSTOMIZE YAHAN KAREIN
# ============================================================ #

BOT_NAME = "riya"
DM_LINK  = "https://t.me/hellupdates1"

# ============================================================ #
#                      ENVIRONMENT VARIABLES
# ============================================================ #

API_ID         = int(os.environ["API_ID"])
API_HASH       = os.environ["API_HASH"]
SESSION_STRING = os.environ["SESSION_STRING"]
OWNER_ID       = int(os.environ["OWNER_ID"])
LOG_GROUP_ID   = int(os.environ.get("LOG_GROUP_ID", "0"))
ROUTER_API     = os.environ.get("ROUTER_API")
MONGODB_URI    = os.environ.get("MONGODB_URI")

# ============================================================ #
#                      MONGODB SETUP
# ============================================================ #

chat_bot_groups = None

if MONGODB_URI:
    from motor.motor_asyncio import AsyncIOMotorClient
    _mongo = AsyncIOMotorClient(MONGODB_URI)
    chat_bot_groups = _mongo["AlishanBot"]["chat_bot_groups"]

# ============================================================ #
#                      OPENROUTER CLIENT
# ============================================================ #

ai = AsyncOpenAI(
    api_key=ROUTER_API,
    base_url="https://openrouter.ai/api/v1",
)

# ============================================================ #
#                      AI REPLY
# ============================================================ #

async def router_reply(user_text: str):
    try:
        resp = await ai.chat.completions.create(
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
                        "If someone flirts too hard, respond with light teasing or mild irritation. "
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
        return resp.choices[0].message.content
    except Exception as e:
        print(f"OpenRouter error: {e}")
        return None


async def simulate_typing(client, chat_id, text: str):
    typing_time = max(1.0, len(text) / 45)
    await client.send_chat_action(chat_id, "typing")
    await asyncio.sleep(typing_time)
    await asyncio.sleep(random.uniform(0.3, 0.8))

# ============================================================ #
#                      MAIN
# ============================================================ #

async def main():
    # FIX: Client yahan banao — same event loop mein
    app = Client(
        name="userbot",
        api_id=API_ID,
        api_hash=API_HASH,
        session_string=SESSION_STRING,
        sleep_threshold=60,
    )

    # ── Error / Log helpers ───────────────────────────────────

    async def send_error_log(command_name: str, error_text: str):
        if LOG_GROUP_ID == 0:
            print(f"ERROR [{command_name}]: {error_text[-300:]}")
            return
        try:
            short = "\n".join(error_text.splitlines()[-6:])
            await app.send_message(LOG_GROUP_ID, f"❌ ERROR\n📌 {command_name}\n\n`{short}`")
        except Exception as e:
            print(f"Log send failed: {e}")

    async def send_log(text: str):
        if LOG_GROUP_ID == 0:
            return
        try:
            await app.send_message(LOG_GROUP_ID, text)
        except Exception:
            pass

    # ── All commands list ─────────────────────────────────────

    ALL_CMDS = ["start", "help", "ping", "chatbot", "summon",
                "admins", "stoptag", "blacklist", "whitelist"]

    # ── DM Handler ───────────────────────────────────────────

    @app.on_message(
        filters.private
        & ~filters.command(ALL_CMDS, prefixes=["/", ".", "!"])
    )
    async def dm_handler(client, message: Message):
        if not message.text:
            return
        await client.send_chat_action(message.chat.id, "typing")
        await asyncio.sleep(random.uniform(1.0, 2.5))
        await message.reply(DM_LINK)

    # ── Group Chatbot Handler ─────────────────────────────────

    @app.on_message(
        filters.text
        & filters.group
        & ~filters.command(ALL_CMDS, prefixes=["/", ".", "!"])
    )
    async def group_chatbot(client, message: Message):
        chat_id = message.chat.id

        if chat_bot_groups is not None:
            data = await chat_bot_groups.find_one({"chat_id": chat_id, "enabled": True})
            if not data:
                return
        else:
            return

        me = await client.get_me()
        text = message.text.strip()

        is_reply_to_bot = (
            message.reply_to_message is not None
            and message.reply_to_message.from_user is not None
            and message.reply_to_message.from_user.id == me.id
        )
        is_mention = bool(
            me.username and re.search(rf"@{me.username}", text, re.IGNORECASE)
        )

        if not (is_reply_to_bot or is_mention):
            return

        clean_text = text
        if is_mention and me.username:
            clean_text = re.sub(rf"@{me.username}", "", text, flags=re.IGNORECASE).strip()

        if not clean_text:
            return

        reply = await router_reply(clean_text)
        if not reply:
            return

        await simulate_typing(client, chat_id, reply)
        await message.reply(reply)

    # ── Chatbot Toggle ────────────────────────────────────────

    @app.on_message(
        filters.command("chatbot", prefixes=["/", ".", "!"]) & filters.group
    )
    async def chatbot_toggle(client, message: Message):
        if chat_bot_groups is None:
            return await message.reply("❌ MongoDB not configured.")

        from tagbot import is_admin_or_owner
        if not await is_admin_or_owner(client, message.from_user.id, message.chat.id, OWNER_ID):
            return await message.reply("» You must be an admin to manage chatbot")

        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Enable",  callback_data=f"cb_on:{message.chat.id}"),
            InlineKeyboardButton("❌ Disable", callback_data=f"cb_off:{message.chat.id}"),
        ]])
        await message.reply(f"• {BOT_NAME} Chatbot — Choose:", reply_markup=kb)

    @app.on_callback_query(filters.regex(r"cb_on:(-?\d+)"))
    async def cb_enable(client, cb: CallbackQuery):
        chat_id = int(cb.matches[0].group(1))
        from tagbot import is_admin_or_owner
        if not await is_admin_or_owner(client, cb.from_user.id, chat_id, OWNER_ID):
            return await cb.answer("Only admins can do this", show_alert=True)
        await chat_bot_groups.update_one(
            {"chat_id": chat_id}, {"$set": {"enabled": True}}, upsert=True
        )
        await cb.message.edit_text(f"✅ {BOT_NAME} chatbot enabled by {cb.from_user.first_name}!")

    @app.on_callback_query(filters.regex(r"cb_off:(-?\d+)"))
    async def cb_disable(client, cb: CallbackQuery):
        chat_id = int(cb.matches[0].group(1))
        from tagbot import is_admin_or_owner
        if not await is_admin_or_owner(client, cb.from_user.id, chat_id, OWNER_ID):
            return await cb.answer("Only admins can do this", show_alert=True)
        await chat_bot_groups.update_one(
            {"chat_id": chat_id}, {"$set": {"enabled": False}}, upsert=True
        )
        await cb.message.edit_text(f"❌ {BOT_NAME} chatbot disabled by {cb.from_user.first_name}...")

    # ── Ping ──────────────────────────────────────────────────

    @app.on_message(filters.command("ping", prefixes=["/", ".", "!"]))
    async def ping_command(client, message: Message):
        await message.reply(f"✅ {BOT_NAME} Userbot Active")

    # ── Help ──────────────────────────────────────────────────

    @app.on_message(filters.command("help", prefixes=["/", ".", "!"]))
    async def help_command(client, message: Message):
        await message.reply(
            f"📚 **{BOT_NAME} Commands**\n\n"
            "**Chatbot:**\n"
            "🔹 `/chatbot` — Toggle chatbot on/off in group\n"
            "🔹 Reply or @mention to chat\n\n"
            "**TagBot:**\n"
            "🔹 `/summon <msg>` — Tag all members\n"
            "🔹 `/admins <msg>` — Tag all admins\n"
            "🔹 `/stoptag` — Stop running summon\n"
            "🔹 `/blacklist` — Block summon (owner)\n"
            "🔹 `/whitelist` — Allow summon (owner)\n\n"
            "**Other:**\n"
            "🔹 `/ping` — Check bot status\n"
            "🔹 `/help` — Show this help\n\n"
            f"⚡ DM me → link milega"
        )

    # ── TagBot Register ───────────────────────────────────────

    register_tagbot(app, OWNER_ID, send_error_log)

    # ── Start ─────────────────────────────────────────────────

    print(f"✅ {BOT_NAME} Userbot Starting...")
    await app.start()

    me = await app.get_me()
    print(f"🔐 Logged in as: {me.first_name} | @{me.username} | ID: {me.id}")
    print(f"📋 Registered handler groups: {len(app.dispatcher.groups)}")

    await send_log(f"✅ {BOT_NAME} Started!\n👤 @{me.username} | {me.id}")
    print(f"✅ Running. Waiting for messages...")

    await idle()
    await app.stop()
    print(f"⛔ {BOT_NAME} Stopped.")


if __name__ == "__main__":
    asyncio.run(main())
