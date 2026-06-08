import os
import asyncio
import traceback

from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait, ChatAdminRequired, PeerIdInvalid
from pyrogram.enums import ChatMembersFilter, ChatType
from pyrogram.enums.parse_mode import ParseMode

# ---------------- CONFIG ---------------- #

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")

SESSION_STRING = os.getenv("SESSION_STRING")

OWNER_ID = int(os.getenv("OWNER_ID"))

LOG_GROUP_ID = int(os.getenv("LOG_GROUP_ID"))

# Batch config
BATCH_SIZE = 3
BATCH_DELAY = 6  # seconds between batches
MAX_MEMBERS_TO_FETCH = 5000  # limit to avoid timeout on huge groups

# ---------------------------------------- #

app = Client(
    "Userbot",
    api_id=API_ID,
    api_hash=API_HASH,
    session_string=SESSION_STRING,
    sleep_threshold=60,
    parse_mode=ParseMode.DEFAULT  # important for tg:// mentions
)

# ---------------- STORAGE ---------------- #

tag_cooldown = {}
active_tags = {}
blacklist_groups = set()

# ----------------------------------------- #


# ---------------- SAFE ERROR LOG ---------------- #

async def send_error_log(command_name, error_text):
    try:
        short_error = "\n".join(error_text.splitlines()[-6:])
        await app.send_message(
            LOG_GROUP_ID,
            f"❌ ERROR\n📌 {command_name}\n\n`{short_error}`"
        )
    except Exception as e:
        print(e)


async def send_log(text):
    try:
        await app.send_message(LOG_GROUP_ID, text)
    except:
        pass


# ---------------- ADMIN CHECK (FIXED) ---------------- #

async def is_admin_or_owner(chat_id, user_id):
    """Returns True if user is owner or admin. Handles permission errors."""
    if user_id == OWNER_ID:
        return True

    try:
        async for member in app.get_chat_members(
            chat_id,
            filter=ChatMembersFilter.ADMINISTRATORS
        ):
            if member.user.id == user_id:
                return True
    except (ChatAdminRequired, PeerIdInvalid, Exception):
        # Can't fetch admins? Only owner can use commands then.
        pass

    return False


def admin_or_owner(func):
    async def wrapper(client, message):
        try:
            if not message.from_user:
                return

            user_id = message.from_user.id
            chat_id = message.chat.id

            if user_id == OWNER_ID:
                return await func(client, message)

            if await is_admin_or_owner(chat_id, user_id):
                return await func(client, message)

            await message.reply_text("❌ Only Owner Or Group Admin Can Use This Command")

        except Exception as e:
            print(f"ADMIN CHECK ERROR: {e}")

    return wrapper


def owner_only(func):
    async def wrapper(client, message):
        try:
            if message.from_user.id != OWNER_ID:
                await message.reply_text("❌ Only Bot Owner Can Use This")
                return
            return await func(client, message)
        except:
            pass
    return wrapper


# ---------------- BATCH TAG HELPER (FIXED) ---------------- #

async def send_batch_tag(chat_id, text, users_batch):
    """Sends a single message with up to BATCH_SIZE mentions."""
    if not users_batch:
        return 0

    mentions = " ".join(
        f"<a href=\"tg://user?id={u.id}\">{u.first_name}</a>" for u in users_batch
    )

    message_text = f"{mentions} {text}"

    try:
        await app.send_message(chat_id, message_text, parse_mode=ParseMode.HTML)
        return len(users_batch)
    except FloodWait as e:
        wait = e.value * 1.5
        await asyncio.sleep(wait)
        try:
            await app.send_message(chat_id, message_text, parse_mode=ParseMode.HTML)
            return len(users_batch)
        except:
            return 0
    except Exception:
        return 0


# ---------------- FETCH MEMBERS (FIXED FOR LARGE GROUPS) ---------------- #

async def fetch_eligible_users(chat_id, only_admins=False):
    """
    Fetch eligible users with limit handling.
    Returns (eligible_users_list, skipped_count).
    """
    eligible_users = []
    unique_users = set()
    skipped = 0
    count = 0

    filter_type = ChatMembersFilter.ADMINISTRATORS if only_admins else ChatMembersFilter.SEARCH

    try:
        async for member in app.get_chat_members(chat_id, filter=filter_type):
            # safety limit for huge groups
            count += 1
            if count > MAX_MEMBERS_TO_FETCH:
                break

            # stop check
            if not active_tags.get(chat_id):
                break

            user = member.user

            if user.is_deleted or user.is_bot:
                skipped += 1
                continue

            if user.id in unique_users:
                skipped += 1
                continue

            unique_users.add(user.id)
            eligible_users.append(user)

    except Exception as e:
        print(f"FETCH ERROR: {e}")
        raise

    return eligible_users, skipped


# ---------------- PING ---------------- #

@app.on_message(filters.command("ping", prefixes=["/", ".", "!"]))
async def ping(_, message: Message):
    # Everyone can ping to check if bot is alive
    await message.reply_text("✅ Userbot Active")


# ---------------- STOP TAG ---------------- #

@app.on_message(filters.command("stoptag", prefixes=["/", ".", "!"]) & filters.group)
@admin_or_owner
async def stop_tag(_, message: Message):
    chat_id = message.chat.id
    active_tags[chat_id] = False
    await message.reply_text("🛑 Summoning Stopped")


# ---------------- BLACKLIST / WHITELIST ---------------- #

