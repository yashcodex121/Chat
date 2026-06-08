# tagbot.py — TagBot Module (Pyrogram)
# Yeh file sirf tagging ke liye hai — main.py se import hoti hai

import asyncio
import traceback

from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import ChatMembersFilter, ParseMode
from pyrogram.errors import FloodWait

# ============================================================ #
#                      TAGBOT CONFIG
# ============================================================ #

BATCH_SIZE = 3        # Ek message mein kitne log tag hon
BATCH_DELAY = 6       # Har batch ke baad kitne seconds wait karein
COOLDOWN_SEC = 180    # Ek summon ke baad dobara summon ka wait time
MAX_FETCH = 5000      # Max kitne members fetch karein

active_tags: dict = {}
tag_cooldown: dict = {}
blacklist_groups: set = set()


# ============================================================ #
#                      ADMIN CHECK
# ============================================================ #

async def is_admin_or_owner(app: Client, user_id: int, chat_id: int, owner_id: int) -> bool:
    """Check karo user admin ya owner hai ya nahi."""
    if user_id == owner_id:
        return True
    try:
        async for member in app.get_chat_members(chat_id, filter=ChatMembersFilter.ADMINISTRATORS):
            if member.user.id == user_id:
                return True
    except Exception as e:
        print(f"[TagBot] Admin check error: {e}")
    return False


# ============================================================ #
#                      FETCH USERS
# ============================================================ #

async def fetch_users(client: Client, chat_id: int, only_admins: bool = False):
    """
    Group ke eligible users fetch karo.
    Returns: (eligible_list, skipped_count)
    """
    eligible = []
    unique = set()
    skipped = 0
    count = 0

    filter_type = ChatMembersFilter.ADMINISTRATORS if only_admins else ChatMembersFilter.RECENT

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
        print(f"[TagBot] Fetch error: {e}")
        raise

    return eligible, skipped


# ============================================================ #
#                      SEND BATCH
# ============================================================ #

async def send_batch(client: Client, chat_id: int, text: str, users_batch: list) -> int:
    """
    Ek batch message bhejo jisme BATCH_SIZE log mention hon.
    Returns: successfully tagged count
    """
    if not users_batch:
        return 0

    mentions = " ".join(
        f'<a href="tg://user?id={u.id}">{u.first_name}</a>'
        for u in users_batch
    )
    message_text = f"{mentions}\n{text}"

    try:
        await client.send_message(chat_id, message_text, parse_mode=ParseMode.HTML)
        return len(users_batch)
    except FloodWait as e:
        wait_time = e.value * 1.5
        print(f"[TagBot] FloodWait: {wait_time:.1f}s")
        await asyncio.sleep(wait_time)
        try:
            await client.send_message(chat_id, message_text, parse_mode=ParseMode.HTML)
            return len(users_batch)
        except Exception:
            return 0
    except Exception as e:
        print(f"[TagBot] Send error: {e}")
        return 0


# ============================================================ #
#                      REGISTER HANDLERS
# ============================================================ #

