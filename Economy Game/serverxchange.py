import discord
from discord.ext import commands, tasks
import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import math
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.reactions = True
intents.voice_states = True
if hasattr(intents, "moderation"):
    intents.moderation = True

bot = commands.Bot(command_prefix='$', intents=intents, help_command=None)

# ===== CONSTANTS =====

INITIAL_CASH = 10000
INITIAL_PRICE = 100
DAILY_REWARD = 500
STREAK_BONUS = 1000
PRICE_IMPACT_K = 0.2
INACTIVITY_THRESHOLD = 4 * 3600  # 4 hours in seconds
INACTIVITY_DECAY = 0.94  # 6% drop
LIQUIDATION_THRESHOLD = 1.5  # 150% of entry price
MIN_PRICE = 70

# Timezone offset for scheduling
TIMEZONE_OFFSET_HOURS = 0   # adjust if you want local vs UTC

# Weekly market reset (Monday 8:00 AM EST = 13:00 UTC)
WEEKLY_RESET_DAY = 0        # Monday
WEEKLY_RESET_HOUR_UTC = 13  # 8 AM EST = 13:00 UTC

# Shorts behavior
SHORT_FREEZE_MINUTES = 30

# Activity-driven price tick
ACTIVITY_TICK_MINUTES = 15

# VC ping roles (host pings)
VC_PING_ROLES = [
    XXXXXXXXXXXXXXXXXXX,
    XXXXXXXXXXXXXXXXXXX,
    XXXXXXXXXXXXXXXXXXX,
    XXXXXXXXXXXXXXXXXXX,
    XXXXXXXXXXXXXXXXXXX,
    XXXXXXXXXXXXXXXXXXX,
    XXXXXXXXXXXXXXXXXXX,
    XXXXXXXXXXXXXXXXXXX]


VOICE_PING_WINDOW_SECONDS = 5400  # 1.5-hour window for first-10 join bonus
FAST_RESPONSE_SECONDS = 120       # <= 2 minutes = big activity bonus
MEDIUM_RESPONSE_SECONDS = 300     # <= 5 minutes = medium activity bonus
VOICE_PING_HOUR_WINDOW = 3600    # 1-hour window for 3% per-person stock trend

# VC ping stock uptick bonuses
VC_PING_FIRST_N = 10              # First 10 joiners get the join uptick
VC_PING_JOIN_UPTICK = 0.005        # 20% price uptick on join (first 10)
VC_PING_STAY_MINUTES = 60         # Stay 1 hour in VC for additional bonus
VC_PING_STAY_UPTICK = 0.05        # 50% additional uptick for staying 1H (first 10)
VC_PING_LATE_STAY_UPTICK = 0.008   # 30% additional uptick for staying 1H (after first 10)
VC_PING_PER_JOIN_TREND = 0.03     # 3% stock trend per person joining within 1H

# Moderation penalty
MODERATION_PENALTY = 0.45          # 17% stock price drop on warning/timeout

# Photo bonus channels
PHOTO_BONUS_CHANNEL_IDS = {
    XXXXXXXXXXXXXXXXXXX,
    XXXXXXXXXXXXXXXXXXX}


# Hedge fund APY / penalty
HEDGE_FUND_BASE_APY = 0.15      # 15% nominal monthly
EARLY_WITHDRAW_PENALTY = 0.05   # -5% APY per early withdrawal
PENALTY_DURATION_DAYS = 14      # penalty lasts 2 weeks

# Events wallet (no penalty flows)
EVENTS_WALLET_USER_ID = "events_wallet"  # pseudo-user key in funds_data

# Data storage paths
DATA_DIR = "data"
USERS_FILE = os.path.join(DATA_DIR, "users.json")
FUNDS_FILE = os.path.join(DATA_DIR, "funds.json")
PRICES_FILE = os.path.join(DATA_DIR, "prices.json")
FUND_PENALTIES_FILE = os.path.join(DATA_DIR, "fund_penalties.json")

# In-memory data
users_data: Dict[str, dict] = {}
funds_data: Dict[str, dict] = {}
prices_data: Dict[str, dict] = {}
fund_penalty_history: Dict[str, dict] = {}

# Voice/VC tracking
voice_sessions = {}        # user_id -> {"start": datetime, "channel_id": int, "role_ping": bool}
voice_ping_sessions = {}   # message_id -> {"host_id": str, "channel_id": int, "timestamp": str}

# Per-user trade cooldowns
last_trade_time: Dict[str, datetime] = {}
TRADE_COOLDOWN_SECONDS = 15 * 60

# ===== TIME/DATE HELPERS =====

def get_now_with_offset() -> datetime:
    return datetime.utcnow() + timedelta(hours=TIMEZONE_OFFSET_HOURS)

def is_trade_on_cooldown(user_id: str) -> Optional[int]:
    """Return seconds remaining if on cooldown, else None."""
    now = get_now_with_offset()
    last = last_trade_time.get(user_id)
    if not last:
        return None
    elapsed = (now - last).total_seconds()
    if elapsed >= TRADE_COOLDOWN_SECONDS:
        return None
    return int(TRADE_COOLDOWN_SECONDS - elapsed)

def set_trade_time(user_id: str):
    last_trade_time[user_id] = get_now_with_offset()
    
LOG_FILE = os.path.join(DATA_DIR, "audit_log.jsonl")

def save_log_entry(entry: dict):
    ensure_data_dir()
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")    

# ===== DATA MANAGEMENT =====

def ensure_data_dir():
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)

def load_data():
    global users_data, funds_data, prices_data, fund_penalty_history

    ensure_data_dir()

    try:
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, 'r') as f:
                users_data = json.load(f)
        else:
            users_data = {}
    except Exception as e:
        print(f"Error loading users data: {e}")
        users_data = {}

    try:
        if os.path.exists(FUNDS_FILE):
            with open(FUNDS_FILE, 'r') as f:
                funds_data = json.load(f)
        else:
            funds_data = {}
    except Exception as e:
        print(f"Error loading funds data: {e}")
        funds_data = {}

    try:
        if os.path.exists(PRICES_FILE):
            with open(PRICES_FILE, 'r') as f:
                prices_data = json.load(f)
        else:
            prices_data = {}
    except Exception as e:
        print(f"Error loading prices data: {e}")
        prices_data = {}

    try:
        if os.path.exists(FUND_PENALTIES_FILE):
            with open(FUND_PENALTIES_FILE, 'r') as f:
                fund_penalty_history = json.load(f)
        else:
            fund_penalty_history = {}
    except Exception as e:
        print(f"Error loading fund penalties: {e}")
        fund_penalty_history = {}

def save_data():
    ensure_data_dir()
    try:
        with open(USERS_FILE, 'w') as f:
            json.dump(users_data, f, indent=2)
    except Exception as e:
        print(f"Error saving users data: {e}")
    try:
        with open(FUNDS_FILE, 'w') as f:
            json.dump(funds_data, f, indent=2)
    except Exception as e:
        print(f"Error saving funds data: {e}")
    try:
        with open(PRICES_FILE, 'w') as f:
            json.dump(prices_data, f, indent=2)
    except Exception as e:
        print(f"Error saving prices data: {e}")
    try:
        with open(FUND_PENALTIES_FILE, 'w') as f:
            json.dump(fund_penalty_history, f, indent=2)
    except Exception as e:
        print(f"Error saving fund penalties: {e}")

# ===== USER / PRICE / FUND MANAGEMENT =====

def ensure_user(user_id: str):
    if user_id not in users_data:
        users_data[user_id] = {
            "cash_balance": INITIAL_CASH,
            "net_worth": INITIAL_CASH,
            "month_start_net_worth": INITIAL_CASH,
            "portfolio": {
                "long": {},
                "short": {}
            },
            "activity": {
                "today": {
                    "text_msgs": 0,
                    "media_msgs": 0,
                    "voice_minutes": 0,
                    "voice_unique_channels": [],
                    "reaction_count": 0,
                    "reply_count": 0,
                    "role_ping_joins": 0,
                    "role_ping_join_minutes": 0,
                    "timestamp": datetime.utcnow().isoformat()
                },
                "week": {
                    "text_msgs": 0,
                    "media_msgs": 0,
                    "voice_minutes": 0,
                    "voice_unique_channels": [],
                    "reaction_count": 0,
                    "reply_count": 0,
                    "role_ping_joins": 0,
                    "role_ping_join_minutes": 0,
                    "timestamp": datetime.utcnow().isoformat()
                }
            },
            "daily": {
                "last_claim": None,
                "streak": 0
            },
            "last_activity": datetime.utcnow().isoformat(),
            "opted_out": False
        }
        save_data()

def ensure_price(user_id: str):
    if user_id not in prices_data:
        prices_data[user_id] = {
            "current": INITIAL_PRICE,
            "history": [],
            "high_24h": INITIAL_PRICE,
            "low_24h": INITIAL_PRICE,
            "all_time_high": INITIAL_PRICE
        }
        save_data()

