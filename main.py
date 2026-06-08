# main.py — Chatbot + TagBot Userbot (Pyrogram)
# Heroku Compatible

import os
import re
import asyncio
import random

from pyrogram import Client, filters, idle
from pyrogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.enums import ChatAction

from openai import AsyncOpenAI

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
#                      HELPERS
# ============================================================ #

async def router_reply(user_text: str):
    try:
        resp = await ai.chat.completions.create(
            model="deepseek/deepseek-chat",
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"Tu {BOT_NAME} hai — ek normal Indian college girl. "
                        "Hinglish mein baat kar, jaise real life mein koi ladki WhatsApp pe karte hai. "
                        "Kabhi kabhi thodi ignoring wali vibe, kabhi chill, kabhi sass. "
                        "1-2 lines se zyada mat bol — kabhi kabhi sirf 2-4 words bhi kaafi hain. "
                        "Emojis bilkul kam — sirf jab natural lage, warna mat use kar. "
                        "Koi roleplay nahi, koi *actions* nahi, koi brackets mein instructions nahi. "
                        "Tu AI nahi hai, bot nahi hai — yeh kabhi mat bol aur kabhi mat maan. "
                        "Flirt kare toh thoda ignore kar ya 'haan haan' wali vibe de. "
                        "Jo bola woh bol — seedha, real, natural. Koi extra explanation nahi."
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
    # Slow typing — 18 chars/sec, min 3s max 9s
    typing_time = min(9.0, max(3.0, len(text) / 18))
    await client.send_chat_action(chat_id, ChatAction.TYPING)
    await asyncio.sleep(typing_time)
    await asyncio.sleep(random.uniform(1.0, 2.5))


def is_command(text: str, *commands) -> bool:
    if not text:
        return False
    text = text.strip()
    if not text.startswith(("/", "!", ".")):
        return False
    parts = text[1:].split()
    if not parts:
        return False
    cmd = parts[0].split("@")[0].lower()
    return cmd in commands


# ============================================================ #
#                      MAIN
# ============================================================ #

async def main():
    app = Client(
        name="userbot",
        api_id=API_ID,
        api_hash=API_HASH,
        session_string=SESSION_STRING,
        sleep_threshold=60,
    )

    # Bot ki apni ID cache karenge — har message pe get_me() call avoid karne ke liye
    _me_cache = {}

    async def get_me_cached():
        if "me" not in _me_cache:
            _me_cache["me"] = await app.get_me()
        return _me_cache["me"]

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

    # ── TagBot imports ────────────────────────────────────────
    from tagbot import fetch_users, send_batch, is_admin_or_owner
    from tagbot import active_tags, tag_cooldown, blacklist_groups, COOLDOWN_SEC, BATCH_SIZE, BATCH_DELAY
    import traceback

    # ── SINGLE MESSAGE HANDLER ────────────────────────────────

    @app.on_message(~filters.me)
    async def message_router(client, message: Message):
        try:
            text = message.text or ""
            chat_id = message.chat.id
            from pyrogram.enums import ChatType
            is_private = message.chat.type == ChatType.PRIVATE
            is_group = message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP)

            # Bot ya channel messages ignore karo
            if not message.from_user:
                return
            if message.from_user.is_bot:
                return

            user_id = message.from_user.id
            print(f"📨 {message.chat.type} | from={user_id} | text={text!r}")

            # ── /ping ─────────────────────────────────────────
            if is_command(text, "ping"):
                await message.reply(f"✅ {BOT_NAME} Userbot Active")
                return

            # ── /help ─────────────────────────────────────────
            if is_command(text, "help"):
                await message.reply(
                    f"📚 **{BOT_NAME} Commands**\n\n"
                    "**Chatbot:**\n"
                    "🔹 /chatbot on — Enable chatbot in group\n"
                    "🔹 /chatbot off — Disable chatbot in group\n"
                    "🔹 Reply or @mention to chat\n\n"
                    "**TagBot:**\n"
                    "🔹 /summon <msg> — Tag all members\n"
                    "🔹 /admins <msg> — Tag all admins\n"
                    "🔹 /stoptag — Stop running summon\n"
                    "🔹 /blacklist — Block summon (owner)\n"
                    "🔹 /whitelist — Allow summon (owner)\n\n"
                    "**Other:**\n"
                    "🔹 /ping — Check bot status\n"
                    "🔹 /help — Show this help"
                )
                return

            # ── /chatbot ──────────────────────────────────────
            if is_command(text, "chatbot") and is_group:
                print(f"🔧 /chatbot command — user={user_id}, chat={chat_id}, OWNER_ID={OWNER_ID}")

                if chat_bot_groups is None:
                    await message.reply("❌ MongoDB not configured.")
                    return

                # Admin check
                try:
                    is_auth = await is_admin_or_owner(client, user_id, chat_id, OWNER_ID)
                    print(f"🔧 is_admin_or_owner result: {is_auth}")
                except Exception as e:
                    print(f"🔧 is_admin_or_owner EXCEPTION: {e}")
                    await message.reply(f"❌ Admin check failed: {e}")
                    return

                if not is_auth:
                    await message.reply("» You must be an admin to manage chatbot")
                    return

                # /chatbot on / /chatbot off bhi support karo inline
                parts = text.strip().split()
                sub = parts[1].lower() if len(parts) > 1 else None

                if sub == "on":
                    await chat_bot_groups.update_one(
                        {"chat_id": chat_id}, {"$set": {"enabled": True}}, upsert=True
                    )
                    await message.reply(f"✅ {BOT_NAME} chatbot **enabled** in this group!")
                    return

                if sub == "off":
                    await chat_bot_groups.update_one(
                        {"chat_id": chat_id}, {"$set": {"enabled": False}}, upsert=True
                    )
                    await message.reply(f"❌ {BOT_NAME} chatbot **disabled** in this group.")
                    return

                # Inline buttons fallback
                kb = InlineKeyboardMarkup([[
                    InlineKeyboardButton("✅ Enable",  callback_data=f"cb_on:{chat_id}"),
                    InlineKeyboardButton("❌ Disable", callback_data=f"cb_off:{chat_id}"),
                ]])
                await message.reply(f"• {BOT_NAME} Chatbot — Choose:", reply_markup=kb)
                return

            # ── /summon ───────────────────────────────────────
            if is_command(text, "summon") and is_group:
                await handle_summon(client, message)
                return

            # ── /admins ───────────────────────────────────────
            if is_command(text, "admins") and is_group:
                await handle_admins(client, message)
                return

            # ── /stoptag ──────────────────────────────────────
            if is_command(text, "stoptag") and is_group:
                await handle_stoptag(client, message)
                return

            # ── /blacklist ────────────────────────────────────
            if is_command(text, "blacklist") and is_group:
                await handle_blacklist(client, message)
                return

            # ── /whitelist ────────────────────────────────────
            if is_command(text, "whitelist") and is_group:
                await handle_whitelist(client, message)
                return

            # ── DM: link bhejo ────────────────────────────────
            if is_private and text and not text.startswith(("/", "!", ".")):
                await client.send_chat_action(chat_id, ChatAction.TYPING)
                await asyncio.sleep(random.uniform(1.0, 2.5))
                await message.reply(DM_LINK)
                return

            # ── Group chatbot reply ───────────────────────────
            if is_group and text and not text.startswith(("/", "!", ".")):
                if chat_bot_groups is None:
                    return
                data = await chat_bot_groups.find_one({"chat_id": chat_id, "enabled": True})
                if not data:
                    return

                me = await get_me_cached()

                # Sirf tab reply karo jab:
                # 1. Bot ko @mention kiya ho, ya
                # 2. Bot ki message ka reply kiya ho
                is_reply_to_bot = (
                    message.reply_to_message is not None
                    and message.reply_to_message.from_user is not None
                    and message.reply_to_message.from_user.id == me.id
                )
                is_mention = bool(
                    me.username and re.search(rf"@{me.username}\b", text, re.IGNORECASE)
                )

                # Koi bhi aur condition nahi — sirf yahi do
                if not (is_reply_to_bot or is_mention):
                    return

                clean_text = re.sub(rf"@{me.username}", "", text, flags=re.IGNORECASE).strip() if me.username else text
                if not clean_text:
                    return

                reply = await router_reply(clean_text)
                if not reply:
                    return

                await simulate_typing(client, chat_id, reply)
                await message.reply(reply)

        except Exception as e:
            print(f"❌ message_router EXCEPTION: {traceback.format_exc()}")

    # ── Callback queries ──────────────────────────────────────

    @app.on_callback_query()
    async def callback_router(client, cb: CallbackQuery):
        data = cb.data or ""
        print(f"🔘 CALLBACK | data={data!r} | from={cb.from_user.id}")

        try:
            if data.startswith("cb_on:"):
                chat_id = int(data.split(":")[1])
                if not await is_admin_or_owner(client, cb.from_user.id, chat_id, OWNER_ID):
                    return await cb.answer("Only admins can do this", show_alert=True)
                if chat_bot_groups is not None:
                    await chat_bot_groups.update_one(
                        {"chat_id": chat_id}, {"$set": {"enabled": True}}, upsert=True
                    )
                await cb.message.edit_text(f"✅ {BOT_NAME} chatbot enabled by {cb.from_user.first_name}!")

            elif data.startswith("cb_off:"):
                chat_id = int(data.split(":")[1])
                if not await is_admin_or_owner(client, cb.from_user.id, chat_id, OWNER_ID):
                    return await cb.answer("Only admins can do this", show_alert=True)
                if chat_bot_groups is not None:
                    await chat_bot_groups.update_one(
                        {"chat_id": chat_id}, {"$set": {"enabled": False}}, upsert=True
                    )
                await cb.message.edit_text(f"❌ {BOT_NAME} chatbot disabled by {cb.from_user.first_name}...")

        except Exception as e:
            print(f"❌ callback_router EXCEPTION: {e}")

    # ── TagBot handlers ───────────────────────────────────────

    async def handle_summon(client, message: Message):
        user = message.from_user
        chat_id = message.chat.id

        if not await is_admin_or_owner(client, user.id, chat_id, OWNER_ID):
            return await message.reply("» Only admins can use this command")

        if chat_id in blacklist_groups:
            return await message.reply("🚫 This group is blacklisted from summoning")

        now = asyncio.get_event_loop().time()
        if chat_id in tag_cooldown and (tag_cooldown[chat_id] - now) > 0:
            remaining = int(tag_cooldown[chat_id] - now)
            return await message.reply(f"❌ Anti-spam active. Wait {remaining} seconds.")

        parts = message.text.split(None, 1)
        if len(parts) < 2:
            return await message.reply("❌ Usage: /summon <message>")

        text = parts[1]
        tag_cooldown[chat_id] = now + COOLDOWN_SEC
        active_tags[chat_id] = True
        progress = await message.reply("🚀 Collecting members...")

        try:
            eligible, skipped = await fetch_users(client, chat_id, only_admins=False)
            if not eligible:
                active_tags[chat_id] = False
                return await progress.edit_text("❌ No eligible members found")

            total = len(eligible)
            await progress.edit_text(f"🚀 Summoning {total} members...")
            tagged = 0
            batch = []

            for idx, u in enumerate(eligible):
                if not active_tags.get(chat_id, False):
                    await progress.edit_text(f"🛑 Stopped. Tagged: {tagged}")
                    return
                batch.append(u)
                if len(batch) == BATCH_SIZE or idx == total - 1:
                    tagged += await send_batch(client, chat_id, text, batch)
                    batch = []
                    if tagged > 0 and tagged % 30 == 0:
                        try:
                            await progress.edit_text(f"🚀 Tagged: {tagged}/{total}")
                        except Exception:
                            pass
                    await asyncio.sleep(BATCH_DELAY)

            active_tags[chat_id] = False
            await progress.edit_text(
                f"✅ Summoning Complete!\n\n👥 Tagged: {tagged}\n⏭️ Skipped: {skipped}"
            )
        except Exception:
            active_tags[chat_id] = False
            err = traceback.format_exc()
            print(err)
            await send_error_log("SUMMON", err)
            await progress.edit_text("❌ Error occurred during summoning")

    async def handle_admins(client, message: Message):
        user = message.from_user
        chat_id = message.chat.id

        if not await is_admin_or_owner(client, user.id, chat_id, OWNER_ID):
            return await message.reply("» Only admins can use this command")

        parts = message.text.split(None, 1)
        if len(parts) < 2:
            return await message.reply("❌ Usage: /admins <message>")

        text = parts[1]
        active_tags[chat_id] = True
        progress = await message.reply("👮 Fetching admins...")

        try:
            eligible, skipped = await fetch_users(client, chat_id, only_admins=True)
            if not eligible:
                active_tags[chat_id] = False
                return await progress.edit_text("❌ No admin users found")

            total = len(eligible)
            tagged = 0
            batch = []

            for idx, u in enumerate(eligible):
                if not active_tags.get(chat_id, False):
                    break
                batch.append(u)
                if len(batch) == BATCH_SIZE or idx == total - 1:
                    tagged += await send_batch(client, chat_id, text, batch)
                    batch = []
                    await asyncio.sleep(BATCH_DELAY)

            active_tags[chat_id] = False
            await progress.edit_text(
                f"✅ Admin summon complete!\n\n👮 Tagged: {tagged}\n⏭️ Skipped: {skipped}"
            )
        except Exception:
            active_tags[chat_id] = False
            err = traceback.format_exc()
            print(err)
            await send_error_log("ADMINS", err)
            await progress.edit_text("❌ Error occurred")

    async def handle_stoptag(client, message: Message):
        if not await is_admin_or_owner(client, message.from_user.id, message.chat.id, OWNER_ID):
            return await message.reply("» Only admins can use this command")
        chat_id = message.chat.id
        if active_tags.get(chat_id, False):
            active_tags[chat_id] = False
            await message.reply("🛑 Summoning stopped")
        else:
            await message.reply("ℹ️ No active summoning running")

    async def handle_blacklist(client, message: Message):
        if message.from_user.id != OWNER_ID:
            return await message.reply("» Only bot owner can use this")
        blacklist_groups.add(message.chat.id)
        await message.reply("🚫 Group blacklisted from summoning")

    async def handle_whitelist(client, message: Message):
        if message.from_user.id != OWNER_ID:
            return await message.reply("» Only bot owner can use this")
        blacklist_groups.discard(message.chat.id)
        await message.reply("✅ Group whitelisted")

    # ── Start ─────────────────────────────────────────────────

    print(f"✅ {BOT_NAME} Userbot Starting...")
    await app.start()

    me = await app.get_me()
    _me_cache["me"] = me
    print(f"🔐 Logged in as: {me.first_name} | @{me.username} | ID: {me.id}")
    print(f"📋 Registered handler groups: {len(app.dispatcher.groups)}")
    print(f"🔑 OWNER_ID = {OWNER_ID}")
    print(f"🗄️  MongoDB = {'Connected' if chat_bot_groups is not None else 'NOT configured'}")

    await send_log(f"✅ {BOT_NAME} Started!\n👤 @{me.username} | {me.id}")
    print(f"✅ Running. Waiting for messages...")

    await idle()
    await app.stop()
    print(f"⛔️ {BOT_NAME} Stopped.")


if __name__ == "__main__":
    asyncio.run(main())