def register_tagbot(app: Client, owner_id: int, error_log_fn):
    """
    Saare TagBot handlers register karo.
    app         → Pyrogram Client
    owner_id    → Bot owner ka Telegram ID
    error_log_fn → async function(command_name, error_text)
    """

    # ── /summon ──────────────────────────────────────────────

    @app.on_message(filters.command("summon", prefixes=["/", ".", "!"]) & filters.group)
    async def summon_command(client: Client, message: Message):
        """Sabko tag karo (3 per message)."""
        user = message.from_user
        chat_id = message.chat.id

        if not await is_admin_or_owner(client, user.id, chat_id, owner_id):
            return await message.reply("» Only admins can use this command")

        if chat_id in blacklist_groups:
            return await message.reply("🚫 This group is blacklisted from summoning")

        now = asyncio.get_event_loop().time()
        if chat_id in tag_cooldown and (tag_cooldown[chat_id] - now) > 0:
            remaining = int(tag_cooldown[chat_id] - now)
            return await message.reply(f"❌ Anti-spam active. Wait {remaining} seconds.")

        if len(message.command) < 2:
            return await message.reply("❌ Usage:\n`/summon <message>`", quote=True)

        text = message.text.split(None, 1)[1]
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
                    sent = await send_batch(client, chat_id, text, batch)
                    tagged += sent
                    batch = []

                    # Har 30 tags pe progress update
                    if tagged > 0 and tagged % 30 == 0:
                        try:
                            await progress.edit_text(f"🚀 Tagged: {tagged}/{total}")
                        except Exception:
                            pass

                    await asyncio.sleep(BATCH_DELAY)

            active_tags[chat_id] = False
            await progress.edit_text(
                f"✅ Summoning Complete!\n\n"
                f"👥 Tagged: {tagged}\n"
                f"⏭ Skipped (bots/deleted): {skipped}"
            )

        except Exception:
            active_tags[chat_id] = False
            error = traceback.format_exc()
            print(error)
            await error_log_fn("SUMMON", error)
            await progress.edit_text("❌ Error occurred during summoning")

    # ── /admins ──────────────────────────────────────────────

    @app.on_message(filters.command("admins", prefixes=["/", ".", "!"]) & filters.group)
    async def admins_command(client: Client, message: Message):
        """Sirf admins ko tag karo."""
        user = message.from_user
        chat_id = message.chat.id

        if not await is_admin_or_owner(client, user.id, chat_id, owner_id):
            return await message.reply("» Only admins can use this command")

        if len(message.command) < 2:
            return await message.reply("❌ Usage:\n`/admins <message>`", quote=True)

        text = message.text.split(None, 1)[1]
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
                    sent = await send_batch(client, chat_id, text, batch)
                    tagged += sent
                    batch = []
                    await asyncio.sleep(BATCH_DELAY)

            active_tags[chat_id] = False
            await progress.edit_text(
                f"✅ Admin summon complete!\n\n"
                f"👮 Tagged: {tagged}\n"
                f"⏭ Skipped: {skipped}"
            )

        except Exception:
            active_tags[chat_id] = False
            error = traceback.format_exc()
            print(error)
            await error_log_fn("ADMINS", error)
            await progress.edit_text("❌ Error occurred")

    # ── /stoptag ─────────────────────────────────────────────

    @app.on_message(filters.command("stoptag", prefixes=["/", ".", "!"]) & filters.group)
    async def stop_tag_command(client: Client, message: Message):
        """Chal raha summon rok do."""
        user = message.from_user
        chat_id = message.chat.id

        if not await is_admin_or_owner(client, user.id, chat_id, owner_id):
            return await message.reply("» Only admins can use this command")

        if chat_id in active_tags and active_tags[chat_id]:
            active_tags[chat_id] = False
            await message.reply("🛑 Summoning stopped")
        else:
            await message.reply("ℹ️ No active summoning running")

    # ── /blacklist ────────────────────────────────────────────

    @app.on_message(filters.command("blacklist", prefixes=["/", ".", "!"]) & filters.group)
    async def blacklist_command(client: Client, message: Message):
        """Group ko summon se blacklist karo (owner only)."""
        if message.from_user.id != owner_id:
            return await message.reply("» Only bot owner can use this")
        blacklist_groups.add(message.chat.id)
        await message.reply("🚫 Group blacklisted from summoning")

    # ── /whitelist ────────────────────────────────────────────

    @app.on_message(filters.command("whitelist", prefixes=["/", ".", "!"]) & filters.group)
    async def whitelist_command(client: Client, message: Message):
        """Group ko blacklist se hatao (owner only)."""
        if message.from_user.id != owner_id:
            return await message.reply("» Only bot owner can use this")
        blacklist_groups.discard(message.chat.id)
        await message.reply("✅ Group whitelisted")
