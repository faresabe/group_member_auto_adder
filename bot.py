"""
Telegram auto-add bot
----------------------
Runs on YOUR Telegram account (via Telethon). Listens for messages from you
or authorized people containing phone numbers (formats: 09XXXXXXXX,
07XXXXXXXX, or 251XXXXXXXXX / +251XXXXXXXXX), normalizes them, and either:
  1. Adds the number directly to the target group, or
  2. If their privacy settings block direct adding, DMs them the group's
     invite link instead.

Numbers are only added to your Telegram contacts temporarily (if not
already a contact) and removed again immediately after, so your real
contact list/names are never overwritten.

Setup instructions are in README.md.
"""

import asyncio
import os
import re
import logging

from telethon import TelegramClient, events
from telethon.tl.functions.messages import AddChatUserRequest, ExportChatInviteRequest
from telethon.tl.functions.channels import InviteToChannelRequest
from telethon.tl.functions.contacts import ImportContactsRequest, DeleteContactsRequest
from telethon.tl.types import InputPhoneContact, Channel
from telethon.errors import (
    PeerFloodError,
    UserPrivacyRestrictedError,
    UserNotMutualContactError,
    FloodWaitError,
    UserAlreadyParticipantError,
    ChatAdminRequiredError,
)
from dotenv import load_dotenv

load_dotenv()  

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("add-bot")

# ---------- CONFIG (loaded from environment variables, see .env.example) ----------
API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
SESSION_NAME = os.environ.get("SESSION_NAME", "add_bot_session")

# Group you want people added to. Can be a numeric ID (as string) or @username
# of the group. Must be a group/supergroup you are already a member/admin of.
TARGET_GROUP = os.environ["TARGET_GROUP"]

# Comma-separated list of Telegram user IDs allowed to submit numbers.
# Find your own numeric user ID by messaging @userinfobot on Telegram.
AUTHORIZED_USER_IDS = {
    int(uid.strip()) for uid in os.environ.get("AUTHORIZED_USER_IDS", "").split(",") if uid.strip()
}

# Seconds to wait between each add attempt, to stay under Telegram's radar.
DELAY_BETWEEN_ADDS = float(os.environ.get("DELAY_BETWEEN_ADDS", "8"))

# ---------- Phone number normalization ----------
# Matches 09XXXXXXXX / 07XXXXXXXX / 251XXXXXXXXX / +251XXXXXXXXX
NUMBER_PATTERN = re.compile(r"(?:\+?251|0)([79]\d{8})")


def normalize_numbers(text: str) -> list[str]:
    """Extract and normalize every Ethiopian phone number found in text."""
    found = NUMBER_PATTERN.findall(text)
    return [f"+251{digits}" for digits in found]


async def get_invite_link(client: TelegramClient, entity) -> str:
    """Fetch (or reuse) the group's primary invite link."""
    result = await client(ExportChatInviteRequest(peer=entity))
    return result.link


async def resolve_user(client: TelegramClient, phone: str):
    """
    Resolve a phone number to a Telegram user, WITHOUT permanently touching
    your contacts. Returns (user, was_temporarily_imported).
    """
    # If they're already a contact (or otherwise cached/resolvable), use that
    # directly and don't touch your contacts at all.
    try:
        user = await client.get_entity(phone)
        return user, False
    except (ValueError, TypeError):
        pass

    # Not already known — import temporarily just to resolve who they are.
    result = await client(
        ImportContactsRequest(
            [InputPhoneContact(client_id=0, phone=phone, first_name=phone, last_name="")]
        )
    )
    if not result.users:
        return None, False

    return result.users[0], True


# ---------- Core add logic ----------
async def add_number_to_group(client: TelegramClient, phone: str) -> str:
    """Attempt to add a single phone number to TARGET_GROUP.
    Falls back to DMing an invite link if direct add is privacy-blocked.
    Returns a status string."""
    imported_temp = False
    user = None
    try:
        user, imported_temp = await resolve_user(client, phone)
        if user is None:
            return f"{phone}: not found on Telegram or not reachable"

        entity = await client.get_entity(TARGET_GROUP)

        try:
            # Supergroups/channels need InviteToChannelRequest;
            # only classic "basic" groups use AddChatUserRequest.
            if isinstance(entity, Channel):
                invite_result = await client(InviteToChannelRequest(entity, [user]))
                missing = getattr(invite_result, "missing_invitees", None)
                if missing:
                    raise UserPrivacyRestrictedError(None)
            else:
                await client(AddChatUserRequest(entity.id, user.id, fwd_limit=10))

            return f"{phone}: added successfully"

        except UserPrivacyRestrictedError:
            # Fallback: their privacy settings block direct adding.
            # DM them the group's invite link instead.
            try:
                link = await get_invite_link(client, entity)
                await client.send_message(user, f"You've been invited to join the group:\n{link}")
                return f"{phone}: privacy settings blocked direct add — sent invite link via DM instead"
            except Exception as e:
                return f"{phone}: privacy blocked direct add, and couldn't DM invite link ({e})"

    except UserAlreadyParticipantError:
        return f"{phone}: already in the group"
    except UserNotMutualContactError:
        return f"{phone}: not a mutual contact, cannot add"
    except ChatAdminRequiredError:
        return f"{phone}: bot account needs admin rights in the group"
    except PeerFloodError:
        return f"{phone}: FLOOD LIMIT HIT — stop and wait a while before retrying"
    except FloodWaitError as e:
        return f"{phone}: rate limited, must wait {e.seconds}s"
    except Exception as e:
        return f"{phone}: failed ({e})"
    finally:
        # Clean up: remove the temporary contact so your real contacts
        # list/names are never left altered.
        if imported_temp and user is not None:
            try:
                await client(DeleteContactsRequest(id=[user]))
            except Exception as e:
                log.warning(f"Could not clean up temporary contact for {phone}: {e}")


async def process_message(client: TelegramClient, event):
    text = event.raw_text
    numbers = normalize_numbers(text)

    if not numbers:
        await event.reply("No valid phone numbers found. Use 09.., 07.., or 251.. format.")
        return

    await event.reply(f"Found {len(numbers)} number(s). Adding one by one, please wait...")

    results = []
    for phone in numbers:
        status = await add_number_to_group(client, phone)
        log.info(status)
        results.append(status)
        await asyncio.sleep(DELAY_BETWEEN_ADDS)

    await event.reply("Done:\n" + "\n".join(results))


async def main():
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    await client.start()  # first run will prompt for phone number + login code

    me = await client.get_me()
    log.info(f"Logged in as {me.first_name} (id={me.id})")
    if me.id not in AUTHORIZED_USER_IDS:
        log.warning("Your own account ID is not in AUTHORIZED_USER_IDS — add it so you can use the bot.")

    @client.on(events.NewMessage())
    async def handler(event):
        sender_id = event.sender_id
        if sender_id not in AUTHORIZED_USER_IDS:
            return  # silently ignore unauthorized senders
        await process_message(client, event)

    log.info("Listening for messages...")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