def is_opted_out(user_id: str) -> bool:
    """Check if a user has opted out of the stock exchange."""
    ensure_user(user_id)
    return users_data[user_id].get("opted_out", False)

def ensure_fund(user_id: str):
    if user_id not in funds_data:
        funds_data[user_id] = {
            "name": f"Fund {user_id}",
            "manager_id": user_id,
            "cash_balance": 0,
            "investors": {}
        }
        save_data()

def ensure_events_wallet():
    if EVENTS_WALLET_USER_ID not in funds_data:
        funds_data[EVENTS_WALLET_USER_ID] = {
            "name": "Events Wallet",
            "manager_id": EVENTS_WALLET_USER_ID,
            "cash_balance": 0,
            "investors": {}
        }

def calculate_net_worth(user_id: str) -> float:
    ensure_user(user_id)
    ensure_fund(user_id)

    user = users_data[user_id]
    fund_cash = funds_data[user_id]["cash_balance"]

    cash_balance = user["cash_balance"]
    long_value = 0.0
    short_pnl = 0.0

    for target_id, position in user["portfolio"]["long"].items():
        ensure_price(target_id)
        current_price = prices_data[target_id]["current"]
        long_value += position["shares"] * current_price

    for target_id, position in user["portfolio"]["short"].items():
        ensure_price(target_id)
        current_price = prices_data[target_id]["current"]
        entry_value = position["shares"] * position["entry_price"]
        current_value = position["shares"] * current_price
        short_pnl += (entry_value - current_value)

    return cash_balance + fund_cash + long_value + short_pnl

# ===== PRICE MANAGEMENT =====

def apply_trade_price_impact(target_id: str, volume: int, is_buy: bool):
    ensure_price(target_id)
    price = prices_data[target_id]["current"]

    if is_buy:
        price += PRICE_IMPACT_K * (volume / 100)
    else:
        price -= PRICE_IMPACT_K * (volume / 100)
        price = max(price, MIN_PRICE)

    prices_data[target_id]["current"] = price

    prices_data[target_id]["high_24h"] = max(prices_data[target_id]["high_24h"], price)
    prices_data[target_id]["low_24h"] = min(prices_data[target_id]["low_24h"], price)
    prices_data[target_id]["all_time_high"] = max(prices_data[target_id].get("all_time_high", price), price)

    prices_data[target_id]["history"].append({
        "price": price,
        "timestamp": datetime.utcnow().isoformat()
    })

    cutoff = datetime.utcnow() - timedelta(hours=24)
    prices_data[target_id]["history"] = [
        h for h in prices_data[target_id]["history"]
        if datetime.fromisoformat(h["timestamp"]) > cutoff
    ]
    save_data()
    
def get_24h_price_change(user_id: str) -> float:
    ensure_price(user_id)
    history = prices_data[user_id]["history"]

    if not history:
        return 0.0

    cutoff = datetime.utcnow() - timedelta(hours=24)
    old_prices = [
        h["price"]
        for h in history
        if datetime.fromisoformat(h["timestamp"]) <= cutoff
    ]

    if not old_prices:
        old_price = history[0]["price"]
    else:
        old_price = old_prices[-1]

    current_price = prices_data[user_id]["current"]

    if old_price == 0:
        return 0.0

    return ((current_price - old_price) / old_price) * 100

# ===== ENGAGEMENT / TRENDING =====

def calculate_trending_score(activity: dict) -> float:
    text_msgs = activity.get("text_msgs", 0)
    media_msgs = activity.get("media_msgs", 0)
    voice_minutes = activity.get("voice_minutes", 0)
    unique_channels = len(activity.get("voice_unique_channels", []))
    reactions = activity.get("reaction_count", 0)
    replies = activity.get("reply_count", 0)
    role_ping_joins = activity.get("role_ping_joins", 0)
    role_ping_join_minutes = activity.get("role_ping_join_minutes", 0)

    def soft_cap(x, cap):
        return cap * (1 - math.exp(-x / cap))

    text_msgs = soft_cap(text_msgs, 100)
    media_msgs = soft_cap(media_msgs, 50)
    voice_minutes = soft_cap(voice_minutes, 300)
    reactions = soft_cap(reactions, 200)
    replies = soft_cap(replies, 100)
    role_ping_join_minutes = soft_cap(role_ping_join_minutes, 180)

    # Reduce voice contribution by 20%
    voice_minutes *= 0.8
    role_ping_join_minutes *= 0.8

    score = (
        0.05 * text_msgs +
        0.02 * media_msgs +
        0.01 * voice_minutes +
        0.015 * unique_channels +
        0.02 * reactions +
        0.03 * replies +
        0.5 * role_ping_joins +
        0.3 * role_ping_join_minutes
    )

    # Time-decay older activity (72h half-life style)
    ts_str = activity.get("timestamp")
    if ts_str:
        try:
            ts = datetime.fromisoformat(ts_str)
            age_hours = (datetime.utcnow() - ts).total_seconds() / 3600
            decay = max(0.3, math.exp(-age_hours / 72.0))
            score *= decay
        except Exception:
            pass

    return score


def get_drawdown_percentage(user_id: str) -> float:
    """How far this stock is below its 24h high, as a negative percentage."""
    ensure_price(user_id)
    current = prices_data[user_id]["current"]
    high_24h = prices_data[user_id]["high_24h"]
    if high_24h <= 0:
        return 0.0
    # -25.0 means 25% below 24h high
    return (current - high_24h) / high_24h * 100.0


def get_investors(target_id: str):
    """Return list of (user_id, shares) sorted by shares descending."""
    holders = []
    for uid, user in users_data.items():
        long_pos = user.get("portfolio", {}).get("long", {})
        if target_id in long_pos:
            shares = long_pos[target_id].get("shares", 0)
            if shares > 0:
                holders.append((uid, shares))
    holders.sort(key=lambda x: x[1], reverse=True)
    return holders


def get_engagement_tier(score: float, all_scores: List[float]) -> str:
    if not all_scores:
        return "Low"

    sorted_scores = sorted(all_scores, reverse=True)
    # using index() can be skewed with duplicates; this is a simple approach
    percentile_rank = (sorted_scores.index(score) + 1) / len(sorted_scores)

    if percentile_rank <= 0.05:
        return "Elite"
    elif percentile_rank <= 0.30:
        return "High"
    elif percentile_rank <= 0.70:
        return "Medium"
    else:
        return "Low"

def reset_activity_bucket(bucket: dict):
    bucket["text_msgs"] = 0
    bucket["media_msgs"] = 0
    bucket["voice_minutes"] = 0
    bucket["voice_unique_channels"] = []
    bucket["reaction_count"] = 0
    bucket["reply_count"] = 0
    bucket["role_ping_joins"] = 0
    bucket["role_ping_join_minutes"] = 0
    bucket["timestamp"] = datetime.utcnow().isoformat()

def compute_activity_return(user_id: str) -> float:
    """
    Map weekly engagement to a 15-minute return in %,
    tuned for ~8h with stronger upside than downside.
    """
    user = users_data[user_id]
    week_activity = user["activity"]["week"]
    score = calculate_trending_score(week_activity)

    norm = math.log10(score + 1)
    baseline = 0.5
    centered = norm - baseline

    if centered >= 0:
        raw_return = centered * 12.0   # up to ~+6% per tick
    else:
        raw_return = centered * 7.0    # down to ~-3.5% per tick

    raw_return = max(-3.5, min(6.0, raw_return))
    return raw_return

# ===== VC PING / RESPONDER =====

def is_voice_ping_message(message: discord.Message) -> bool:
    """A message counts as a voice ping if it mentions any VC ping role."""
    if not message.guild:
        return False
    if not message.role_mentions:
        return False
    for role in message.role_mentions:
        if role.id in VC_PING_ROLES:
            return True
    return False

def apply_price_uptick(user_id: str, uptick_pct: float):
    """Apply a percentage uptick to a user's stock price."""
    ensure_price(user_id)
    old_price = prices_data[user_id]["current"]
    new_price = max(old_price * (1 + uptick_pct), MIN_PRICE)
    prices_data[user_id]["current"] = new_price
    prices_data[user_id]["high_24h"] = max(prices_data[user_id]["high_24h"], new_price)
    prices_data[user_id]["all_time_high"] = max(prices_data[user_id].get("all_time_high", new_price), new_price)
    prices_data[user_id]["history"].append({
        "price": new_price,
        "timestamp": datetime.utcnow().isoformat()
    })

