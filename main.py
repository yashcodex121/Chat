import os
import asyncio
import traceback

from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait

# ---------------- CONFIG ---------------- #

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")

SESSION_STRING = os.getenv("SESSION_STRING")

OWNER_ID = int(os.getenv("OWNER_ID"))

LOG_GROUP_ID = int(os.getenv("LOG_GROUP_ID"))

# ---------------------------------------- #

app = Client(
    "Userbot",
    api_id=API_ID,
    api_hash=API_HASH,
    session_string=SESSION_STRING
)

# ---------------- STORAGE ---------------- #

tag_cooldown = {}

active_tags = {}

blacklist_groups = set()

# ----------------------------------------- #


# ---------------- LOG FUNCTION ---------------- #

async def send_log(text):
    try:
        await app.send_message(LOG_GROUP_ID, text)
    except Exception as e:
        print(f"LOG ERROR : {e}")


# ---------------- OWNER + ADMIN CHECK ---------------- #

def admin_or_owner(func):

    async def wrapper(client, message):

        try:

            user_id = message.from_user.id
            chat_id = message.chat.id

            # owner allowed
            if user_id == OWNER_ID:
                return await func(client, message)

            # admin check
            member = await app.get_chat_member(
                chat_id,
                user_id
            )

            if member.status in [
                "administrator",
                "owner"
            ]:

                return await func(client, message)

            return await message.reply_text(
                "❌ Only Owner Or Group Admin Can Use This Command"
            )

        except Exception as e:

            print(e)

    return wrapper


# ---------------- OWNER ONLY ---------------- #

def owner_only(func):

    async def wrapper(client, message):

        if message.from_user.id != OWNER_ID:

            return await message.reply_text(
                "❌ Only Bot Owner Can Use This"
            )

        return await func(client, message)

    return wrapper


# ---------------- PING ---------------- #

@app.on_message(filters.command("ping", prefixes=["/", ".", "!"]))
@admin_or_owner
async def ping(_, message: Message):

    await message.reply_text(
        "✅ Userbot Active"
    )


# ---------------- STOP TAG ---------------- #

@app.on_message(filters.command("stoptag", prefixes=["/", ".", "!"]) & filters.group)
@admin_or_owner
async def stop_tag(_, message: Message):

    chat_id = message.chat.id

    active_tags[chat_id] = False

    await message.reply_text(
        "🛑 Tagging Stopped"
    )


# ---------------- BLACKLIST ---------------- #

@app.on_message(filters.command("blacklist", prefixes=["/", ".", "!"]) & filters.group)
@owner_only
async def blacklist(_, message: Message):

    blacklist_groups.add(message.chat.id)

    await message.reply_text(
        "🚫 Group Blacklisted"
    )


# ---------------- WHITELIST ---------------- #

@app.on_message(filters.command("whitelist", prefixes=["/", ".", "!"]) & filters.group)
@owner_only
async def whitelist(_, message: Message):

    blacklist_groups.discard(message.chat.id)

    await message.reply_text(
        "✅ Group Whitelisted"
    )


# ---------------- SUMMON TAG ---------------- #

