# tagbot.py — TagBot Module (Pyrogram)

import asyncio
import traceback

from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import ChatMembersFilter, ParseMode
from pyrogram.errors import FloodWait, ChatAdminRequired, UserNotParticipant, MessageIdInvalid, MessageNotModified


async def safe_edit(msg, text: str):
    """Edit message safely — agar message delete ho gaya ho toh crash mat karo."""
    try:
        await msg.edit_text(text)
    except (MessageIdInvalid, MessageNotModified):
        pass
    except Exception as e:
        print(f"[TagBot] safe_edit error: {e}")

# ============================================================ #
#                      TAGBOT CONFIG
# ============================================================ #

BATCH_SIZE  = 3
BATCH_DELAY = 6
COOLDOWN_SEC = 180
MAX_FETCH   = 10000

active_tags: dict    = {}
tag_cooldown: dict   = {}
blacklist_groups: set = set()


# ============================================================ #
#                      ADMIN CHECK
# ============================================================ #

async def is_admin_or_owner(app: Client, user_id: int, chat_id: int, owner_id: int) -> bool:
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
    eligible = []
    unique   = set()
    skipped  = 0

    try:
        if only_admins:
            async for member in client.get_chat_members(chat_id, filter=ChatMembersFilter.ADMINISTRATORS):
                user = member.user
                if user.is_deleted or user.is_bot:
                    skipped += 1
                    continue
                if user.id in unique:
                    skipped += 1
                    continue
                unique.add(user.id)
                eligible.append(user)
        else:
            # Method 1: Direct pagination with offset (5k+ groups ke liye)
            offset = 0
            limit  = 200
            empty_streak = 0

            while len(unique) < MAX_FETCH:
                try:
                    batch_members = await client.get_chat_members(
                        chat_id,
                        filter=ChatMembersFilter.RECENT,
                        offset=offset,
                        limit=limit,
                    )
                    if not batch_members:
                        empty_streak += 1
                        if empty_streak >= 3:
                            break
                        offset += limit
                        continue

                    empty_streak = 0
                    added_this_batch = 0

                    for member in batch_members:
                        user = member.user
                        if user.is_deleted or user.is_bot:
                            skipped += 1
                            continue
                        if user.id in unique:
                            continue
                        unique.add(user.id)
                        eligible.append(user)
                        added_this_batch += 1

                    print(f"[TagBot] offset={offset} fetched={len(batch_members)} new={added_this_batch} total={len(unique)}")

                    # Agar 3 consecutive batches mein koi naya nahi mila toh band karo
                    if added_this_batch == 0:
                        empty_streak += 1
                        if empty_streak >= 3:
                            break
                    else:
                        empty_streak = 0

                    offset += limit
                    await asyncio.sleep(0.5)  # Rate limit avoid

                except FloodWait as e:
                    print(f"[TagBot] FloodWait during fetch: {e.value}s")
                    await asyncio.sleep(e.value + 2)
                except Exception as e:
                    print(f"[TagBot] Offset {offset} error: {e}")
                    break

            # Method 2: a-z search trick — extra members jo offset mein miss hue
            queries = list("abcdefghijklmnopqrstuvwxyz0123456789")
            for q in queries:
                if len(unique) >= MAX_FETCH:
                    break
                try:
                    async for member in client.get_chat_members(chat_id, query=q):
                        user = member.user
                        if user.is_deleted or user.is_bot:
                            skipped += 1
                            continue
                        if user.id in unique:
                            continue
                        unique.add(user.id)
                        eligible.append(user)
                    await asyncio.sleep(0.3)
                except FloodWait as e:
                    await asyncio.sleep(e.value + 1)
                except Exception as e:
                    print(f"[TagBot] Query '{q}' error: {e}")
                    continue

    except Exception as e:
        print(f"[TagBot] Fetch error: {e}")
        raise

    print(f"[TagBot] Fetched: {len(eligible)} eligible, {skipped} skipped")
    return eligible, skipped


# ============================================================ #
#                      SEND BATCH
# ============================================================ #