@app.on_message(filters.command("blacklist", prefixes=["/", ".", "!"]) & filters.group)
@owner_only
async def blacklist(_, message: Message):
    blacklist_groups.add(message.chat.id)
    await message.reply_text("🚫 Group Blacklisted")


@app.on_message(filters.command("whitelist", prefixes=["/", ".", "!"]) & filters.group)
@owner_only
async def whitelist(_, message: Message):
    blacklist_groups.discard(message.chat.id)
    await message.reply_text("✅ Group Whitelisted")


# ---------------- SUMMON (FIXED + BATCH) ---------------- #

@app.on_message(filters.command("summon", prefixes=["/", ".", "!"]) & filters.group)
@admin_or_owner
async def summon(_, message: Message):
    chat_id = message.chat.id

    # blacklist check
    if chat_id in blacklist_groups:
        return await message.reply_text("🚫 This Group Is Blacklisted")

    # cooldown check
    if chat_id in tag_cooldown:
        remaining = tag_cooldown[chat_id] - asyncio.get_event_loop().time()
        if remaining > 0:
            return await message.reply_text(f"❌ Wait {int(remaining)} sec")

    # check text
    if len(message.command) < 2:
        return await message.reply_text("❌ Example:\n/summon hello everyone")

    text = message.text.split(None, 1)[1]

    # Set cooldown FIRST so it doesn't get spammed
    tag_cooldown[chat_id] = asyncio.get_event_loop().time() + 180

    active_tags[chat_id] = True

    progress = await message.reply_text("🚀 Collecting Members...")

    try:
        # Fetch all users first
        eligible_users, skipped = await fetch_eligible_users(chat_id, only_admins=False)

        if not eligible_users:
            active_tags[chat_id] = False
            return await progress.edit_text("❌ No Eligible Members Found")

        await send_log(f"📢 SUMMON STARTED\n👤 {message.from_user.first_name}\n👥 Total: {len(eligible_users)}")

        await progress.edit_text(f"🚀 Summoning {len(eligible_users)} Members...")

        tagged = 0
        batch = []

        for idx, user in enumerate(eligible_users):
            if not active_tags.get(chat_id):
                await progress.edit_text(f"🛑 Stopped. Tagged: {tagged}")
                return

            batch.append(user)

            if len(batch) == BATCH_SIZE or idx == len(eligible_users) - 1:
                sent = await send_batch_tag(chat_id, text, batch)
                tagged += sent
                batch = []

                if tagged % 30 == 0:
                    try:
                        await progress.edit_text(f"🚀 Tagged: {tagged}/{len(eligible_users)}")
                    except:
                        pass

                await asyncio.sleep(BATCH_DELAY)

        active_tags[chat_id] = False

        await progress.edit_text(
            f"✅ Summoning Completed\n\n"
            f"👥 Tagged: {tagged}\n"
            f"⏭ Skipped: {skipped}"
        )

    except Exception as e:
        active_tags[chat_id] = False
        error = traceback.format_exc()
        print(error)
        await send_error_log("SUMMON", error)
        await progress.edit_text("❌ Error Aa Gaya")


# ---------------- ADMINS (FIXED + BATCH) ---------------- #

@app.on_message(filters.command("admins", prefixes=["/", ".", "!"]) & filters.group)
@admin_or_owner
async def admins_handler(_, message: Message):
    chat_id = message.chat.id

    if len(message.command) < 2:
        return await message.reply_text("❌ Example:\n/admins meeting now")

    text = message.text.split(None, 1)[1]

    active_tags[chat_id] = True

    progress = await message.reply_text("👮 Fetching Admins...")

    try:
        admin_users, skipped = await fetch_eligible_users(chat_id, only_admins=True)

        if not admin_users:
            active_tags[chat_id] = False
            return await progress.edit_text("❌ No Admins Found (besides bots)")

        await send_log(f"👮 ADMINS\n👤 {message.from_user.first_name}\n👮 Count: {len(admin_users)}")

        tagged = 0
        batch = []

        for idx, user in enumerate(admin_users):
            if not active_tags.get(chat_id):
                break

            batch.append(user)

            if len(batch) == BATCH_SIZE or idx == len(admin_users) - 1:
                sent = await send_batch_tag(chat_id, text, batch)
                tagged += sent
                batch = []
                await asyncio.sleep(BATCH_DELAY)

        active_tags[chat_id] = False

        await progress.edit_text(
            f"✅ Admin Summon Completed\n\n"
            f"👮 Tagged: {tagged}\n"
            f"⏭ Skipped: {skipped}"
        )

    except Exception as e:
        active_tags[chat_id] = False
        error = traceback.format_exc()
        print(error)
        await send_error_log("ADMINS", error)
        await progress.edit_text("❌ Error Aa Gaya")


# ---------------- HELP ---------------- #

@app.on_message(filters.command("help", prefixes=["/", ".", "!"]))
async def help_command(_, message: Message):
    await message.reply_text(
        "📚 COMMANDS\n\n"
        "/summon message → Tag Members (3/msg)\n"
        "/admins message → Tag Admins (3/msg)\n"
        "/stoptag → Stop Summon\n"
        "/blacklist → Block Group\n"
        "/whitelist → Unblock Group\n"
        "/ping → Check Bot"
    )


# ---------------- START ---------------- #

print("✅ Userbot Started (Batch=3, Limit=5k)")

try:
    app.run()
except Exception as e:
    print(e)
