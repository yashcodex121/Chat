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

# How many users to tag per single message (3 as requested)
BATCH_SIZE = 3

# Delay between batch sends (seconds)
BATCH_DELAY = 5

# Anti-flood sleep on FloodWait multiplier
FLOOD_BACKOFF = 1.5

# Max concurrent tagging tasks for very large groups
MAX_CONCURRENT_BATCHES = 2

# ---------------------------------------- #

app = Client(
    "Userbot",
    api_id=API_ID,
    api_hash=API_HASH,
    session_string=SESSION_STRING,
    sleep_threshold=60  # auto-handle smaller FloodWaits
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


# ---------------- BATCH TAG HELPER ---------------- #

async def send_batch_tag(chat_id, text, users_batch):

    """
    Sends a single message tagging up to BATCH_SIZE users.
    Returns the number of users actually included.
    """
    if not users_batch:
        return 0

    # Build mention string for all users in this batch
    mentions = []
    for user in users_batch:
        mention = f"[{user.first_name}](tg://user?id={user.id})"
        mentions.append(mention)

    # Join all mentions with the custom text
    batch_message = " ".join(mentions) + f" {text}"

    try:
        await app.send_message(chat_id, batch_message)
        return len(users_batch)

    except FloodWait as e:
        # Wait the required time + backoff
        wait_time = e.value * FLOOD_BACKOFF
        await asyncio.sleep(wait_time)
        # Retry once after flood wait
        try:
            await app.send_message(chat_id, batch_message)
            return len(users_batch)
        except:
            return 0

    except Exception:
        return 0


# ---------------- SUMMON (BATCH MODE) ---------------- #

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

        # cooldown - 120 sec for big groups to avoid ban
        tag_cooldown[chat_id] = asyncio.get_event_loop().time() + 120

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
        skipped = 0

        progress = await message.reply_text(
            "🚀 Summoning Started..."
        )

        # Collect all eligible users first (faster than iterating with sends)
        eligible_users = []
        unique_users = set()

        async for member in app.get_chat_members(chat_id):

            # stop check during collection too
            if not active_tags.get(chat_id):
                await progress.edit_text("🛑 Summoning Cancelled During Collection")
                return

            user = member.user

            # skip deleted / bots / duplicates
            if user.is_deleted or user.is_bot:
                skipped += 1
                continue

            if user.id in unique_users:
                skipped += 1
                continue

            unique_users.add(user.id)
            eligible_users.append(user)

        # Now batch tag
        batch = []

        for idx, user in enumerate(eligible_users):

            # stop check
            if not active_tags.get(chat_id):
                await progress.edit_text(
                    f"🛑 Summoning Cancelled\n\n"
                    f"✅ Tagged Before Stop : {tagged}"
                )
                return

            batch.append(user)

            # When batch is full OR it's the last user, send
            if len(batch) == BATCH_SIZE or (idx == len(eligible_users) - 1 and batch):

                sent_count = await send_batch_tag(chat_id, text, batch)
                tagged += sent_count

                batch = []  # reset batch

                # progress update every 3 batches
                if tagged % (BATCH_SIZE * 3) == 0:
                    try:
                        await progress.edit_text(
                            f"🚀 Summoning Running...\n\n"
                            f"✅ Tagged : {tagged}"
                        )
                    except:
                        pass

                # Delay between batches
                await asyncio.sleep(BATCH_DELAY)

        active_tags[chat_id] = False

        await progress.edit_text(
            f"✅ Summoning Completed\n\n"
            f"👥 Total Tagged : {tagged}\n"
            f"⏭ Skipped (bot/del/dup) : {skipped}"
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


# ---------------- ADMINS (BATCH MODE) ---------------- #

@app.on_message(filters.command("admins", prefixes=["/", ".", "!"]) & filters.group)
@admin_or_owner
async def admins_handler(_, message: Message):

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
        skipped = 0

        # Collect all admin users
        admin_users = []
        unique_admins = set()

        async for member in app.get_chat_members(
            chat_id,
            filter=ChatMembersFilter.ADMINISTRATORS
        ):

            if not active_tags.get(chat_id):
                break

            user = member.user

            if user.is_bot:
                skipped += 1
                continue

            if user.id in unique_admins:
                skipped += 1
                continue

            unique_admins.add(user.id)
            admin_users.append(user)

        # Batch tag admins
        batch = []

        for idx, user in enumerate(admin_users):

            if not active_tags.get(chat_id):
                break

            batch.append(user)

            if len(batch) == BATCH_SIZE or (idx == len(admin_users) - 1 and batch):

                sent_count = await send_batch_tag(chat_id, text, batch)
                tagged += sent_count
                batch = []

                await asyncio.sleep(BATCH_DELAY)

        active_tags[chat_id] = False

        await message.reply_text(
            f"✅ Admin Summon Completed\n\n"
            f"👮 Tagged : {tagged}\n"
            f"⏭ Skipped (bots/dup) : {skipped}"
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
        "→ Summon All Members (3 per msg)\n\n"
        "/admins message\n"
        "→ Summon All Admins (3 per msg)\n\n"
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

print("✅ Userbot Started Successfully (Batch Mode = 3)")

try:

    app.run()

except Exception as e:

    print(e)
