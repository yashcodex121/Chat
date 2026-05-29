import os
import asyncio
import traceback

from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait
from pyrogram.enums import ChatMembersFilter

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


# ---------------- SAFE ERROR LOG ---------------- #

async def send_error_log(command_name, error_text):

    try:

        short_error = "\n".join(
            error_text.splitlines()[-6:]
        )

        await app.send_message(
            LOG_GROUP_ID,
            f"❌ ERROR DETECTED\n\n"
            f"📌 Command : {command_name}\n\n"
            f"🛠 Hint : Check Recent Changes / Permissions / Flood Limits\n\n"
            f"📄 Error:\n"
            f"`{short_error}`"
        )

    except Exception as e:
        print(e)


# ---------------- SIMPLE LOG ---------------- #

async def send_log(text):

    try:
        await app.send_message(
            LOG_GROUP_ID,
            text
        )

    except:
        pass


# ---------------- OWNER + ADMIN CHECK ---------------- #

def admin_or_owner(func):

    async def wrapper(client, message):

        try:

            if not message.from_user:
                return

            user_id = message.from_user.id
            chat_id = message.chat.id

            # owner access
            if user_id == OWNER_ID:
                return await func(client, message)

            admins = []

            async for member in app.get_chat_members(
                chat_id,
                filter=ChatMembersFilter.ADMINISTRATORS
            ):

                admins.append(member.user.id)

            # admin access
            if user_id in admins:
                return await func(client, message)

            return await message.reply_text(
                "❌ Only Owner Or Group Admin Can Use This Command"
            )

        except Exception as e:

            print(f"ADMIN CHECK ERROR : {e}")

            return await message.reply_text(
                "❌ Admin Check Failed"
            )

    return wrapper


# ---------------- OWNER ONLY ---------------- #

def owner_only(func):

    async def wrapper(client, message):

        try:

            if message.from_user.id != OWNER_ID:

                return await message.reply_text(
                    "❌ Only Bot Owner Can Use This"
                )

            return await func(client, message)

        except:
            return

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
        "🛑 Summoning Stopped"
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


# ---------------- SUMMON ---------------- #

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

        # cooldown check
        if chat_id in tag_cooldown:

            remaining = tag_cooldown[chat_id] - asyncio.get_event_loop().time()

            if remaining > 0:

                return await message.reply_text(
                    f"❌ Anti Spam Active\n\n"
                    f"⏳ Wait {int(remaining)} sec"
                )

        # cooldown
        tag_cooldown[chat_id] = asyncio.get_event_loop().time() + 60

        # check text
        if len(message.command) < 2:

            return await message.reply_text(
                "❌ Example:\n/summon hello everyone"
            )

        text = message.text.split(None, 1)[1]

        await send_log(
            f"📢 SUMMON STARTED\n"
            f"👤 {message.from_user.first_name}"
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

            # skip deleted users
            if user.is_deleted:
                continue

            # skip bots
            if user.is_bot:
                continue

            # duplicate protection
            if user.id in unique_users:
                continue

            unique_users.add(user.id)

            try:

                await app.send_message(
                    chat_id,
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

        active_tags[chat_id] = False

        await progress.edit_text(
            f"✅ Summoning Completed\n\n"
            f"👥 Total Tagged : {tagged}"
        )

    except Exception:

        active_tags[chat_id] = False

        error = traceback.format_exc()

        print(error)

        await send_error_log(
            "SUMMON",
            error
        )

        await message.reply_text(
            "❌ Error Aa Gaya"
        )


# ---------------- ADMINS ---------------- #

@app.on_message(filters.command("admins", prefixes=["/", ".", "!"]) & filters.group)
@admin_or_owner
async def admins(_, message: Message):

    try:

        chat_id = message.chat.id

        if len(message.command) < 2:

            return await message.reply_text(
                "❌ Example:\n/admins meeting now"
            )

        text = message.text.split(None, 1)[1]

        await send_log(
            f"👮 ADMINS COMMAND STARTED\n"
            f"👤 {message.from_user.first_name}"
        )

        active_tags[chat_id] = True

        tagged = 0

        unique_admins = set()

        async for member in app.get_chat_members(
            chat_id,
            filter=ChatMembersFilter.ADMINISTRATORS
        ):

            # stop check
            if not active_tags.get(chat_id):
                break

            user = member.user

            if user.is_bot:
                continue

            if user.id in unique_admins:
                continue

            unique_admins.add(user.id)

            try:

                await app.send_message(
                    chat_id,
                    f"[{user.first_name}](tg://user?id={user.id}) {text}"
                )

                tagged += 1

                await asyncio.sleep(3)

            except FloodWait as e:

                await asyncio.sleep(e.value)

            except Exception:
                continue

        active_tags[chat_id] = False

        await message.reply_text(
            f"✅ Admin Summon Completed\n\n"
            f"👮 Tagged : {tagged}"
        )

    except Exception:

        active_tags[message.chat.id] = False

        error = traceback.format_exc()

        print(error)

        await send_error_log(
            "ADMINS",
            error
        )

        await message.reply_text(
            "❌ Error Aa Gaya"
        )


# ---------------- HELP ---------------- #

@app.on_message(filters.command("help", prefixes=["/", ".", "!"]))
@admin_or_owner
async def help_command(_, message: Message):

    await message.reply_text(
        "📚 COMMANDS\n\n"
        "/summon message\n"
        "→ Summon All Members\n\n"
        "/admins message\n"
        "→ Summon All Admins\n\n"
        "/stoptag\n"
        "→ Stop Running Summon\n\n"
        "/blacklist\n"
        "→ Disable Summon In Group\n\n"
        "/whitelist\n"
        "→ Enable Summon In Group\n\n"
        "/ping\n"
        "→ Check Userbot"
    )


# ---------------- START ---------------- #

print("✅ Userbot Started Successfully")

try:

    app.run()

except Exception as e:

    print(e)