@app.on_message(filters.command("summon", prefixes=["/", ".", "!"]) & filters.group)
@admin_or_owner
async def summon(_, message: Message):

    try:

        chat_id = message.chat.id

        # blacklist check
        if chat_id in blacklist_groups:

            return await message.reply_text(
                "🚫 This Group Is Blacklisted"
            )

        # cooldown
        if chat_id in tag_cooldown:

            remaining = tag_cooldown[chat_id] - asyncio.get_event_loop().time()

            if remaining > 0:

                return await message.reply_text(
                    f"❌ Anti Spam Active\n\n"
                    f"⏳ Wait {int(remaining)} sec"
                )

        # cooldown time
        tag_cooldown[chat_id] = asyncio.get_event_loop().time() + 60

        # command message
        if len(message.command) < 2:

            return await message.reply_text(
                "❌ Example:\n/summon hello everyone"
            )

        text = message.text.split(None, 1)[1]

        await send_log(
            f"📢 SUMMON USED\n\n"
            f"👤 User : {message.from_user.mention}\n"
            f"🆔 ID : `{message.from_user.id}`\n"
            f"💬 Chat : {message.chat.title}\n"
            f"📝 Message : {text}"
        )

        active_tags[chat_id] = True

        tagged = 0

        progress = await message.reply_text(
            "🚀 Summoning Started..."
        )

        unique_users = set()

        async for member in app.get_chat_members(chat_id):

            # stop check
            if not active_tags.get(chat_id):

                return await progress.edit_text(
                    "🛑 Summoning Cancelled"
                )

            user = member.user

            if user.is_bot:
                continue

            if user.id in unique_users:
                continue

            unique_users.add(user.id)

            try:

                await message.reply_text(
                    f"[{user.first_name}](tg://user?id={user.id}) {text}"
                )

                tagged += 1

                # progress update
                if tagged % 10 == 0:

                    try:
                        await progress.edit_text(
                            f"🚀 Summoning Running...\n\n"
                            f"✅ Tagged : {tagged}"
                        )
                    except:
                        pass

                # anti flood
                await asyncio.sleep(3)

            except FloodWait as e:

                await asyncio.sleep(e.value)

            except Exception:
                continue

        await progress.edit_text(
            f"✅ Summoning Completed\n\n"
            f"👥 Total Tagged : {tagged}"
        )

        active_tags[chat_id] = False

    except Exception:

        error = traceback.format_exc()

        await send_log(
            f"❌ SUMMON ERROR\n\n"
            f"{error}"
        )

        await message.reply_text(
            "❌ Error aa gaya."
        )


# ---------------- ADMINS TAG ---------------- #

@app.on_message(filters.command("admins", prefixes=["/", ".", "!"]) & filters.group)
@admin_or_owner
async def admins(_, message: Message):

    try:

        if len(message.command) < 2:

            return await message.reply_text(
                "❌ Example:\n/admins meeting now"
            )

        text = message.text.split(None, 1)[1]

        await send_log(
            f"👮 ADMINS TAG USED\n\n"
            f"👤 User : {message.from_user.mention}\n"
            f"🆔 ID : `{message.from_user.id}`\n"
            f"💬 Chat : {message.chat.title}\n"
            f"📝 Message : {text}"
        )

        unique_admins = set()

        active_tags[message.chat.id] = True

        tagged = 0

        async for admin in app.get_chat_members(
            message.chat.id,
            filter="administrators"
        ):

            if not active_tags.get(message.chat.id):
                break

            user = admin.user

            if user.is_bot:
                continue

            if user.id in unique_admins:
                continue

            unique_admins.add(user.id)

            try:

                await message.reply_text(
                    f"[{user.first_name}](tg://user?id={user.id}) {text}"
                )

                tagged += 1

                await asyncio.sleep(3)

            except FloodWait as e:

                await asyncio.sleep(e.value)

            except Exception:
                continue

        await message.reply_text(
            f"✅ Admin Tag Completed\n\n"
            f"👮 Tagged : {tagged}"
        )

        active_tags[message.chat.id] = False

    except Exception:

        error = traceback.format_exc()

        await send_log(
            f"❌ ADMINS ERROR\n\n"
            f"{error}"
        )

        await message.reply_text(
            "❌ Error aa gaya."
        )


# ---------------- HELP ---------------- #

@app.on_message(filters.command("help", prefixes=["/", ".", "!"]))
@admin_or_owner
async def help_command(_, message: Message):

    await message.reply_text(
        "📚 COMMANDS\n\n"
        "/summon message\n"
        "→ Tag All Members One By One\n\n"
        "/admins message\n"
        "→ Tag Admins One By One\n\n"
        "/stoptag\n"
        "→ Stop Running Tag\n\n"
        "/blacklist\n"
        "→ Disable Tag In Group (Owner Only)\n\n"
        "/whitelist\n"
        "→ Enable Tag In Group (Owner Only)\n\n"
        "/ping\n"
        "→ Check Userbot"
    )


# ---------------- START ---------------- #

print("✅ Userbot Started Successfully")

try:

    app.run()

except Exception as e:

    print(e)