async def send_batch(client: Client, chat_id: int, text: str, users_batch: list) -> int:
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

    # ── /summon ──────────────────────────────────────────────

    @app.on_message(filters.command("summon", prefixes=["/", ".", "!"]) & filters.group)
    async def summon_command(client: Client, message: Message):
        user    = message.from_user
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
            return await message.reply("❌ Usage: /summon <message>")

        text = message.text.split(None, 1)[1]
        tag_cooldown[chat_id] = now + COOLDOWN_SEC
        active_tags[chat_id]  = True
        progress = await message.reply("🚀 Collecting members...")

        try:
            eligible, skipped = await fetch_users(client, chat_id, only_admins=False)

            if not eligible:
                active_tags[chat_id] = False
                await safe_edit(progress, "❌ No eligible members found")
                return

            total = len(eligible)
            await safe_edit(progress, f"🚀 Summoning {total} members...")

            tagged = 0
            batch  = []

            for idx, u in enumerate(eligible):
                if not active_tags.get(chat_id, False):
                    await safe_edit(progress, f"🛑 Stopped. Tagged: {tagged}")
                    return

                batch.append(u)

                if len(batch) == BATCH_SIZE or idx == total - 1:
                    tagged += await send_batch(client, chat_id, text, batch)
                    batch = []
                    if tagged > 0 and tagged % 30 == 0:
                        try:
                            await safe_edit(progress, f"🚀 Tagged: {tagged}/{total}")
                        except Exception:
                            pass
                    await asyncio.sleep(BATCH_DELAY)

            active_tags[chat_id] = False
            await safe_edit(progress, 
                f"✅ Summoning Complete!\n\n👥 Tagged: {tagged}\n⏭️ Skipped: {skipped}"
            )

        except Exception:
            active_tags[chat_id] = False
            err = traceback.format_exc()
            print(err)
            await error_log_fn("SUMMON", err)
            await safe_edit(progress, "❌ Error occurred during summoning")

    # ── /admins ──────────────────────────────────────────────

    @app.on_message(filters.command("admins", prefixes=["/", ".", "!"]) & filters.group)
    async def admins_command(client: Client, message: Message):
        user    = message.from_user
        chat_id = message.chat.id

        if not await is_admin_or_owner(client, user.id, chat_id, owner_id):
            return await message.reply("» Only admins can use this command")

        if len(message.command) < 2:
            return await message.reply("❌ Usage: /admins <message>")

        text = message.text.split(None, 1)[1]
        active_tags[chat_id] = True
        progress = await message.reply("👮 Fetching admins...")

        try:
            eligible, skipped = await fetch_users(client, chat_id, only_admins=True)

            if not eligible:
                active_tags[chat_id] = False
                await safe_edit(progress, "❌ No admin users found")
                return

            total  = len(eligible)
            tagged = 0
            batch  = []

            for idx, u in enumerate(eligible):
                if not active_tags.get(chat_id, False):
                    break

                batch.append(u)

                if len(batch) == BATCH_SIZE or idx == total - 1:
                    tagged += await send_batch(client, chat_id, text, batch)
                    batch = []
                    await asyncio.sleep(BATCH_DELAY)

            active_tags[chat_id] = False
            await safe_edit(progress, 
                f"✅ Admin summon complete!\n\n👮 Tagged: {tagged}\n⏭️ Skipped: {skipped}"
            )

        except Exception:
            active_tags[chat_id] = False
            err = traceback.format_exc()
            print(err)
            await error_log_fn("ADMINS", err)
            await safe_edit(progress, "❌ Error occurred")

    # ── /stoptag ─────────────────────────────────────────────

    @app.on_message(filters.command("stoptag", prefixes=["/", ".", "!"]) & filters.group)
    async def stop_tag_command(client: Client, message: Message):
        if not await is_admin_or_owner(client, message.from_user.id, message.chat.id, owner_id):
            return await message.reply("» Only admins can use this command")
        chat_id = message.chat.id
        if active_tags.get(chat_id, False):
            active_tags[chat_id] = False
            await message.reply("🛑 Summoning stopped")
        else:
            await message.reply("ℹ️ No active summoning running")

    # ── /blacklist ────────────────────────────────────────────

    @app.on_message(filters.command("blacklist", prefixes=["/", ".", "!"]) & filters.group)
    async def blacklist_command(client: Client, message: Message):
        if message.from_user.id != owner_id:
            return await message.reply("» Only bot owner can use this")
        blacklist_groups.add(message.chat.id)
        await message.reply("🚫 Group blacklisted from summoning")

    # ── /whitelist ────────────────────────────────────────────

    @app.on_message(filters.command("whitelist", prefixes=["/", ".", "!"]) & filters.group)
    async def whitelist_command(client: Client, message: Message):
        if message.from_user.id != owner_id:
            return await message.reply("» Only bot owner can use this")
        blacklist_groups.discard(message.chat.id)
        await message.reply("✅ Group whitelisted")