def reward_voice_ping_response(responder_id: str, channel_id: int):
    """Reward a user for joining any voice channel after a VC ping.

    - First 10 joiners within 1.5H: 20% stock price uptick
    - If they stay 1H in VC: additional 50% stock price uptick
    - Every joiner within 1H of ping: 3% stock price trend uptick
    """
    ensure_user(responder_id)
    ensure_price(responder_id)

    # Skip opted-out users
    if users_data[responder_id].get("opted_out", False):
        return

    now = datetime.utcnow()
    responder = users_data[responder_id]

    for msg_id, data in list(voice_ping_sessions.items()):
        host_id = data["host_id"]
        ts_str = data["timestamp"]

        try:
            ping_time = datetime.fromisoformat(ts_str)
        except Exception:
            del voice_ping_sessions[msg_id]
            continue

        age = (now - ping_time).total_seconds()

        # Clean up expired sessions (beyond 1.5h window)
        if age > VOICE_PING_WINDOW_SECONDS:
            del voice_ping_sessions[msg_id]
            continue

        # Don't reward the host for their own ping
        if responder_id == host_id:
            continue

        # Check if already responded to this ping
        responders = data.get("responders", [])
        if any(r["user_id"] == responder_id for r in responders):
            continue

        # 3% stock trend uptick for every person joining within 1 hour
        if age <= VOICE_PING_HOUR_WINDOW:
            apply_price_uptick(responder_id, VC_PING_PER_JOIN_TREND)

        # First 10 joiners within 1.5H get 20% stock price uptick
        if len(responders) < VC_PING_FIRST_N:
            apply_price_uptick(responder_id, VC_PING_JOIN_UPTICK)

            # Flag voice session for 1H stay bonus tracking (50%)
            if responder_id in voice_sessions:
                voice_sessions[responder_id]["ping_stay_start"] = now.isoformat()
                voice_sessions[responder_id]["ping_stay_uptick"] = VC_PING_STAY_UPTICK
        else:
            # After first 10: 3% join uptick already applied above
            # Track for 30% stay bonus if they remain 1H
            if responder_id in voice_sessions:
                voice_sessions[responder_id]["ping_stay_start"] = now.isoformat()
                voice_sessions[responder_id]["ping_stay_uptick"] = VC_PING_LATE_STAY_UPTICK

        # Record this responder
        responders.append({
            "user_id": responder_id,
            "join_time": now.isoformat()
        })
        data["responders"] = responders

        # Keep existing activity score bonuses (speed-based)
        if age <= FAST_RESPONSE_SECONDS:
            speed_mult = 3.0
        elif age <= MEDIUM_RESPONSE_SECONDS:
            speed_mult = 2.0
        else:
            speed_mult = 1.0

        base_points = 5.0
        bonus = base_points * speed_mult

        responder["activity"]["today"]["role_ping_join_minutes"] += bonus
        responder["activity"]["week"]["role_ping_join_minutes"] += bonus

        host = users_data.get(host_id)
        if host:
            host["activity"]["today"]["role_ping_joins"] += 0.5
            host["activity"]["week"]["role_ping_joins"] += 0.5

# ===== HEDGE FUND PENALTY & EVENTS =====

def get_user_penalty_apr(user_id: str) -> float:
    """Return the temporary APY penalty for this user, if any."""
    rec = fund_penalty_history.get(user_id)
    if not rec:
        return 0.0
    until_str = rec.get("penalty_until")
    if not until_str:
        return 0.0
    try:
        until = datetime.fromisoformat(until_str)
    except Exception:
        return 0.0
    now = datetime.utcnow()
    if now >= until:
        return 0.0
    return rec.get("penalty_apr", 0.0)

def apply_early_withdraw_penalty(user_id: str):
    """Apply or extend a penalty if the user withdraws early."""
    now = datetime.utcnow()
    rec = fund_penalty_history.get(user_id, {
        "penalty_apr": 0.0,
        "penalty_until": now.isoformat()
    })
    new_penalty = rec["penalty_apr"] + EARLY_WITHDRAW_PENALTY
    penalty_until = now + timedelta(days=PENALTY_DURATION_DAYS)
    fund_penalty_history[user_id] = {
        "penalty_apr": new_penalty,
        "penalty_until": penalty_until.isoformat()
    }
    save_data()

# ===== BOT EVENTS =====

@bot.event
async def on_ready():
    print(f'{bot.user} is online!')
    load_data()
    ensure_events_wallet()
    monthly_rollover_check.start()
    inactivity_price_decay.start()
    short_liquidation_check.start()
    short_freeze_check.start()
    activity_price_step.start()
    weekly_market_reset.start()

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    user_id = str(message.author.id)
    ensure_user(user_id)
    ensure_price(user_id)

    user = users_data[user_id]
    user["last_activity"] = datetime.utcnow().isoformat()

    # Photo bonus channels
    if message.attachments:
        user["activity"]["today"]["media_msgs"] += 1
        user["activity"]["week"]["media_msgs"] += 1

        if message.channel and message.channel.id in PHOTO_BONUS_CHANNEL_IDS:
            # Big bonus for media in special channels
            user["activity"]["today"]["role_ping_join_minutes"] += 10.0
            user["activity"]["week"]["role_ping_join_minutes"] += 10.0
    else:
        user["activity"]["today"]["text_msgs"] += 1
        user["activity"]["week"]["text_msgs"] += 1

    if message.reference and getattr(message.reference, 'message_id', None):
        user["activity"]["today"]["reply_count"] += 1
        user["activity"]["week"]["reply_count"] += 1

    # Voice channel activity bonus: +4% stock uptick for each message/media sent while in voice
    if user_id in voice_sessions:
        apply_price_uptick(user_id, 0.04)

    # Voice ping detection
    member = message.author
    if isinstance(member, discord.Member) and member.voice and member.voice.channel:
        if is_voice_ping_message(message):
            voice_ping_sessions[message.id] = {
                "host_id": user_id,
                "channel_id": member.voice.channel.id,
                "timestamp": datetime.utcnow().isoformat(),
                "responders": []
            }
            user["activity"]["today"]["role_ping_joins"] += 1
            user["activity"]["week"]["role_ping_joins"] += 1

    save_data()

    await bot.process_commands(message)

@bot.event
async def on_reaction_add(reaction, user):
    if user.bot:
        return

    user_id = str(user.id)
    ensure_user(user_id)

    users_data[user_id]["activity"]["today"]["reaction_count"] += 1
    users_data[user_id]["activity"]["week"]["reaction_count"] += 1
    users_data[user_id]["last_activity"] = datetime.utcnow().isoformat()

    save_data()

@bot.event
async def on_member_update(before, after):
    """Detect when a member gets timed out and drop their stock price by 17%."""
    if after.bot:
        return

    # Timeout detection: timed_out_until went from None to a value
    was_timed_out = before.timed_out_until is not None
    is_timed_out = after.timed_out_until is not None

    if not was_timed_out and is_timed_out:
        user_id = str(after.id)
        ensure_user(user_id)
        ensure_price(user_id)
        apply_price_uptick(user_id, -MODERATION_PENALTY)
        save_data()
        print(f"[MODERATION] {after.display_name} timed out — stock dropped {int(MODERATION_PENALTY * 100)}%")

@bot.event
async def on_automod_action(execution):
    """Detect automod actions (warnings) and drop the user's stock price by 45%."""
    user_id = str(execution.user_id)
    ensure_user(user_id)
    ensure_price(user_id)
    apply_price_uptick(user_id, -MODERATION_PENALTY)
    save_data()
    print(f"[MODERATION] User {user_id} hit by automod — stock dropped {int(MODERATION_PENALTY * 100)}%")

