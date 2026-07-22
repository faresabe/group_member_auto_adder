# Telegram Auto-Add Bot

Runs on your own Telegram account. When you or an authorized person sends it a
message containing phone numbers, it adds each number to a target group.

Accepted formats: `0912345678`, `0712345678`, `251912345678`, `+251912345678`
(one or many per message, separated by spaces/commas/newlines).

## 1. Get API credentials

1. Go to https://my.telegram.org and log in with your phone number.
2. Open **API Development Tools**.
3. Create an app (any name/description is fine) and copy the **api_id** and
   **api_hash**.

## 2. Install dependencies

```bash
pip install telethon python-dotenv
```

## 3. Configure

1. Copy `.env.example` to `.env`.
2. Fill in `API_ID` and `API_HASH` from step 1.
3. Set `TARGET_GROUP` to the group's `@username`, or its numeric ID
   (you can get the ID by forwarding a message from the group to
   @userinfobot, or using Telethon's `client.get_dialogs()` once logged in).
4. Set `AUTHORIZED_USER_IDS` — the Telegram numeric IDs of everyone allowed
   to submit numbers (get your own from @userinfobot; ask your manager to do
   the same and share theirs with you).
5. Leave `DELAY_BETWEEN_ADDS` at 8 or higher to reduce the risk of Telegram
   flagging the account.

Then load the `.env` file — either run:

```bash
export $(cat .env | xargs)   # macOS/Linux
```

or add this near the top of `bot.py`:

```python
from dotenv import load_dotenv
load_dotenv()
```

## 4. First run (login)

```bash
python bot.py
```

The first time you run it, Telethon will ask for your phone number and the
login code Telegram sends you (and your 2FA password if you have one). After
that, it saves a session file (`add_bot_session.session`) and won't ask
again — keep that file private, it's equivalent to being logged into your
account.

## 5. Use it

Message your own account (Saved Messages) or have an authorized user DM the
account running this script with numbers, e.g.:

```
0912345678
0798765432
```

The bot replies with a per-number result: added, already in group, blocked
by privacy settings, not found, etc.

## Important limits and risks

- **This automates a real user account, not a bot-token bot** — it's the
  only way to add someone by phone number. Telegram's Terms of Service
  discourage bulk/automated actions on regular accounts, and the account can
  be temporarily limited (or in severe/repeated cases, banned) if it adds
  people too fast or gets reported.
- A number can only be added if it's an active Telegram account and its
  privacy settings allow being added by non-contacts — some numbers will
  fail with "privacy settings block being added." That's expected and not a
  bug.
- Keep volume moderate and the delay reasonable (8+ seconds is a sane
  starting point). If you get a `FLOOD` error, stop entirely for a while
  before trying again.
- The account running this must already be a member of the target group,
  and the group must allow members to add others (or the account needs
  admin rights).