@bot.event
async def on_voice_state_update(member, before, after):
    if member.bot:
        return

    user_id = str(member.id)
    ensure_user(user_id)

    # Joined a voice channel
    if before.channel is None and after.channel is not None:
        voice_sessions[user_id] = {
            "start": datetime.utcnow(),
            "channel_id": after.channel.id,
            "role_ping": False
        }
        users_data[user_id]["last_activity"] = datetime.utcnow().isoformat()
        reward_voice_ping_response(user_id, after.channel.id)
        save_data()

    # Left a voice channel
    elif before.channel is not None and after.channel is None:
        if user_id in voice_sessions:
            session = voice_sessions[user_id]
            duration = (datetime.utcnow() - session["start"]).total_seconds() / 60

            users_data[user_id]["activity"]["today"]["voice_minutes"] += duration
            users_data[user_id]["activity"]["week"]["voice_minutes"] += duration

            ch_id = str(session["channel_id"])
            if ch_id not in users_data[user_id]["activity"]["today"]["voice_unique_channels"]:
                users_data[user_id]["activity"]["today"]["voice_unique_channels"].append(ch_id)
            if ch_id not in users_data[user_id]["activity"]["week"]["voice_unique_channels"]:
                users_data[user_id]["activity"]["week"]["voice_unique_channels"].append(ch_id)

            if session["role_ping"]:
                users_data[user_id]["activity"]["today"]["role_ping_join_minutes"] += duration
                users_data[user_id]["activity"]["week"]["role_ping_join_minutes"] += duration

            # VC ping stay bonus: uptick if stayed >= 1H after ping
            ping_stay_start = session.get("ping_stay_start")
            if ping_stay_start:
                try:
                    stay_start = datetime.fromisoformat(ping_stay_start)
                    stay_minutes = (datetime.utcnow() - stay_start).total_seconds() / 60
                    if stay_minutes >= VC_PING_STAY_MINUTES:
                        uptick = session.get("ping_stay_uptick", VC_PING_STAY_UPTICK)
                        apply_price_uptick(user_id, uptick)
                except Exception:
                    pass

            del voice_sessions[user_id]
            save_data()

    # Switched channels
    elif before.channel != after.channel and before.channel is not None and after.channel is not None:
        carry_ping_stay_start = None
        carry_ping_stay_uptick = None
        if user_id in voice_sessions:
            session = voice_sessions[user_id]
            duration = (datetime.utcnow() - session["start"]).total_seconds() / 60

            users_data[user_id]["activity"]["today"]["voice_minutes"] += duration
            users_data[user_id]["activity"]["week"]["voice_minutes"] += duration

            ch_id = str(session["channel_id"])
            if ch_id not in users_data[user_id]["activity"]["today"]["voice_unique_channels"]:
                users_data[user_id]["activity"]["today"]["voice_unique_channels"].append(ch_id)
            if ch_id not in users_data[user_id]["activity"]["week"]["voice_unique_channels"]:
                users_data[user_id]["activity"]["week"]["voice_unique_channels"].append(ch_id)

            if session["role_ping"]:
                users_data[user_id]["activity"]["today"]["role_ping_join_minutes"] += duration
                users_data[user_id]["activity"]["week"]["role_ping_join_minutes"] += duration

            # Check VC ping stay bonus on channel switch
            ping_stay_start = session.get("ping_stay_start")
            if ping_stay_start:
                try:
                    stay_start = datetime.fromisoformat(ping_stay_start)
                    stay_minutes = (datetime.utcnow() - stay_start).total_seconds() / 60
                    if stay_minutes >= VC_PING_STAY_MINUTES:
                        uptick = session.get("ping_stay_uptick", VC_PING_STAY_UPTICK)
                        apply_price_uptick(user_id, uptick)
                    else:
                        # Carry over to new session so timer keeps running
                        carry_ping_stay_start = ping_stay_start
                        carry_ping_stay_uptick = session.get("ping_stay_uptick", VC_PING_STAY_UPTICK)
                except Exception:
                    pass

        new_session = {
            "start": datetime.utcnow(),
            "channel_id": after.channel.id,
            "role_ping": False
        }
        if carry_ping_stay_start:
            new_session["ping_stay_start"] = carry_ping_stay_start
            new_session["ping_stay_uptick"] = carry_ping_stay_uptick
        voice_sessions[user_id] = new_session
        users_data[user_id]["last_activity"] = datetime.utcnow().isoformat()
        reward_voice_ping_response(user_id, after.channel.id)
        save_data()
@bot.event
async def on_message_delete(message):
    log_entry = {
        "action": "message_delete",
        "user": str(message.author.id),
        "channel": str(message.channel.id),
        "content": message.content,
        "timestamp": message.created_at.isoformat()
    }
    save_log_entry(log_entry)

@bot.event
async def on_guild_role_update(before, after):
    log_entry = {
        "action": "role_update",
        "role_id": str(after.id),
        "changes": {
            "name": (before.name, after.name),
            "permissions": (before.permissions, after.permissions)
        },
        "timestamp": datetime.utcnow().isoformat()
    }
    save_log_entry(log_entry)
    
# ===== COMMANDS: ECONOMY =====

@bot.command(name='balance')
async def balance(ctx):
    """Check your cash balance and net worth."""
    user_id = str(ctx.author.id)
    ensure_user(user_id)
    ensure_fund(user_id)

    cash = users_data[user_id]["cash_balance"]
    net_worth = calculate_net_worth(user_id)
    fund_cash = funds_data[user_id]["cash_balance"]

    users_data[user_id]["net_worth"] = net_worth
    save_data()

    embed = discord.Embed(title=f"💰 {ctx.author.display_name}'s Balance", color=discord.Color.green())
    embed.add_field(name="Cash", value=f"${cash:,.2f}", inline=True)
    embed.add_field(name="Net Worth", value=f"${net_worth:,.2f}", inline=True)
    embed.add_field(name="Hedge Fund", value=f"${fund_cash:,.2f}", inline=True)

    await ctx.send(embed=embed, delete_after=45)

@bot.command(name='mb')
async def mb(ctx):
    """Shortcut for $balance."""
    await balance(ctx)

@bot.command(name='daily')
async def daily(ctx):
    """Claim your daily reward (500/day, 1000 on day 7 streak)."""
    user_id = str(ctx.author.id)
    ensure_user(user_id)

    if is_opted_out(user_id):
        await ctx.send("❌ You have opted out of the stock exchange. Use `$optin` to rejoin.", delete_after=45)
        return

    user = users_data[user_id]
    last_claim = user["daily"]["last_claim"]

    now = datetime.utcnow()
    can_claim = False

    if last_claim is None:
        can_claim = True
        user["daily"]["streak"] = 1
    else:
        last_claim_dt = datetime.fromisoformat(last_claim)
        time_since = now - last_claim_dt

        if time_since >= timedelta(days=1):
            can_claim = True
            if time_since < timedelta(days=2):
                user["daily"]["streak"] += 1
            else:
                user["daily"]["streak"] = 1

    if not can_claim:
        last_claim_dt = datetime.fromisoformat(last_claim)
        next_claim = last_claim_dt + timedelta(days=1)
        time_left = next_claim - now
        hours = int(time_left.total_seconds() // 3600)
        minutes = int((time_left.total_seconds() % 3600) // 60)
        await ctx.send(f"❌ You already claimed your daily reward! Next claim in {hours}h {minutes}m.", delete_after=30)
        return

    reward = DAILY_REWARD
    if user["daily"]["streak"] == 7:
        reward = DAILY_REWARD + STREAK_BONUS
        await ctx.send(f"🎉 **7-day streak bonus!** You received ${reward:,.0f}!", delete_after=30)
        user["daily"]["streak"] = 0
    else:
        await ctx.send(f"✅ Daily reward claimed! +${reward:,.0f} (Streak: {user['daily']['streak']} days)", delete_after=30)

    user["cash_balance"] += reward
    user["daily"]["last_claim"] = now.isoformat()
    save_data()

# ===== COMMANDS: TRADING / PRICES =====

@bot.command(name='price')
async def price(ctx, target: discord.Member = None):
    """Check a user's stock price."""
    if target is None:
        target = ctx.author

    target_id = str(target.id)

    if is_opted_out(target_id):
        await ctx.send(
            "❌ That user has opted out of the stock exchange. Their share value is not listed.",
            delete_after=30
        )
        return

    ensure_price(target_id)

    current_price = prices_data[target_id]["current"]
    price_change = get_24h_price_change(target_id)
    high_24h = prices_data[target_id]["high_24h"]
    low_24h = prices_data[target_id]["low_24h"]
    all_time_high = prices_data[target_id].get("all_time_high", current_price)

    embed = discord.Embed(
        title=f"📊 {target.display_name}'s Stock Price",
        color=discord.Color.blue()
    )
    embed.add_field(name="Current Price", value=f"${current_price:.2f}", inline=True)
    embed.add_field(name="24h Change", value=f"{price_change:+.2f}%", inline=True)
    embed.add_field(name="24h High", value=f"${high_24h:.2f}", inline=True)
    embed.add_field(name="24h Low", value=f"${low_24h:.2f}", inline=True)
    embed.add_field(name="All-Time High", value=f"${all_time_high:.2f}", inline=True)

    # === Investors (members who hold this stock) ===
    investors = get_investors(target_id)

    if investors:
        total_shares = sum(shares for _, shares in investors)
        lines = []
        for inv_id, shares in investors[:10]:  # top 10 investors
            member = ctx.guild.get_member(int(inv_id))
            name = member.display_name if member else f"User {inv_id}"
            pct = (shares / total_shares) * 100 if total_shares > 0 else 0
            lines.append(f"{name}: {shares:,} shares ({pct:.1f}%)")
        investors_text = "\n".join(lines)
    else:
        investors_text = "No investors yet."

    embed.add_field(
        name=f"Investors ({len(investors)})",
        value=investors_text,
        inline=False
    )

    await ctx.send(embed=embed, delete_after=60)


@bot.command(name='ticker')
async def ticker(ctx, target: discord.Member = None):
    """Alias for $price."""
    await price(ctx, target)


@bot.command(name='my_stock')
async def my_stock(ctx):
    """Quick view of your own stock price."""
    await price(ctx, ctx.author)
    
def trading_allowed(ctx) -> Optional[str]:
    """Return error message if trading not allowed, else None."""
    user_id = str(ctx.author.id)
    remaining = is_trade_on_cooldown(user_id)
    if remaining is not None:
        mins = remaining // 60
        secs = remaining % 60
        return f"⏱️ Trade cooldown active. Try again in {mins}m {secs}s."
    return None

@bot.command(name='buy')
async def buy(ctx, target: discord.Member, shares: int):
    """Buy shares of another user's stock."""
    if shares <= 0:
        await ctx.send("❌ Shares must be positive.", delete_after=30)
        return

    user_id = str(ctx.author.id)
    target_id = str(target.id)

    if is_opted_out(user_id):
        await ctx.send("❌ You have opted out of the stock exchange. Use `$optin` to rejoin.", delete_after=30)
        return

    if is_opted_out(target_id):
        await ctx.send("❌ That user has opted out of the stock exchange and cannot be traded.", delete_after=30)
        return

    if user_id == target_id:
        await ctx.send("❌ You cannot buy your own stock.", delete_after=30)
        return

    ensure_user(user_id)
    ensure_price(target_id)

    current_price = prices_data[target_id]["current"]
    cost = current_price * shares

    if users_data[user_id]["cash_balance"] < cost:
        await ctx.send(f"❌ Insufficient funds! You need ${cost:,.2f} but have ${users_data[user_id]['cash_balance']:,.2f}.", delete_after=30)
        return

    users_data[user_id]["cash_balance"] -= cost

    portfolio = users_data[user_id]["portfolio"]["long"]
    if target_id in portfolio:
        old_shares = portfolio[target_id]["shares"]
        old_avg = portfolio[target_id]["avg_entry"]
        new_shares = old_shares + shares
        new_avg = ((old_shares * old_avg) + (shares * current_price)) / new_shares
        portfolio[target_id]["shares"] = new_shares
        portfolio[target_id]["avg_entry"] = new_avg
        portfolio[target_id]["last_purchase_time"] = datetime.utcnow().isoformat()
    else:
        portfolio[target_id] = {
            "shares": shares,
            "avg_entry": current_price,
            "last_purchase_time": datetime.utcnow().isoformat()
        }

    apply_trade_price_impact(target_id, shares, is_buy=True)

    save_data()

    await ctx.send(f"✅ Bought {shares} shares of {target.display_name} for ${cost:,.2f} at ${current_price:.2f}/share.", delete_after=30)

@bot.command(name='sell')
async def sell(ctx, target: discord.Member, shares: int):
    """Sell shares of another user's stock."""
    if shares <= 0:
        await ctx.send("❌ Shares must be positive.", delete_after=30)
        return

    user_id = str(ctx.author.id)
    target_id = str(target.id)

    if is_opted_out(user_id):
        await ctx.send("❌ You have opted out of the stock exchange. Use `$optin` to rejoin.", delete_after=30)
        return

    ensure_user(user_id)
    ensure_price(target_id)

    portfolio = users_data[user_id]["portfolio"]["long"]

    if target_id not in portfolio or portfolio[target_id]["shares"] < shares:
        owned = portfolio.get(target_id, {}).get("shares", 0)
        await ctx.send(f"❌ Insufficient shares! You own {owned} shares of {target.display_name}.", delete_after=45)
        return

    # Check 1-hour cooldown on purchased shares
    position = portfolio[target_id]
    last_purchase = position.get("last_purchase_time")
    if last_purchase:
        try:
            purchase_time = datetime.fromisoformat(last_purchase)
            time_since_purchase = (datetime.utcnow() - purchase_time).total_seconds() / 60
            if time_since_purchase < 60:
                minutes_left = int(60 - time_since_purchase)
                await ctx.send(f"❌ Cooldown active! You must wait {minutes_left} minute(s) before selling this stock.", delete_after=30)
                return
        except Exception:
            pass

    current_price = prices_data[target_id]["current"]
    revenue = current_price * shares

    users_data[user_id]["cash_balance"] += revenue

    portfolio[target_id]["shares"] -= shares
    if portfolio[target_id]["shares"] == 0:
        del portfolio[target_id]

    apply_trade_price_impact(target_id, shares, is_buy=False)

    save_data()

    await ctx.send(f"✅ Sold {shares} shares of {target.display_name} for ${revenue:,.2f} at ${current_price:.2f}/share.", delete_after=30)

@bot.command(name='short')
async def short(ctx, target: discord.Member, shares: int):
    """Short sell another user's stock."""
    if shares <= 0:
        await ctx.send("❌ Shares must be positive.", delete_after=30)
        return

    err = trading_allowed(ctx)
    if err:
        await ctx.send(err, delete_after=30)
        return

    user_id = str(ctx.author.id)
    target_id = str(target.id)

    if is_opted_out(user_id):
        await ctx.send("❌ You have opted out of the stock exchange. Use `$optin` to rejoin.", delete_after=30)
        return

    if is_opted_out(target_id):
        await ctx.send("❌ That user has opted out of the stock exchange and cannot be traded.", delete_after=30)
        return

    if user_id == target_id:
        await ctx.send("❌ You cannot short your own stock.", delete_after=30)
        return

    ensure_user(user_id)
    ensure_price(target_id)
    ensure_fund(user_id)

    current_price = prices_data[target_id]["current"]
    notional = current_price * shares

    cash_available = users_data[user_id]["cash_balance"]
    fund_cash = funds_data[user_id]["cash_balance"]
    fund_available = fund_cash * 0.5
    total_collateral = cash_available + fund_available

    if total_collateral < notional:
        await ctx.send(f"❌ Insufficient collateral! Need ${notional:,.2f}, have ${total_collateral:,.2f} (cash + 50% of fund).", delete_after=30)
        return

    locked_cash = min(cash_available, notional)
    locked_fund = min(fund_available, notional - locked_cash)

    users_data[user_id]["cash_balance"] -= locked_cash
    funds_data[user_id]["cash_balance"] -= locked_fund

    portfolio = users_data[user_id]["portfolio"]["short"]
    now_str = datetime.utcnow().isoformat()

    if target_id in portfolio:
        position = portfolio[target_id]
        if position.get("frozen"):
            await ctx.send("❌ This short position is frozen and cannot be modified.", delete_after=30)
            return

        old_shares = position["shares"]
        old_entry = position["entry_price"]
        old_locked_cash = position["locked_cash"]
        old_locked_fund = position["locked_fund"]

        new_shares = old_shares + shares
        new_entry = ((old_shares * old_entry) + (shares * current_price)) / new_shares

        position["shares"] = new_shares
        position["entry_price"] = new_entry
        position["locked_cash"] = old_locked_cash + locked_cash
        position["locked_fund"] = old_locked_fund + locked_fund
    else:
        portfolio[target_id] = {
            "shares": shares,
            "entry_price": current_price,
            "locked_cash": locked_cash,
            "locked_fund": locked_fund,
            "created_at": now_str,
            "frozen": False
        }

    apply_trade_price_impact(target_id, shares, is_buy=False)
    set_trade_time(user_id)

    save_data()

    await ctx.send(f"✅ Shorted {shares} shares of {target.display_name} at ${current_price:.2f}/share. Locked ${locked_cash + locked_fund:,.2f} collateral.", delete_after=30)

@bot.command(name='cover')
async def cover(ctx, target: discord.Member, shares: int):
    """Cover a short position."""
    if shares <= 0:
        await ctx.send("❌ Shares must be positive.", delete_after=30)
        return

    err = trading_allowed(ctx)
    if err:
        await ctx.send(err, delete_after=30)
        return

    user_id = str(ctx.author.id)
    target_id = str(target.id)

    if is_opted_out(user_id):
        await ctx.send("❌ You have opted out of the stock exchange. Use `$optin` to rejoin.", delete_after=30)
        return

    ensure_user(user_id)
    ensure_price(target_id)
    ensure_fund(user_id)

    portfolio = users_data[user_id]["portfolio"]["short"]

    if target_id not in portfolio or portfolio[target_id]["shares"] < shares:
        owned = portfolio.get(target_id, {}).get("shares", 0)
        await ctx.send(f"❌ Insufficient short position! You have shorted {owned} shares of {target.display_name}.", delete_after=30)
        return

    position = portfolio[target_id]

    current_price = prices_data[target_id]["current"]
    cost = current_price * shares

    if users_data[user_id]["cash_balance"] < cost:
        await ctx.send(f"❌ Insufficient cash to cover! Need ${cost:,.2f}, have ${users_data[user_id]['cash_balance']:,.2f}.", delete_after=30)
        return

    users_data[user_id]["cash_balance"] -= cost

    entry_price = position["entry_price"]
    pnl = (entry_price - current_price) * shares

    proportion = shares / position["shares"]
    released_cash = position["locked_cash"] * proportion
    released_fund = position["locked_fund"] * proportion

    users_data[user_id]["cash_balance"] += released_cash
    funds_data[user_id]["cash_balance"] += released_fund

    if pnl > 0:
        users_data[user_id]["cash_balance"] += pnl

    position["shares"] -= shares
    position["locked_cash"] -= released_cash
    position["locked_fund"] -= released_fund

    if position["shares"] == 0:
        del portfolio[target_id]

    set_trade_time(user_id)
    save_data()

    pnl_text = f"+${pnl:,.2f}" if pnl > 0 else f"-${abs(pnl):,.2f}"
    await ctx.send(f"✅ Covered {shares} shares of {target.display_name} at ${current_price:.2f}/share. PnL: {pnl_text}.", delete_after=30)

def chunk_lines(lines, max_length=900):
    chunks = []
    current = ""

    for line in lines:
        if len(line) > max_length:
            line = line[:max_length - 3] + "..."

        if len(current) + len(line) + 1 > max_length:
            if current:
                chunks.append(current)
            current = line
        else:
            current = f"{current}\n{line}" if current else line

    if current:
        chunks.append(current)

    return chunks
    
@bot.command(name='portfolio')
async def portfolio_cmd(ctx, target: discord.Member = None):
    """View your portfolio or another user's portfolio."""
    if target is None:
        target = ctx.author

    target_id = str(target.id)
    ensure_user(target_id)
    ensure_fund(target_id)

    user = users_data[target_id]

    cash_balance = user["cash_balance"]
    fund_balance = funds_data[target_id]["cash_balance"]
    total_net_worth = calculate_net_worth(target_id)

    long_lines = []
    for stock_id, position in user["portfolio"]["long"].items():
        member = ctx.guild.get_member(int(stock_id))
        if not member:
            continue

        ensure_price(stock_id)

        name = member.display_name
        if len(name) > 20:
            name = name[:17] + "..."

        current_price = prices_data[stock_id]["current"]
        value = position["shares"] * current_price
        pnl = (current_price - position["avg_entry"]) * position["shares"]
        pnl_pct = ((current_price - position["avg_entry"]) / position["avg_entry"]) * 100 if position["avg_entry"] > 0 else 0

        line = (
            f"**{name}**: {position['shares']} @ ${position['avg_entry']:.2f} "
            f"(Now: ${current_price:.2f}) | Value: ${value:,.2f} | "
            f"PnL: {pnl:+,.2f} ({pnl_pct:+.1f}%)"
        )
        long_lines.append(line)

    short_lines = []
    for stock_id, position in user["portfolio"]["short"].items():
        member = ctx.guild.get_member(int(stock_id))
        if not member:
            continue

        ensure_price(stock_id)

        name = member.display_name
        if len(name) > 20:
            name = name[:17] + "..."

        current_price = prices_data[stock_id]["current"]
        pnl = (position["entry_price"] - current_price) * position["shares"]
        pnl_pct = ((position["entry_price"] - current_price) / position["entry_price"]) * 100 if position["entry_price"] > 0 else 0
        frozen_flag = " (FROZEN)" if position.get("frozen") else ""

        line = (
            f"**{name}**: {position['shares']} @ ${position['entry_price']:.2f} "
            f"(Now: ${current_price:.2f}) | PnL: {pnl:+,.2f} ({pnl_pct:+.1f}%){frozen_flag}"
        )
        short_lines.append(line)

    if not long_lines:
        long_lines = ["No long positions"]

    if not short_lines:
        short_lines = ["No short positions"]

    long_chunks = chunk_lines(long_lines, max_length=900)
    short_chunks = chunk_lines(short_lines, max_length=900)

    total_pages = max(1, len(long_chunks), len(short_chunks))

    for page_index in range(total_pages):
        embed = discord.Embed(
            title=f"📈 {target.display_name}'s Portfolio",
            color=discord.Color.gold()
        )

        if page_index == 0:
            embed.add_field(name="Cash", value=f"${cash_balance:,.2f}", inline=True)
            embed.add_field(name="Hedge Fund", value=f"${fund_balance:,.2f}", inline=True)
            embed.add_field(name="Net Worth", value=f"${total_net_worth:,.2f}", inline=True)

        long_value = long_chunks[page_index] if page_index < len(long_chunks) else "—"
        short_value = short_chunks[page_index] if page_index < len(short_chunks) else "—"

        embed.add_field(
            name=f"Long Positions ({page_index + 1}/{len(long_chunks)})",
            value=long_value,
            inline=False
        )

        embed.add_field(
            name=f"Short Positions ({page_index + 1}/{len(short_chunks)})",
            value=short_value,
            inline=False
        )

        embed.set_footer(text=f"Portfolio Page {page_index + 1}/{total_pages}")
        await ctx.send(embed=embed, delete_after=60)

@bot.command(name='pf')
async def pf(ctx, target: discord.Member = None):
    await portfolio_cmd(ctx, target)

@bot.command(name='mp')
async def mp(ctx, target: discord.Member = None):
    await portfolio_cmd(ctx, target or ctx.author)

# ===== COMMANDS: HEDGE FUNDS =====

@bot.command(name='fund')
async def fund(ctx, action: str = None, *args):
    """Manage your hedge fund. Usage: $fund create/info/deposit/withdraw/send_events"""
    if action is None:
        await ctx.send("Usage: $fund create [name], $fund info [@user], $fund deposit <amount>, $fund withdraw <amount>, $fund send_events <amount>", delete_after=30)
        return

    action = action.lower()

    if action == "create":
        user_id = str(ctx.author.id)
        ensure_fund(user_id)

        if args:
            name = " ".join(args)
            funds_data[user_id]["name"] = name
            save_data()
            await ctx.send(f"✅ Hedge fund renamed to: **{name}**", delete_after=30)
        else:
            await ctx.send(f"✅ Hedge fund created: **{funds_data[user_id]['name']}**", delete_after=30)

    elif action == "info":
        if args and ctx.message.mentions:
            target = ctx.message.mentions[0]
        else:
            target = ctx.author

        target_id = str(target.id)
        ensure_fund(target_id)

        fund_obj = funds_data[target_id]
        penalty_apr = get_user_penalty_apr(target_id)
        effective_apy = max(0.0, HEDGE_FUND_BASE_APY - penalty_apr)

        embed = discord.Embed(title=f"🏦 {fund_obj['name']}", color=discord.Color.purple())
        embed.add_field(name="Manager", value=target.mention, inline=True)
        embed.add_field(name="Cash Balance", value=f"${fund_obj['cash_balance']:,.2f}", inline=True)
        embed.add_field(name="Investors", value=str(len(fund_obj['investors'])), inline=True)
        embed.add_field(name="Base APY", value=f"{HEDGE_FUND_BASE_APY*100:.1f}%", inline=True)
        embed.add_field(name="Penalty APR", value=f"{penalty_apr*100:.1f}%", inline=True)
        embed.add_field(name="Effective APY", value=f"{effective_apy*100:.1f}%", inline=True)

        await ctx.send(embed=embed, delete_after=30)

    elif action == "deposit":
        if not args:
            await ctx.send("Usage: $fund deposit <amount>", delete_after=30)
            return
        try:
            amount = float(args[0])
        except ValueError:
            await ctx.send("❌ Invalid amount.", delete_after=30)
            return
        if amount <= 0:
            await ctx.send("❌ Amount must be positive.", delete_after=30)
            return

        user_id = str(ctx.author.id)
        ensure_user(user_id)

        if user_id not in funds_data:
            await ctx.send("❌ You don't have a hedge fund yet! Use `$fund create` first.", delete_after=30)
            return

        if users_data[user_id]["cash_balance"] < amount:
            await ctx.send(f"❌ Insufficient funds! You have ${users_data[user_id]['cash_balance']:,.2f} available.", delete_after=30)
            return

        users_data[user_id]["cash_balance"] -= amount
        funds_data[user_id]["cash_balance"] += amount

        save_data()

        await ctx.send(f"✅ Deposited ${amount:,.2f} into your hedge fund.", delete_after=30)

    elif action == "withdraw":
        if not args:
            await ctx.send("Usage: $fund withdraw <amount>", delete_after=30)
            return
        try:
            amount = float(args[0])
        except ValueError:
            await ctx.send("❌ Invalid amount.", delete_after=30)
            return
        if amount <= 0:
            await ctx.send("❌ Amount must be positive.", delete_after=30)
            return

        user_id = str(ctx.author.id)
        ensure_user(user_id)
        ensure_fund(user_id)

        fund_obj = funds_data[user_id]

        if fund_obj["cash_balance"] < amount:
            await ctx.send(f"❌ Insufficient fund balance! Available: ${fund_obj['cash_balance']:,.2f}.", delete_after=30)
            return

        # Apply early withdrawal penalty logic (unless this is month-end rollover)
        now = datetime.utcnow()
        if now.day != 1:  # treat anything not on the 1st as "early"
            apply_early_withdraw_penalty(user_id)

        fund_obj["cash_balance"] -= amount
        users_data[user_id]["cash_balance"] += amount

        save_data()

        await ctx.send(f"✅ Withdrew ${amount:,.2f} from your hedge fund to your trading account.", delete_after=30)

    elif action == "send_events":
        if not args:
            await ctx.send("Usage: $fund send_events <amount>", delete_after=30)
            return
        try:
            amount = float(args[0])
        except ValueError:
            await ctx.send("❌ Invalid amount.", delete_after=30)
            return
        if amount <= 0:
            await ctx.send("❌ Amount must be positive.", delete_after=30)
            return

        user_id = str(ctx.author.id)
        ensure_user(user_id)
        ensure_fund(user_id)
        ensure_events_wallet()

        fund_obj = funds_data[user_id]
        events_fund = funds_data[EVENTS_WALLET_USER_ID]

        if fund_obj["cash_balance"] < amount:
            await ctx.send(f"❌ Insufficient fund balance! Available: ${fund_obj['cash_balance']:,.2f}.", delete_after=30)
            return

        # Events transfer: no APY penalty
        fund_obj["cash_balance"] -= amount
        events_fund["cash_balance"] += amount

        save_data()

        await ctx.send(f"✅ Sent ${amount:,.2f} from your hedge fund to the Events wallet (no penalty).", delete_after=30)

    else:
        await ctx.send("Unknown action. Use: $fund create/info/deposit/withdraw/send_events", delete_after=30)

# ===== COMMANDS: ENGAGEMENT & LEADERBOARD =====

@bot.command(name='mystats')
async def mystats(ctx):
    """View your weekly activity stats: messages, VC time, and VC pings."""
    user_id = str(ctx.author.id)
    ensure_user(user_id)

    user = users_data[user_id]
    week = user["activity"]["week"]

    text_msgs = week.get("text_msgs", 0) + week.get("media_msgs", 0)
    voice_minutes = week.get("voice_minutes", 0)
    vc_pings = week.get("role_ping_joins", 0)

    hours = int(voice_minutes // 60)
    mins = int(voice_minutes % 60)
    vc_time_str = f"{hours}h {mins}m" if hours > 0 else f"{mins}m"

    embed = discord.Embed(
        title=f"📊 {ctx.author.display_name}'s Weekly Stats",
        color=discord.Color.blue()
    )
    embed.add_field(name="💬 Messages Sent", value=str(text_msgs), inline=True)
    embed.add_field(name="🔊 Time in VC", value=vc_time_str, inline=True)
    embed.add_field(name="📣 VC Pings", value=str(int(vc_pings)), inline=True)

    await ctx.send(embed=embed, delete_after=30)

@bot.command(name='trending')
async def trending(ctx):
    """View the top trending users based on price change and engagement (top 15 up)."""
    user_scores = []

    for user_id in users_data.keys():
        if users_data[user_id].get("opted_out", False):
            continue
        ensure_price(user_id)
        price_pct = get_24h_price_change(user_id)
        current_price = prices_data[user_id]["current"]
        week_score = calculate_trending_score(users_data[user_id]["activity"]["week"])
        norm_eng = math.log10(week_score + 1)
        blended = 0.7 * price_pct + 0.3 * norm_eng

        user_scores.append({
            "user_id": user_id,
            "blended": blended,
            "price": int(current_price),
            "price_pct": int(price_pct)
        })

    user_scores.sort(key=lambda x: x["blended"], reverse=True)

    embed = discord.Embed(title="📈 Trending Tickers", color=discord.Color.gold())

    top_15 = user_scores[:15]
    description = "```\n"
    description += f"{'Rank':<6} {'Name':<18} {'Price':<10} {'24h %':<8}\n"
    description += "-" * 42 + "\n"

    for i, entry in enumerate(top_15, 1):
        member = ctx.guild.get_member(int(entry["user_id"]))
        if member:
            name = member.display_name[:16]
            description += f"{i:<6} {name:<18} ${entry['price']:<9} {entry['price_pct']:+d}%\n"

    description += "```"
    embed.description = description
    await ctx.send(embed=embed, delete_after=30)

@bot.command(name='losers')
async def losers(ctx):
    """View the 15 stocks that have fallen the most from their 24h high."""
    user_scores = []

    for user_id in users_data.keys():
        if users_data[user_id].get("opted_out", False):
            continue

        ensure_price(user_id)
        current_price = prices_data[user_id]["current"]
        dd_pct = get_drawdown_percentage(user_id)

        # Only count if actually below the high
        if dd_pct < 0:
            user_scores.append({
                "user_id": user_id,
                "price": current_price,
                "drawdown": dd_pct  # negative number, e.g. -25.3
            })

    if not user_scores:
        await ctx.send("📉 No stocks are currently below their previous highs.", delete_after=30)
        return

    # Sort by biggest drawdown first (most negative)
    user_scores.sort(key=lambda x: x["drawdown"])

    embed = discord.Embed(
        title="📉 Biggest Losers (from 24h high)",
        color=discord.Color.red()
    )

    bottom_15 = user_scores[:15]

    # Proper code-block with real newlines
    description = "```\n"
    description += f"{'Rank':<4} {'Name':<18} {'Price':<12} {'From 24h High %':<15}\n"
    description += "-" * 52 + "\n"

    for i, entry in enumerate(bottom_15, 1):
        member = ctx.guild.get_member(int(entry["user_id"]))
        if member:
            name = member.display_name[:18]
            dd = entry["drawdown"]
            description += (
                f"{i:<4} {name:<18} "
                f"${entry['price']:<11.2f} "
                f"{dd:>6.1f}%\n"
            )

    description += "```"
    embed.description = description
    await ctx.send(embed=embed, delete_after=45)

@bot.command(name='leaderboard')
async def leaderboard(ctx):
    """View the top 15 users by total net worth."""
    user_scores = []

    for user_id in users_data.keys():
        if users_data[user_id].get("opted_out", False):
            continue

        ensure_user(user_id)
        ensure_fund(user_id)

        net_worth = calculate_net_worth(user_id)
        users_data[user_id]["net_worth"] = net_worth

        user_scores.append({
            "user_id": user_id,
            "net_worth": net_worth
        })

    save_data()

    user_scores.sort(key=lambda x: x["net_worth"], reverse=True)

    embed = discord.Embed(title="💎 Net Worth Leaderboard", color=discord.Color.gold())

    top_15 = user_scores[:15]
    description = "```\\n"
    description += f"{'Rank':<6} {'Name':<20} {'Net Worth':<15}\\n"
    description += "-" * 43 + "\\n"

    for i, entry in enumerate(top_15, 1):
        member = ctx.guild.get_member(int(entry["user_id"]))
        if member:
            name = member.display_name[:18]
            description += f"{i:<6} {name:<20} ${entry['net_worth']:<14,.2f}\\n"

    description += "```"
    embed.description = description
    await ctx.send(embed=embed, delete_after=45)


@bot.command(name='lb')
async def lb(ctx):
    await leaderboard(ctx)
# ===== COMMANDS: OPT OUT / OPT IN =====

@bot.command(name='optout')
async def optout(ctx):
    """Opt out of participating in the stock exchange."""
    user_id = str(ctx.author.id)
    ensure_user(user_id)

    if users_data[user_id].get("opted_out", False):
        await ctx.send("⚠️ You have already opted out of the stock exchange.", delete_after=30)
        return

    users_data[user_id]["opted_out"] = True
    save_data()
    await ctx.send("✅ You have opted out of the stock exchange. You can no longer be purchased, trade stocks, or receive rewards. Your share value will not be listed. Use `$optin` to rejoin.", delete_after=30)

@bot.command(name='optin')
async def optin(ctx):
    """Opt back into participating in the stock exchange."""
    user_id = str(ctx.author.id)
    ensure_user(user_id)

    if not users_data[user_id].get("opted_out", False):
        await ctx.send("⚠️ You are already participating in the stock exchange.", delete_after=30)
        return

    users_data[user_id]["opted_out"] = False
    save_data()
    await ctx.send("✅ Welcome back! You have opted back into the stock exchange. You can now trade, be traded, and receive rewards again.", delete_after=30)

# ===== COMMANDS: HELP =====

@bot.command(name='help')
async def help_command(ctx):
    """Display available commands."""
    embed = discord.Embed(title="📚 Slut Stock xXxchange Commands", color=discord.Color.blue())

    embed.add_field(
        name="💰 Economy",
        value=(
            "$balance / $mb - View your balances\n"
            "$daily - Claim daily reward (500, 1000 on day 7)\n"
        ),
        inline=False
    )

    embed.add_field(
        name="📊 Trading",
        value=(
            "$ticker [@user] / $price - Check stock price\n"
            "$my_stock - Quick view of your stock\n"
            "$buy @user <shares> - Buy shares\n"
            "$sell @user <shares> - Sell shares\n"
            "$short @user <shares> - Short sell\n"
            "$cover @user <shares> - Cover short\n"
            "$portfolio [@user] / $pf / $mp - View portfolio\n"
            "$networth [@user] - View overall networth\n"
        ),
        inline=False
    )

    embed.add_field(
        name="🏦 Hedge Fund",
        value=(
            "$fund create [name] - Create/rename fund\n"
            "$fund deposit <amount> - Deposit to fund\n"
            "$fund info [@user] - View fund details\n"
            "$fund withdraw <amount> - Withdraw to trading\n"
            "$fund send_events <amount> - Send to Events (no penalty)\n"
        ),
        inline=False
    )

    embed.add_field(
        name="📈 Leaderboards",
        value=(
            "$mystats - View your engagement stats\n"
            "$trending - Top trending users\n"
            "$leaderboard / $lb - Top net worth users\n"
            "$losers - Top down-trending users\n"
        ),
        inline=False
    )

    embed.add_field(
        name="🚪 Opt Out / Opt In",
        value=(
            "$optout - Opt out of the stock exchange\n"
            "$optin - Opt back into the stock exchange\n"
        ),
        inline=False
    )

    await ctx.send(embed=embed, delete_after=60)

# ===== BACKGROUND TASKS =====

@tasks.loop(hours=1)
async def monthly_rollover_check():
    """Check if it's time for monthly rollover."""
    now = datetime.utcnow()
    if now.day == 1 and now.hour == 0:
        print("Performing monthly rollover...")

        for user_id in list(users_data.keys()):
            ensure_user(user_id)
            ensure_fund(user_id)

            net_worth = calculate_net_worth(user_id)
            month_start = users_data[user_id]["month_start_net_worth"]
            earnings = max(0, net_worth - month_start)

            funds_data[user_id]["cash_balance"] += earnings

            users_data[user_id]["cash_balance"] = INITIAL_CASH
            users_data[user_id]["net_worth"] = INITIAL_CASH
            users_data[user_id]["month_start_net_worth"] = INITIAL_CASH
            users_data[user_id]["portfolio"]["long"] = {}
            users_data[user_id]["portfolio"]["short"] = {}

            print(f"Rolled over user {user_id}: ${earnings:.2f} to fund")

        save_data()
        print("Monthly rollover complete!")

@tasks.loop(minutes=30)
async def inactivity_price_decay():
    """Apply price decay for inactive users."""
    now = datetime.utcnow()

    for user_id in list(users_data.keys()):
        ensure_user(user_id)
        ensure_price(user_id)

        last_activity = datetime.fromisoformat(users_data[user_id]["last_activity"])
        inactive_seconds = (now - last_activity).total_seconds()

        if inactive_seconds >= INACTIVITY_THRESHOLD:
            blocks = int(inactive_seconds // INACTIVITY_THRESHOLD)

            old_price = prices_data[user_id]["current"]
            new_price = old_price * (INACTIVITY_DECAY ** blocks)
            new_price = max(new_price, MIN_PRICE)

            if new_price != old_price:
                prices_data[user_id]["current"] = new_price
                prices_data[user_id]["low_24h"] = min(prices_data[user_id]["low_24h"], new_price)
                prices_data[user_id]["history"].append({
                    "price": new_price,
                    "timestamp": now.isoformat()
                })

    save_data()

@tasks.loop(minutes=15)
async def short_freeze_check():
    """Freeze short positions older than 30 minutes."""
    now = datetime.utcnow()

    for user_id, user in users_data.items():
        shorts = user["portfolio"]["short"]
        for target_id, position in list(shorts.items()):
            created_at_str = position.get("created_at")
            if not created_at_str:
                position["created_at"] = now.isoformat()
                position.setdefault("frozen", False)
                continue

            try:
                created_at = datetime.fromisoformat(created_at_str)
            except ValueError:
                position["created_at"] = now.isoformat()
                position.setdefault("frozen", False)
                continue

            age_minutes = (now - created_at).total_seconds() / 60
            if age_minutes >= SHORT_FREEZE_MINUTES and not position.get("frozen"):
                position["frozen"] = True

    save_data()

@tasks.loop(minutes=15)
async def activity_price_step():
    """Every 15 minutes, adjust each user's price based on activity."""
    now = datetime.utcnow()
    for user_id in list(users_data.keys()):
        ensure_user(user_id)
        ensure_price(user_id)

        r = compute_activity_return(user_id)
        factor = 1.0 + r / 100.0

        # clamp factor to [0.94, 1.07]
        factor = max(0.94, min(factor, 1.07))

        old_price = prices_data[user_id]["current"]
        new_price = max(MIN_PRICE, old_price * factor)

        prices_data[user_id]["current"] = new_price
        prices_data[user_id]["high_24h"] = max(prices_data[user_id]["high_24h"], new_price)
        prices_data[user_id]["low_24h"] = min(prices_data[user_id]["low_24h"], new_price)
        prices_data[user_id]["all_time_high"] = max(prices_data[user_id].get("all_time_high", new_price), new_price)
        prices_data[user_id]["history"].append({
            "price": new_price,
            "timestamp": now.isoformat()
        })

    save_data()

@tasks.loop(minutes=15)
async def short_liquidation_check():
    """Check and liquidate risky short positions."""
    for user_id in list(users_data.keys()):
        ensure_user(user_id)
        ensure_fund(user_id)

        shorts = users_data[user_id]["portfolio"]["short"].copy()

        for target_id, position in shorts.items():
            ensure_price(target_id)
            current_price = prices_data[target_id]["current"]
            entry_price = position["entry_price"]

            if current_price >= LIQUIDATION_THRESHOLD * entry_price:
                print(f"Liquidating short position: user {user_id}, target {target_id}")

                users_data[user_id]["cash_balance"] += position["locked_cash"]
                funds_data[user_id]["cash_balance"] += position["locked_fund"]

                cost = current_price * position["shares"]

                if users_data[user_id]["cash_balance"] >= cost:
                    users_data[user_id]["cash_balance"] -= cost
                else:
                    remaining = cost - users_data[user_id]["cash_balance"]
                    users_data[user_id]["cash_balance"] = 0
                    funds_data[user_id]["cash_balance"] -= remaining
                    funds_data[user_id]["cash_balance"] = max(0, funds_data[user_id]["cash_balance"])

                del users_data[user_id]["portfolio"]["short"][target_id]
                users_data[user_id]["net_worth"] = calculate_net_worth(user_id)

    save_data()

@tasks.loop(minutes=5)
async def weekly_market_reset():
    """Reset the market every other Monday at 8:00 AM EST (13:00 UTC)."""
    now = datetime.utcnow()
    if now.weekday() != WEEKLY_RESET_DAY or now.hour != WEEKLY_RESET_HOUR_UTC:
        return

    iso_year, iso_week, _ = now.isocalendar()
    
    # Only run on even-numbered weeks (every other Monday)
    if iso_week % 2 != 0:
        return

    # Only trigger once per hour window (avoid re-triggering within the same hour)
    if hasattr(weekly_market_reset, '_last_reset_week'):
        if weekly_market_reset._last_reset_week == (iso_year, iso_week):
            return

    weekly_market_reset._last_reset_week = (iso_year, iso_week)

    print("Performing weekly market reset...")

    for user_id in list(users_data.keys()):
        ensure_user(user_id)
        ensure_price(user_id)

        # Reset stock price to initial
        prices_data[user_id]["current"] = INITIAL_PRICE
        prices_data[user_id]["high_24h"] = INITIAL_PRICE
        prices_data[user_id]["low_24h"] = INITIAL_PRICE
        prices_data[user_id]["history"] = []

        # Reset activity buckets
        reset_activity_bucket(users_data[user_id]["activity"]["today"])
        reset_activity_bucket(users_data[user_id]["activity"]["week"])

        # Reset portfolio (clear all long and short positions)
        users_data[user_id]["portfolio"]["long"] = {}
        users_data[user_id]["portfolio"]["short"] = {}

        # Reset cash balance
        users_data[user_id]["cash_balance"] = INITIAL_CASH
        users_data[user_id]["net_worth"] = INITIAL_CASH
        users_data[user_id]["month_start_net_worth"] = INITIAL_CASH

    save_data()
    print("Weekly market reset complete!")

# ===== RUN BOT =====

if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("ERROR: DISCORD_TOKEN environment variable not set!")
        exit(1)

    bot.run(token)


