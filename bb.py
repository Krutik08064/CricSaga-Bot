# --- Standard Library Imports ---
import os
import random
import json
import logging
import asyncio
import time
import re
import html
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Set, List, DefaultDict, Optional, Union
from collections import defaultdict
from html import escape as html_escape  # Renamed to avoid conflict with custom function
from dataclasses import dataclass
from enum import Enum
from functools import wraps

# --- Third Party Imports ---
import telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery, BotCommandScope
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from telegram.error import BadRequest
from telegram.constants import ParseMode, ChatType
from telegram.helpers import escape_markdown
import psycopg2
from psycopg2 import Error
from psycopg2.extras import DictCursor
from psycopg2.pool import SimpleConnectionPool
from dotenv import load_dotenv
import async_timeout

# --- Initialization & Configuration ---
# Note: DatabaseHandler class is defined below at line ~885

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)
load_dotenv()

# Constants
DATA_DIR = Path("data")
MATCH_HISTORY_FILE = DATA_DIR / "match_history.json"
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
# Fix: Only add BOT_ADMIN if it exists (prevent empty string admin)
BOT_ADMINS: Set[str] = set()
if os.getenv('BOT_ADMIN'):
    BOT_ADMINS.add(os.getenv('BOT_ADMIN'))
games: Dict[str, Dict] = {}

# Required Channels - Users must join these to use the bot
# TEMPORARY: Set to empty to disable force subscription during testing
# TODO: Add bot as admin to channels, then uncomment the lines below
REQUIRED_CHANNELS = {
     'official': '@SagaArenaOfficial',  # Saga Arena | Official
     'community': '@SagaArenaChat'      # Saga Arena • Community
 }
CHANNEL_LINKS = {
    'official': 'https://t.me/SagaArenaOfficial',
    'community': 'https://t.me/SagaArenaChat'
}

# Flood control tracking
user_command_timestamps: DefaultDict[str, List[float]] = defaultdict(list)
FLOOD_LIMIT = 10  # Max commands per window
FLOOD_WINDOW = 60  # 60 seconds

# Add new constants for profile UI
PROFILE_THEMES = {
    'sections': {
        'overview': '🎯',
        'batting': '🏏',
        'bowling': '⚾',
        'achievements': '🏆'
    },
    'stats_icons': {
        'matches': '🎮',
        'wins': '✨',
        'runs': '📊',
        'wickets': '🎯',
        'sixes': '💥',
        'fours': '🔥'
    }
}

UI_THEMES = {
    'primary': {
        'separator': "┏━━━━━━━━━━━━━━━━━━━━━┓",
        'section_sep': "┣━━━━━━━━━━━━━━━━━━━━━┫",
        'footer': "┗━━━━━━━━━━━━━━━━━━━━━┛",
        'bullet': "•",
        'frames': {
            'top': "╔══════════════════════╗",
            'middle': "╠══════════════════════╣",
            'bottom': "╚══════════════════════╝"
        }
    },
    'accents': {
        'match': "🎯",
        'score': "📊",
        'bat': "🏏",
        'ball': "⚾",
        'win': "🏆",
        'stats': "📈",
        'alert': "⚠️",
        'error': "❌",
        'success': "✅"
    },
    'animations': {
        'loading': ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"],
        'progress': ["▰▱▱▱▱", "▰▰▱▱▱", "▰▰▰▱▱", "▰▰▰▰▱", "▰▰▰▰▰"]
    }
}

MESSAGE_STYLES = {
    'game_start': (
        "🎮 *CRICKET SAGA*\n"
        "━━━━━━━━━━━━━━━━\n\n"
        "• *Mode:* {mode}\n"
        "• *Host:* {host}"
    ),
    'match_status': (
        "📊 *LIVE MATCH*\n"
        "━━━━━━━━━━━━━━━━\n\n"
        "• *Score:* {score}/{wickets}\n"
        "• *Overs:* {overs}.{balls}\n"
        "• *Run Rate:* {run_rate:.2f}\n"
        "{target_info}\n\n"
        "{commentary}"
    ),
    'innings_complete': (
        "🏁 *INNINGS COMPLETE*\n"
        "━━━━━━━━━━━━━━━━\n\n"
        "• *Score:* {score}/{wickets}\n"
        "• *Overs:* {overs}\n"
        "• *Run Rate:* {run_rate:.2f}\n"
        "• *Target:* {target}"
    ),
    'match_result': (
        "🏆 *MATCH COMPLETE*\n"
        "━━━━━━━━━━━━━━━━\n\n"
        "• *1st Innings:* {score1}/{wickets1} ({overs1})\n"
        "• *2nd Innings:* {score2}/{wickets2} ({overs2})\n\n"
        "• *Boundaries:* {boundaries} | *Sixes:* {sixes}\n"
        "• *Best Over:* {best_over} runs\n"
        "• *Run Rate:* {run_rate:.2f}\n\n"
        "{result}"
    )
}

# Update GAME_MODES with properly escaped descriptions
GAME_MODES = {
    'classic': {
        'icon': "🏏",
        'title': "CLASSIC MATCH",
        'description': [
            "Traditional gameplay.",
            "Set wickets (1-10) & play until all out."
        ],
        'max_wickets': 10,
        'max_overs': 20,
        'style': 'elegant'
    },
    'quick': {
        'icon': "⚡",
        'title': "QUICK BLITZ",
        'description': [
            "Fast-paced action.",
            "Set overs (1-50) with unlimited wickets."
        ],
        'max_wickets': float('inf'),
        'max_overs': 5,
        'style': 'dynamic'
    },
    'survival': {
        'icon': "🎯",
        'title': "SURVIVAL",
        'description': [
            "The ultimate test.",
            "1 Wicket. Infinite Overs. High Score wins."
        ],
        'max_wickets': 1,
        'max_overs': float('inf'),
        'style': 'intense'
    }
}



# Animation and timing constants
ANIMATION_DELAY = 2.0  # Increased from 1.5
TRANSITION_DELAY = 1.5  # Increased from 1.0
BALL_ANIMATION_DELAY = 3.0  # Increased from 2.5 to prevent rate limits in ranked
BUTTON_COOLDOWN = 2.0
BUTTON_PRESS_COOLDOWN = 3
FLOOD_CONTROL_LIMIT = 24
MAX_RETRIES = 5
RETRY_DELAY = 2.5  # Increased from 2.0
SPLIT_ERROR_DELAY = 0.5
MAX_BUTTON_RETRIES = 2
TURN_WAIT_TIME = 5
FLOOD_WAIT_TIME = 20  # Increased from 15
ERROR_DISPLAY_TIME = 3
RETRY_WAIT_TIME = 5
MAX_AUTO_RETRIES = 3
OVER_BREAK_DELAY = 4.0  # Increased from 3.5
INFINITY_SYMBOL = "∞"
TIMEOUT_RETRY_DELAY = 2.0  # Increased from 1.5
MAX_MESSAGE_RETRIES = 3
MAINTENANCE_MODE = False
BLACKLISTED_USERS = set()

# Game state tracking
last_button_press = {}
user_last_click = {}
user_scorecards = {}
user_action_cooldown = {}  # Track last bat/bowl action time per user
ACTION_COOLDOWN_SECONDS = 3  # 3 second cooldown between bat/bowl actions

# Phase 2: Ranked matchmaking queue tracking
ranked_queue = {}  # {user_id: {'username': str, 'rating': int, 'rank_tier': str, 'joined_at': float, 'message': Message}}
queue_search_tasks = {}  # {user_id: asyncio.Task} - Track active search tasks
RANKED_SEARCH_TIMEOUT = 120  # 2 minutes timeout for queue search
RANKED_RATING_RANGE = 200  # ±200 rating for matchmaking
QUEUE_JOIN_COOLDOWN = 30  # 30 seconds cooldown between queue joins
user_queue_cooldown = {}  # {user_id: timestamp} - Track last queue join time

# ========================================
# ANTI-CHEAT SYSTEM CONSTANTS
# ========================================
# Thresholds for detecting suspicious behavior
SUSPICIOUS_OPPONENT_FREQUENCY = 5  # Matches against same opponent in 24h
SUSPICIOUS_OPPONENT_PERCENTAGE = 0.30  # 30% of total matches with same opponent
WIN_TRADING_CONSECUTIVE_THRESHOLD = 3  # Consecutive matches with alternating wins
MIN_TRUST_SCORE = 30  # Below this, rating gains are reduced
SUSPEND_TRUST_SCORE = 10  # Below this, suspended from ranked
MIN_TELEGRAM_ACCOUNT_AGE_DAYS = 7  # Minimum account age for ranked

# Rating gain multipliers based on total match count (anti-smurf)
RATING_MULTIPLIER_BY_MATCHES = {
    (0, 5): 0.30,      # 30% rating gain for first 5 matches
    (6, 10): 0.50,     # 50% for matches 6-10
    (11, 20): 0.75,    # 75% for matches 11-20
    (21, float('inf')): 1.00  # 100% for 21+ matches
}

# Trust score adjustments
TRUST_SCORE_ADJUSTMENTS = {
    'unique_opponent': 2,          # +2 per unique opponent (max +30)
    'consistent_play': 10,         # +10 for normal play patterns
    'no_flags': 20,                # +20 for clean record
    'alternating_wins': -30,       # -30 for win trading pattern
    'farming_detected': -40,       # -40 for farming new accounts
    'excessive_rematches': -20,    # -20 for too many rematches
    'suspicious_pattern': -25      # -25 for suspicious win/loss pattern
}

# Decorator for blacklist checking
def check_blacklist():
    """Decorator to check if user is blacklisted"""
    def decorator(func):
        @wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user_id = str(update.effective_user.id)
            if user_id in BLACKLISTED_USERS:
                await update.message.reply_text(
                    escape_markdown_v2_custom("❌ You are blacklisted from using this bot."),
                    parse_mode=ParseMode.MARKDOWN_V2
                )
                return
            return await func(update, context)
        return wrapper
    return decorator

# Database configuration
DB_CONFIG = {
    'dbname': os.getenv('DB_NAME', 'postgres'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', '6543')),  # Default to Transaction Mode (was 5432)
    'connect_timeout': 10,  # 10 second connection timeout
    'sslmode': 'require',
    'keepalives': 1,
    'keepalives_idle': 10,  # Send keepalive after 10s idle (was 30s)
    'keepalives_interval': 5,  # Retry keepalive every 5s (was 10s)
    'keepalives_count': 3,  # Give up after 3 failed keepalives (was 5)
    'client_encoding': 'utf8',
    'application_name': 'cricket_bot',
    'options': '-c statement_timeout=30000'  # 30 second query timeout
}

# Add near the top with other constants
# Optimized for Supabase Transaction Mode
DB_POOL_MIN = 10  # Increased from 5
DB_POOL_MAX = 50  # Increased from 20 to handle concurrent requests
CONNECTION_MAX_AGE = 180  # Recycle connections after 3 minutes (was 5)
db_pool = None
last_pool_check = 0

# Admin logging configuration (separate bot for monitoring both CricSaga & Arena of Champions)
ADMIN_LOG_BOT_TOKEN = os.getenv('ADMIN_LOG_BOT_TOKEN', '')  # Separate bot token for logging
ADMIN_LOG_CHAT_ID = os.getenv('ADMIN_LOG_CHAT_ID', '')  # Chat ID to send logs to

# Add this after DB_CONFIG
DB_SCHEMA_VERSION = 2  # For tracking database updates

def init_db_pool():
    """Initialize database connection pool with better error handling"""
    global db_pool
    try:
        if not all([DB_CONFIG['user'], DB_CONFIG['password'], DB_CONFIG['host']]):
            logger.error("Database configuration missing. Please check your .env file")
            return False

        # Log connection attempt
        logger.info(f"Attempting to connect to database at {DB_CONFIG['host']}:{DB_CONFIG['port']}")
        
        # Warn if using Session Mode
        if DB_CONFIG['port'] == 5432:
            logger.warning("⚠️ WARNING: Using Session Mode (port 5432) - Limited to ~15 connections!")
            logger.warning("⚠️ RECOMMENDED: Change DB_PORT to 6543 (Transaction Mode) for 1000+ connections")
        else:
            logger.info(f"✅ Using Transaction Mode (port {DB_CONFIG['port']})")
            
        # Create connection pool with retry logic
        retry_count = 0
        max_retries = 5  # Increased retries
        
        while retry_count < max_retries:
            try:
                db_pool = SimpleConnectionPool(
                    DB_POOL_MIN,
                    DB_POOL_MAX,
                    **DB_CONFIG
                )
                
                # Test the connection
                conn = db_pool.getconn()
                with conn.cursor() as cursor:
                    cursor.execute('SELECT 1')
                db_pool.putconn(conn)
                
                logger.info(f"✅ Database connection pool created successfully ({DB_POOL_MIN}-{DB_POOL_MAX} connections)")
                return True
                
            except Exception as e:
                retry_count += 1
                logger.error(f"Connection attempt {retry_count}/{max_retries} failed: {e}")
                if retry_count < max_retries:
                    wait_time = retry_count * 3  # Exponential backoff: 3, 6, 9, 12 seconds
                    logger.info(f"Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                    continue
                break
                
        logger.error("❌ Failed to create connection pool after all retries")
        return False
        
    except Exception as e:
        logger.error(f"Failed to create connection pool: {e}")
        return False


def check_admin(user_id: str) -> bool:
    """Check if user is an admin - checks database for accuracy"""
    # Quick check in-memory first
    if user_id in BOT_ADMINS:
        return True
    
    # Verify against database for dynamic admin changes
    try:
        conn = get_db_connection()
        if not conn:
            return user_id in BOT_ADMINS  # Fallback to in-memory
        
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) FROM bot_admins 
                WHERE admin_id = %s AND is_active = TRUE
            """, (int(user_id),))
            result = cur.fetchone()
            is_admin = result[0] > 0 if result else False
            
            # Update in-memory cache
            if is_admin:
                BOT_ADMINS.add(user_id)
            
            return is_admin
    except Exception as e:
        logger.error(f"Error checking admin status: {e}")
        return user_id in BOT_ADMINS  # Fallback to in-memory
    finally:
        if conn:
            return_db_connection(conn)


def escape_markdown_v2_custom(text: str) -> str:
    """Escape special characters for Markdown V2 format with custom handling"""
    special_chars = ['_', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        text = text.replace(char, f"\\{char}")
    return text

def format_text(text: str) -> str:
    """Escape special characters for Markdown V2 format"""
    return escape_markdown_v2_custom(text)

def truncate_text(text: str, max_length: int = 30, suffix: str = "...") -> str:
    """Truncate text to max length with ellipsis"""
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix

async def check_connection_health():
    """Periodic health check for database connections"""
    global db, last_pool_check
    
    while True:
        try:
            await asyncio.sleep(60)  # Check every minute
            now = time.time()
            
            # Validate db connection
            if db and not db.check_connection():
                logger.warning("⚠️ Database connection lost, attempting reconnection...")
                db._init_pool()
            
            # Log pool stats every 5 minutes
            if now - last_pool_check > 300:
                last_pool_check = now
                if db and db.pool:
                    logger.info(f"📊 Connection pool health check passed")
                    
        except Exception as e:
            logger.error(f"Error in connection health check: {e}")

async def cleanup_old_games():
    """Periodic cleanup of stale games to prevent memory leaks"""
    while True:
        try:
            await asyncio.sleep(300)  # Run every 5 minutes
            now = time.time()
            stale_games = []
            
            for game_id, game in list(games.items()):
                last_activity = game.get('last_activity', game.get('created_at', now))
                if now - last_activity > 3600:  # Remove games inactive for 1 hour
                    stale_games.append(game_id)
            
            for game_id in stale_games:
                logger.info(f"Cleaning up stale game: {game_id}")
                del games[game_id]
            
            # Also cleanup old queue entries
            for user_id in list(user_queue_cooldown.keys()):
                if now - user_queue_cooldown[user_id] > 600:  # 10 minutes
                    del user_queue_cooldown[user_id]
            
            # Cleanup stale ranked_queue entries (older than 5 minutes)
            stale_queue = []
            for user_id, queue_entry in list(ranked_queue.items()):
                if now - queue_entry.get('joined_at', now) > 300:  # 5 minutes
                    stale_queue.append(user_id)
            
            for user_id in stale_queue:
                logger.info(f"🧹 Cleaning stale ranked queue entry for user {user_id}")
                del ranked_queue[user_id]
                # Also cancel any search tasks
                if user_id in queue_search_tasks:
                    queue_search_tasks[user_id].cancel()
                    del queue_search_tasks[user_id]
            
            # Cleanup old user click tracking
            for user_id in list(user_last_click.keys()):
                if now - user_last_click[user_id] > 600:  # 10 minutes
                    del user_last_click[user_id]
                    
            if stale_games:
                logger.info(f"Cleaned up {len(stale_games)} stale games")
            if stale_queue:
                logger.info(f"Cleaned up {len(stale_queue)} stale queue entries")
                
        except Exception as e:
            logger.error(f"Error in cleanup task: {e}")

def validate_game_state(game: dict) -> tuple[bool, str]:
    """Validate game state integrity with detailed error messages"""
    required_keys = ['chat_id', 'creator', 'status', 'score', 'wickets', 'balls']
    
    for key in required_keys:
        if key not in game:
            return False, f"Missing required key: {key}"
    
    if not isinstance(game['score'], dict):
        return False, "Score must be a dictionary"
    
    if 'innings1' not in game['score'] or 'innings2' not in game['score']:
        return False, "Score missing innings data"
    
    # Validate required fields for active game
    if game.get('status') == 'active':
        required_active = ['mode', 'current_innings', 'max_wickets', 'max_overs']
        for field in required_active:
            if field not in game:
                return False, f"Active game missing required field: {field}"
    
    return True, "Valid"

def check_flood_limit(user_id: str) -> bool:
    """Check if user has exceeded command rate limit"""
    now = time.time()
    timestamps = user_command_timestamps[user_id]
    
    # Remove old timestamps outside the window
    timestamps[:] = [t for t in timestamps if now - t < FLOOD_WINDOW]
    
    # Check if limit exceeded
    if len(timestamps) >= FLOOD_LIMIT:
        return False  # Too many commands
    
    # Add current timestamp
    timestamps.append(now)
    return True  # OK to proceed

def get_db_connection(retry_count=0, max_retries=3):
    """Get a connection from the pool with health check and automatic retry"""
    global db_pool
    
    if db_pool is None:
        logger.warning("Connection pool is None, initializing...")
        if not init_db_pool():
            if retry_count < max_retries:
                logger.info(f"Retry {retry_count + 1}/{max_retries} after pool init failure")
                time.sleep(2 ** retry_count)  # Exponential backoff: 1, 2, 4 seconds
                return get_db_connection(retry_count + 1, max_retries)
            return None
    
    try:
        # Get connection from pool
        conn = db_pool.getconn()
        
        # Test if connection is alive
        try:
            with conn.cursor() as cursor:
                cursor.execute('SELECT 1')
            return conn  # Connection is healthy
            
        except Exception as e:
            # Connection is dead, close it and get a new one
            logger.warning(f"Dead connection detected ({e}), getting new one")
            try:
                conn.close()
            except:
                pass
            
            # Put back bad connection so pool can create new one
            try:
                db_pool.putconn(conn, close=True)
            except:
                pass
            
            # Get fresh connection
            try:
                conn = db_pool.getconn()
                # Test new connection
                with conn.cursor() as cursor:
                    cursor.execute('SELECT 1')
                return conn  # New connection works
                
            except Exception as e2:
                logger.error(f"New connection also failed: {e2}")
                
                # Last resort: Reinitialize entire pool
                try:
                    logger.warning("Recreating entire connection pool...")
                    db_pool.closeall()
                    db_pool = None
                except:
                    pass
                
                if retry_count < max_retries:
                    logger.info(f"Retry {retry_count + 1}/{max_retries} after connection failure")
                    time.sleep(2 ** retry_count)  # Exponential backoff
                    return get_db_connection(retry_count + 1, max_retries)
                
                return None
    
    except Exception as e:
        logger.error(f"Error getting connection from pool: {e}")
        
        # If pool exhausted, force recreation
        if "exhausted" in str(e).lower():
            logger.error("🔴 Pool exhausted! Recreating pool...")
            try:
                if db_pool:
                    db_pool.closeall()
                db_pool = None
            except:
                pass
        
        # Retry on any exception
        if retry_count < max_retries:
            logger.info(f"Retry {retry_count + 1}/{max_retries} after exception")
            time.sleep(2 ** retry_count)
            return get_db_connection(retry_count + 1, max_retries)
        
        logger.error("❌ Failed to get connection after all retries")
        return None

def return_db_connection(conn):
    """Return a connection to the pool"""
    global db_pool
    if db_pool is not None and conn is not None:
        try:
            db_pool.putconn(conn)
        except Exception as e:
            logger.error(f"Error returning connection to pool: {e}")

class DatabaseTransaction:
    """Context manager for database transactions with automatic connection return"""
    def __init__(self):
        self.conn = None
        self.cursor = None
    
    def __enter__(self):
        self.conn = get_db_connection()
        if not self.conn:
            raise Exception("Failed to get database connection")
        self.cursor = self.conn.cursor()
        return self.cursor
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if exc_type is not None:
                # An error occurred, rollback
                if self.conn:
                    self.conn.rollback()
                    logger.error(f"Transaction rolled back due to: {exc_val}")
            else:
                # Success, commit
                if self.conn:
                    self.conn.commit()
        finally:
            # ALWAYS return connection to pool
            if self.conn:
                return_db_connection(self.conn)
        
        # Don't suppress exceptions
        return False

class DatabaseConnection:
    """Context manager for simple database queries with automatic connection return"""
    def __init__(self):
        self.conn = None
    
    def __enter__(self):
        self.conn = get_db_connection()
        if not self.conn:
            raise Exception("Failed to get database connection")
        return self.conn
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        # ALWAYS return connection to pool, even if exception occurred
        if self.conn:
            return_db_connection(self.conn)
        return False  # Don't suppress exceptions

# Add new function to check connection status
def is_connection_alive(connection):
    """Check if PostgreSQL connection is alive"""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            return True
    except (psycopg2.Error, AttributeError):
        return False

async def track_group_membership(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Track when bot is added to or removed from groups.
    Automatically saves group info to database.
    """
    try:
        my_chat_member = update.my_chat_member
        if not my_chat_member:
            return
        
        chat = my_chat_member.chat
        new_status = my_chat_member.new_chat_member.status
        old_status = my_chat_member.old_chat_member.status
        
        # Only track groups and supergroups
        if chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
            return
        
        conn = get_db_connection()
        if not conn:
            return
        
        try:
            with conn.cursor() as cur:
                # Bot was added to group
                if new_status in ['member', 'administrator'] and old_status in ['left', 'kicked']:
                    # Save group to database
                    cur.execute("""
                        INSERT INTO authorized_groups (group_id, group_name, added_by, is_active)
                        VALUES (%s, %s, %s, TRUE)
                        ON CONFLICT (group_id) DO UPDATE
                        SET group_name = EXCLUDED.group_name,
                            is_active = TRUE,
                            added_at = CURRENT_TIMESTAMP
                    """, (chat.id, chat.title or "Unknown Group", my_chat_member.from_user.id))
                    conn.commit()
                    
                    logger.info(f"✅ Bot added to group: {chat.title} (ID: {chat.id})")
                    
                    # Send notification to admin log
                    await send_admin_log(
                        f"🟢 Bot added to group\n"
                        f"Group: {chat.title}\n"
                        f"ID: {chat.id}\n"
                        f"Added by: {my_chat_member.from_user.first_name} (ID: {my_chat_member.from_user.id})",
                        log_type="success",
                        chat_context=f"GC: {chat.title} (ID: {chat.id})"
                    )
                
                # Bot was removed from group
                elif new_status in ['left', 'kicked'] and old_status in ['member', 'administrator']:
                    # Mark group as inactive
                    cur.execute("""
                        UPDATE authorized_groups 
                        SET is_active = FALSE
                        WHERE group_id = %s
                    """, (chat.id,))
                    conn.commit()
                    
                    logger.info(f"❌ Bot removed from group: {chat.title} (ID: {chat.id})")
                    
                    # Send notification to admin log
                    await send_admin_log(
                        f"🔴 Bot removed from group\n"
                        f"Group: {chat.title}\n"
                        f"ID: {chat.id}",
                        log_type="warning",
                        chat_context=f"GC: {chat.title} (ID: {chat.id})"
                    )
        
        finally:
            if conn:
                return_db_connection(conn)
    
    except Exception as e:
        logger.error(f"Error tracking group membership: {e}")

async def auto_save_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Automatically save group info when any message/command is used in it.
    This runs before every command to ensure groups are always tracked.
    """
    try:
        # Only process groups and supergroups
        if not update.effective_chat or update.effective_chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
            return
        
        chat = update.effective_chat
        user = update.effective_user
        
        conn = get_db_connection()
        if not conn:
            return
        
        try:
            with conn.cursor() as cur:
                # Save or update group
                cur.execute("""
                    INSERT INTO authorized_groups (group_id, group_name, added_by, is_active)
                    VALUES (%s, %s, %s, TRUE)
                    ON CONFLICT (group_id) DO UPDATE
                    SET group_name = EXCLUDED.group_name,
                        is_active = TRUE
                    RETURNING (xmax = 0) AS is_new
                """, (chat.id, chat.title or "Unknown Group", user.id if user else 0))
                
                result = cur.fetchone()
                conn.commit()
                
                # Log only when new group is added
                if result and result[0]:
                    logger.info(f"✅ Auto-saved new group: {chat.title} (ID: {chat.id})")
                    await send_admin_log(
                        f"🟢 New group auto-detected\n"
                        f"Group: {chat.title}\n"
                        f"ID: {chat.id}\n"
                        f"First used by: {user.first_name if user else 'Unknown'} (ID: {user.id if user else 'N/A'})",
                        log_type="success",
                        chat_context=f"GC: {chat.title} (ID: {chat.id})"
                    )
        finally:
            if conn:
                return_db_connection(conn)
    
    except Exception as e:
        logger.error(f"Error auto-saving group: {e}")

async def send_admin_log(message: str, log_type: str = "info", chat_context: str = None):
    """Send log message to admin chat via separate logging bot (non-blocking)
    
    Args:
        message: The log message to send
        log_type: Type of log - 'info', 'command', 'error', 'match', 'db_error'
        chat_context: Chat context like "DM" or "GC: -1001234567890" or "GC: Group Name"
    """
    if not ADMIN_LOG_BOT_TOKEN or not ADMIN_LOG_CHAT_ID:
        return  # Logging not configured, skip silently
    
    try:
        import aiohttp
        from datetime import datetime
        
        # Format message with bot name header and timestamp
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        # Choose emoji based on log type
        emoji_map = {
            'info': 'ℹ️',
            'command': '⚡',
            'error': '❌',
            'match': '🏏',
            'db_error': '🔴',
            'success': '✅'
        }
        emoji = emoji_map.get(log_type, 'ℹ️')
        
        # Add chat context if provided
        context_line = f"\n📍 {chat_context}" if chat_context else ""
        
        # Format with clean structure
        formatted_message = (
            f"<b>CricSaga Bot</b>\n"
            f"━━━━━━━━━━━━━━━\n"
            f"{emoji} [{timestamp}] {message}{context_line}"
        )
        
        url = f"https://api.telegram.org/bot{ADMIN_LOG_BOT_TOKEN}/sendMessage"
        payload = {
            'chat_id': ADMIN_LOG_CHAT_ID,
            'text': formatted_message,
            'parse_mode': 'HTML',
            'disable_notification': True  # Silent notifications
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=5)) as response:
                if response.status != 200:
                    logger.debug(f"Admin log failed: {response.status}")
    except Exception as e:
        # Never let logging errors break the bot
        logger.debug(f"Admin log error: {e}")
        pass

def get_chat_context(update: Update) -> str:
    """Get formatted chat context for logging"""
    chat_type = update.effective_chat.type
    if chat_type == 'private':
        return "DM"
    else:
        chat_title = update.effective_chat.title or "Group"
        chat_id = update.effective_chat.id
        return f"GC: {chat_title} ({chat_id})"

# Note: DatabaseHandler class is defined below, initialization happens after class definition

# Add in-memory fallback storage
in_memory_scorecards = []

# Error message templates
ERROR_MESSAGES = {
    'turn_wait': "⏳ *Please wait* {} *seconds for your turn*...",
    'flood_control': "🚫 *Telegram limit reached!* Wait *{}* seconds...",  # Added bold for seconds
    'invalid_turn': "❌ *Not your turn!* It's *{}*'s turn to *{}*",
    'game_state': "⚠️ *Game state error:* *{}*",  # Added bold for error message
    'recovery': "🔄 *Attempting to recover game state*..."
}

# Commentary phrases
COMMENTARY_PHRASES = {
    'wicket': [
        "💥 *BOWLED!* {} *gets the breakthrough!*",
        "🎯 *CLEAN BOWLED!* {} *destroys the stumps!*",
        "⚡ *OUT!* *Masterful bowling by* {}!",
        "🌟 *THAT'S OUT!* {} *celebrates the wicket!*",
        "💫 *DESTROYED!* *Perfect delivery by* {}!",
        "🔥 *INCREDIBLE!* {} *breaks through!*",
        "🎯 *GENIUS!* {} *outsmarts the batsman!*",
        "⚡ *SENSATIONAL!* {} *strikes gold!*",
        "🌟 *WHAT A BALL!* {} *does the trick!*",
        "💫 *BRILLIANT!* {} *gets the breakthrough!*",
        "🎱 *PERFECT DELIVERY!* {} *hits the target!*",
        "🎯 *MASTERCLASS!* {} *shows pure skill!*",
        "⭐ *SPECTACULAR!* {} *makes it happen!*",
        "🔮 *MAGICAL!* {} *weaves their magic!*",
        "💎 *PRECIOUS WICKET!* {} *strikes gold!*"
    ],
    'run_1': [
        "👌 *Good single by* {}",
        "🏃 *Quick running by* {}",
        "✨ *Smart cricket from* {}",
        "🎯 *Well placed by* {}",
        "🎯 *Precise placement by* {}",
        "💫 *Clever running by* {}",
        "🌟 *Good judgment by* {}",
        "⚡ *Sharp single from* {}",
        "✨ *Excellent awareness by* {}",
        "🎭 *Tactical single by* {}",
        "🎪 *Smart cricket from* {}",
        "🎯 *Perfect timing by* {}",
        "🌠 *Calculated single by* {}",
        "⭐ *Well executed by* {}"
    ],
    'run_2': [
        "🏃‍♂️ *Quick double by* {}",
        "⚡ *Good running between wickets by* {}",
        "💫 *Smart cricket from* {}",
        "🎯 *Well played by* {}",
        "🏃‍♂️ *Excellent running by* {}",
        "⚡ *Perfect coordination by* {}",
        "🎯 *Sharp doubles from* {}",
        "💫 *Brilliant running by* {}",
        "✨ *Quick between wickets by* {}",
        "🎭 *Great understanding shown by* {}",
        "🌟 *Perfect judgment by* {}",
        "⭐ *Aggressive running by* {}",
        "🎪 *Fantastic doubles from* {}",
        "🌠 *Professional running by* {}"
    ],
    'run_3': [
        "💪 *Excellent running by* {}",
        "🏃‍♂️ *Great effort for three by* {}",
        "⚡ *Aggressive running by* {}",
        "✨ *Brilliant running between wickets by* {}"
    ],
    'run_4': [
        "🏏 *FOUR!* *Beautiful shot by* {}",
        "⚡ *Cracking boundary by* {}",
        "🎯 *Elegant four from* {}",
        "💫 *Fantastic placement by* {}",
        "✨ *Brilliant shot by* {}",
        "⭐ *Magnificent stroke by* {}",
        "🌟 *Classic boundary by* {}"
    ],
    'run_6': [
        "💥 *MASSIVE SIX!* {} *clears the ropes*",
        "🚀 *HUGE HIT!* {} *goes big*",
        "⚡ *MAXIMUM!* {} *shows the power*",
        "🎆 *SPECTACULAR!* {} *into the crowd*",
        "🎯 *PURE POWER!* {} *launches it*",
        "💫 *WHAT A HIT!* {} *goes downtown*",
        "✨ *HUGE HIT!* {} *makes it look easy*"
    ],
    'over_complete': [
        "🎯 *End of the over!* Time for a bowling change.",
        "⏱️ *That's the over completed!* Teams regrouping.",
        "🔄 *Over completed!* Players taking positions.",
        "📊 *Over finished!* Time for fresh tactics."
    ],
    'innings_end': [
        "🏁 *INNINGS COMPLETE!* What a performance!",
        "🎊 *That's the end of the innings!* Time to switch sides!",
        "🔚 *INNINGS OVER!* Get ready for the chase!",
        "📢 *And that concludes the innings!* Let's see what happens next!"
    ],
    'chase_complete': [
        "🏆 *GAME OVER!* The chase is successful!",
        "🎉 *Victory achieved!* What a chase!",
        "💫 *Target achieved!* Brilliant batting!",
        "🌟 *Chase completed!* Fantastic performance!"
    ],
    'chase_failed': [
        "🎯 *GAME OVER!* The chase falls short!",
        "🏁 *That's it!* Defense wins the day!",
        "🔚 *Chase unsuccessful!* What a bowling performance!",
        "📢 *All over!* The target proves too much!"
    ],
    'run_5': [
        "🔥 *FIVE RUNS!* *Smart cricket by* {}",
        "⭐ *Bonus run taken by* {}",
        "💫 *Extra run grabbed by* {}",
        "✨ *Quick thinking by* {}"
    ]
}

# UI Constants - Centralized separators
UI_SEPARATOR = "━━━━━━━━━━━━━━━━"  # Standard separator (16 chars)
UI_SEPARATOR_LONG = "━━━━━━━━━━━━━━━━━━━━"  # Long separator (20 chars)
MATCH_SEPARATOR = UI_SEPARATOR  # Maintain backward compatibility

# Add near the top with other constants
AUTHORIZED_GROUPS = set()  # Store authorized group IDs
TEST_MODE = False  # Flag to enable/disable group restriction (set True for dev/testing)

# Add these new animation messages
ACTION_MESSAGES = {
    'batting': [
        "🏏 *Power Stance!* {} *takes guard*...",
        "⚡ *Perfect Balance!* {} *ready to face the delivery*...",
        "🎯 *Focused!* {} *watches the bowler intently*...",
        "💫 *Calculating!* {} *reads the field placement*...",
        "✨ *Ready!* {} *grips the bat tightly*...",
        "🎯 *Mental Focus!* {} *visualizes the shot*...",
        "💫 *Perfect Stance!* {} *looks determined*...",
        "🌟 *Battle Ready!* {} *adjusts the gloves*...",
        "⚡ *Game Face!* {} *taps the crease*...",
        "✨ *Pure Focus!* {} *eyes on the bowler*...",
        "🎭 *Alert Mode!* {} *checks the field*...",
        "⭐ *Lightning Ready!* {} *takes center*...",
        "🎪 *Warrior Mode!* {} *marks the guard*...",
        "🌠 *Zen Mode!* {} *deep breath*...",
        "💎 *Power Pose!* {} *ready to face*..."
    ],
    'bowling': [
        "🎯 *Strategic Setup!* {} *marks the run-up*...",
        "⚡ *Perfect Grip!* {} *adjusts the seam position*...",
        "💫 *Building Momentum!* {} *starts the approach*...",
        "🌟 *Full Steam!* {} *charging in to bowl*...",
        "🎭 *Masterful!* {} *about to release*...",
        "🎯 *Perfect Rhythm!* {} *measures the run-up*...",
        "💫 *Focused Attack!* {} *plans the delivery*...",
        "🌟 *Strategic Setup!* {} *checks the field*...",
        "⚡ *Power Stance!* {} *ready to strike*...",
        "✨ *Battle Ready!* {} *eyes the target*...",
        "🎭 *Precision Mode!* {} *adjusts the field*...",
        "⭐ *Strike Ready!* {} *locks the target*...",
        "🎪 *Perfect Setup!* {} *final check*...",
        "🌠 *Attack Mode!* {} *starts the run*...",
        "💎 *Lethal Mode!* {} *ready to deliver*..."
    ],
    'delivery': [
        "⚾ *RELEASE!* The ball flies through the air...",
        "🎯 *BOWLED!* The delivery is on its way...",
        "⚡ *PERFECT!* Beautiful release from the hand...",
        "💫 *INCOMING!* The ball curves through the air...",
        "✨ *BRILLIANT!* What a delivery this could be...",
        "🎯 *PRECISION!* What a delivery path...",
        "💫 *MASTERFUL!* The ball dances in air...",
        "🌟 *PERFECT!* Beautifully executed...",
        "⚡ *LIGHTNING!* The ball zips through...",
        "✨ *MAGICAL!* What a delivery this...",
        "🎭 *BRILLIANT!* The ball curves nicely...",
        "⭐ *STUNNING!* Perfect line and length...",
        "🎪 *AMAZING!* Great trajectory...",
        "🌠 *SUPERB!* The ball moves perfectly...",
        "💎 *CLINICAL!* Excellent execution..."
    ]
}
# Add near other constants
BROADCAST_DELAY = 1  # Delay between messages to avoid flood limits

# Add to constants section
REGISTERED_USERS = set()  # Store registered user IDs

# --- Helper Functions ---
def get_active_game_id(chat_id: int) -> str:
    """Get active game ID for a given chat"""
    for game_id, game in games.items():
        if game.get('chat_id') == chat_id:
            return game_id
    return None

async def check_button_cooldown(msg, user_id: str, text: str, keyboard=None) -> bool:
    """Check if user can click button again"""
    current_time = time.time()
    if user_id in user_last_click:
        time_since_last_click = current_time - user_last_click[user_id]
        if time_since_last_click < BUTTON_COOLDOWN:
            # Cooldown still active - don't update timestamp
            try:
                if keyboard:
                    return await msg.edit_text(
                        text,
                        reply_markup=keyboard
                    )
                return await msg.edit_text(text)
            except Exception as e:
                logger.error(f"Failed to edit message: {e}")
                return None
    
    # Update timestamp - user can proceed
    user_last_click[user_id] = current_time
    return True

async def recover_game_state(game_id: str, chat_id: int) -> bool:
    """Try to recover game state if possible"""
    try :
        if game_id in games:
            game = games[game_id]
            if 'status' not in game:
                game['status'] = 'config'
            if 'score' not in game:
                game['score'] = {'innings1': 0, 'innings2': 0}
            if 'wickets' not in game:
                game['wickets'] = 0
            if 'balls' not in game:
                game['balls'] = 0
            return True
        return False
    except Exception as e:
        logger.error(f"Error recovering game state: {e}")
        return False

def safe_split_callback(data: str, expected_parts: int = 3) -> tuple:
    """Safely split callback data and ensure correct number of parts"""
    parts = data.split('_', expected_parts - 1)
    if len(parts) != expected_parts:
        raise ValueError(f"Invalid callback data format: {data}")
    return tuple(parts)

async def show_error_message(query, message: str, show_alert: bool = True, delete_after: float = None):
    """Show error message to user with optional auto-delete"""
    try:
        await query.answer(message, show_alert=show_alert)
        if delete_after:
            await asyncio.sleep(delete_after)
    except Exception as e:
        logger.error(f"Error showing message: {e}")

def should_end_innings(game: dict) -> bool:
    """Check if innings should end based on wickets or overs"""
    max_wickets = game.get('max_wickets', float('inf'))
    max_overs = game.get('max_overs', float('inf'))
    
    return (
        (max_wickets != float('inf') and game['wickets'] >= max_wickets) or 
        (max_overs != float('inf') and game['balls'] >= max_overs * 6) or
        (game['current_innings'] == 2 and game['score']['innings2'] >= game.get('target', float('inf')))
    )

def store_first_innings(game: dict):
    """Store first innings details before resetting"""
    game['first_innings_wickets'] = game['wickets']
    game['first_innings_score'] = game['score']['innings1']
    game['first_innings_balls'] = game['balls']  # Store balls for proper overs display
    game['first_innings_overs'] = f"{game['balls']//6}.{game['balls']%6}"
    game['target'] = game['score']['innings1'] + 1

def generate_match_summary(game: dict, current_score: int) -> dict:
    """Generate enhanced match summary"""
    try:
        match_id = escape_markdown_v2_custom(game.get('match_id', ''))
        date = escape_markdown_v2_custom(datetime.now().strftime('%d %b %Y'))
        team1 = escape_markdown_v2_custom(game['creator_name'])
        team2 = escape_markdown_v2_custom(game['joiner_name'])
        
        # First innings details
        first_batting = escape_markdown_v2_custom(game['creator_name'])
        first_score = game['first_innings_score']
        first_wickets = game['first_innings_wickets']
        first_overs = game['first_innings_overs']
        first_balls = game.get('first_innings_balls', 0)
        
        # Second innings details
        second_batting = escape_markdown_v2_custom(game['batsman_name'])
        
        # Calculate various statistics
        total_boundaries = game.get('first_innings_boundaries', 0) + game.get('second_innings_boundaries', 0)
        total_sixes = game.get('first_innings_sixes', 0) + game.get('second_innings_sixes', 0)
        dot_balls = game.get('dot_balls', 0)
        best_over = (0, 0)  # Default value
        if game.get('over_scores'):
            best_over = max(game.get('over_scores', {0: 0}).items(), key=lambda x: x[1])
        
        # FIXED: Correct cricket math using balls, not string conversion
        # Convert balls to proper overs: balls_to_overs = balls // 6 + (balls % 6) / 6
        first_overs_float = first_balls / 6 if first_balls > 0 else 0
        second_overs_float = game['balls'] / 6 if game['balls'] > 0 else 0
        total_balls = first_balls + game['balls']
        total_overs_float = total_balls / 6 if total_balls > 0 else 0
        
        return {
            'match_id': match_id,
            'timestamp': date,
            'game_mode': game['mode'],
            'teams': {
                'batting_first': team1,
                'bowling_first': team2
            },
            'innings1': {
                'score': first_score,
                'wickets': first_wickets,
                'overs': first_overs,
                'run_rate': safe_division(first_score, first_overs_float, 0),  # Fixed: ball-based RR
                'boundaries': game.get('first_innings_boundaries', 0),
                'sixes': game.get('first_innings_sixes', 0)
            },
            'innings2': {
                'score': current_score,
                'wickets': game['wickets'],
                'overs': f"{game['balls']//6}.{game['balls']%6}",
                'run_rate': safe_division(current_score, second_overs_float, 0),  # Fixed: ball-based RR
                'boundaries': game.get('second_innings_boundaries', 0),
                'sixes': game.get('second_innings_sixes', 0)
            },
            'stats': {
                'dot_balls': dot_balls,
                'total_boundaries': total_boundaries,
                'average_rr': safe_division(first_score + current_score, total_overs_float, 0),  # Fixed: total balls
                'best_over_runs': best_over[1],
                'best_over_number': best_over[0]
            },
            'winner_id': game['batsman'] if current_score >= game.get('target', float('inf')) else game['bowler'],
            'win_margin': calculate_win_margin(game, current_score),
            'match_result': format_match_result(game, current_score)
        }
    except Exception as e:
        logger.error(f"Error generating match summary: {e}")
        return {
            'stats': {
                'total_boundaries': 0,
                'total_sixes': 0,
                'average_rr': 0,
                'best_over_runs': 0,
                'best_over_number': 0
            }
        }

def calculate_win_margin(game: dict, current_score: int) -> str:
    """Calculate the margin of victory"""
    if game['current_innings'] == 2:
        if current_score >= game.get('target', float('inf')):
            return f"{game['max_wickets'] - game['wickets']} wickets"
        else:
            return f"{game['target'] - current_score - 1} runs"
    return ""

def format_match_result(game: dict, current_score: int) -> str:
    """Format the match result string with proper escaping"""
    if game['score']['innings1'] == game['score']['innings2']:
        return "*Match Drawn\\!*"
    
    winner_name = escape_markdown_v2_custom(
        game['batsman_name'] if current_score >= game.get('target', float('inf')) 
        else game['bowler_name']
    )
    margin = calculate_win_margin(game, current_score)
    return f"*{winner_name} won by {margin}\\!*"

# ========================================
# FORCE SUBSCRIPTION FUNCTIONS
# ========================================

async def check_user_membership(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> tuple[bool, list]:
    """Check if user is a member of all required channels"""
    not_joined = []
    
    for channel_name, channel_username in REQUIRED_CHANNELS.items():
        try:
            member = await context.bot.get_chat_member(channel_username, user_id)
            # Check if user is member, administrator, or creator
            if member.status in ['left', 'kicked']:
                not_joined.append(channel_name)
        except Exception as e:
            logger.error(f"Error checking membership for {channel_username}: {e}")
            not_joined.append(channel_name)
    
    return len(not_joined) == 0, not_joined

def require_subscription(func):
    """Decorator to check if user has joined required channels before executing command"""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        
        # Skip check for admins
        if str(user_id) in BOT_ADMINS:
            return await func(update, context, *args, **kwargs)
        
        # Check membership
        is_member, not_joined = await check_user_membership(user_id, context)
        
        if not is_member:
            keyboard = [
                [
                    InlineKeyboardButton("📢 Join Official Channel", url=CHANNEL_LINKS['official']),
                    InlineKeyboardButton("💬 Join Community", url=CHANNEL_LINKS['community'])
                ],
                [
                    InlineKeyboardButton("✅ I've Joined - Verify", callback_data="verify_subscription")
                ]
            ]
            
            message = (
                "🏏 *Access Required*!\n\n"
                "⚠️ You must join our channels to use this bot:\n\n"
                "📢 *Saga Arena | Official*\n"
                "💬 *Saga Arena • Community*\n\n"
                "After joining, click the verify button below."
            )
            
            if update.message:
                await update.message.reply_text(
                    escape_markdown_v2_custom(message),
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode=ParseMode.MARKDOWN_V2
                )
            elif update.callback_query:
                await update.callback_query.answer("Please join required channels first!", show_alert=True)
                await update.callback_query.message.reply_text(
                    escape_markdown_v2_custom(message),
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode=ParseMode.MARKDOWN_V2
                )
            return
        
        return await func(update, context, *args, **kwargs)
    return wrapper

# Callback handler for subscription verification
async def verify_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the verify subscription button callback"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    is_member, not_joined = await check_user_membership(user_id, context)
    
    if is_member:
        # User has joined both channels - register and show welcome
        user = query.from_user
        
        # Register user
        try:
            if db:
                db.register_user(
                    telegram_id=user.id,
                    username=user.username,
                    first_name=user.first_name
                )
            REGISTERED_USERS.add(str(user.id))
        except Exception as e:
            logger.error(f"Error registering user: {e}")
        
        welcome_message = (
            f"✅ *Verification Successful!*\n\n"
            f"🏏 *WELCOME TO CRICKET SAGA* 🏏\n"
            f"{MATCH_SEPARATOR}\n\n"
            f"✨ Hey {user.first_name}!\n\n"
            f"*Cricket Saga* is an interactive multiplayer cricket game for Telegram.\n"
            f"Play quick matches, compete in ranked games, and track your stats — all inside your chats.\n\n"
            f"🎮 *WHAT YOU CAN DO:*\n"
            f"• Play 1v1 or team matches\n"
            f"• Compete in ranked mode\n"
            f"• Track your career & rankings\n\n"
            f"🚀 *GET STARTED:*\n"
            f"• Use /gameon in a group to start a match\n"
            f"• Use /help to see all commands\n\n"
            f"Ready to play? Add me to a group and type /gameon!"
        )
        
        await query.edit_message_text(
            escape_markdown_v2_custom(welcome_message),
            parse_mode=ParseMode.MARKDOWN_V2
        )
    else:
        # User still hasn't joined
        keyboard = [
            [
                InlineKeyboardButton("📢 Join Official Channel", url=CHANNEL_LINKS['official']),
                InlineKeyboardButton("💬 Join Community", url=CHANNEL_LINKS['community'])
            ],
            [
                InlineKeyboardButton("✅ I've Joined - Verify", callback_data="verify_subscription")
            ]
        ]
        
        channels_text = ""
        if 'official' in not_joined:
            channels_text += "📢 Saga Arena | Official\n"
        if 'community' in not_joined:
            channels_text += "💬 Saga Arena • Community\n"
        
        await query.edit_message_text(
            escape_markdown_v2_custom(
                f"❌ Verification Failed\n\n"
                f"You haven't joined these channels yet:\n\n"
                f"{channels_text}\n"
                f"Please join both channels and click verify again."
            ),
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN_V2
        )

# ========================================
# ANTI-CHEAT DETECTION FUNCTIONS
# ========================================

async def check_telegram_account_age(user) -> tuple[bool, int]:
    """
    Check if user's Telegram account is old enough for ranked play
    Returns: (is_valid, account_age_days)
    """
    try:
        # Telegram doesn't expose exact creation date, but we can use heuristics
        # Users with ID < 10 million are very old accounts (pre-2013)
        # New accounts typically have very high IDs (9+ digits)
        user_id = user.id
        
        # Rough heuristic: older accounts have lower IDs
        # This isn't perfect but provides some protection
        if user_id < 1000000000:  # 9 digits - likely older account
            return True, 999  # Assume old enough
        
        # For newer accounts, we'll track registration date in our database
        conn = get_db_connection()
        if conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT registered_at FROM users WHERE telegram_id::bigint = %s
                """, (user_id,))
                result = cur.fetchone()
                if result and result[0]:
                    # Ensure timezone-aware comparison
                    registered = result[0]
                    if registered.tzinfo is None:
                        registered = registered.replace(tzinfo=timezone.utc)
                    account_age = (datetime.now(timezone.utc) - registered).days
                    return account_age >= MIN_TELEGRAM_ACCOUNT_AGE_DAYS, account_age
        
        # Default: allow but log
        return True, 0
    except Exception as e:
        logger.error(f"Error checking account age: {e}")
        return True, 0  # Allow on error

async def check_match_patterns(player1_id: str, player2_id: str) -> tuple[bool, str, dict]:
    """
    Check if two players have suspicious match patterns
    Returns: (is_suspicious, reason, pattern_data)
    """
    try:
        with DatabaseConnection() as conn:
            with conn.cursor() as cur:
                # Get match pattern between these two players
                cur.execute("""
                    SELECT total_matches, wins, losses, matches_last_24h, last_match_time
                    FROM match_patterns
                    WHERE player_id::bigint = %s AND opponent_id::bigint = %s
                """, (int(player1_id), int(player2_id)))
                
                pattern = cur.fetchone()
                if not pattern:
                    return False, "", {}
                
                total_matches, wins, losses, matches_24h, last_match = pattern
                
                # Check 1: Too many matches in 24 hours
                if matches_24h >= SUSPICIOUS_OPPONENT_FREQUENCY:
                    return True, f"🚨 {matches_24h} matches in 24h", {
                        'total': total_matches,
                        'recent': matches_24h,
                        'wins': wins,
                        'losses': losses
                    }
                
                # Check 2: Too many total matches with same opponent
                # Get player's total match count
                cur.execute("""
                    SELECT total_matches FROM career_stats WHERE user_id::bigint = %s
                """, (int(player1_id),))
                total_user_matches = cur.fetchone()
                if total_user_matches and total_user_matches[0] > 0:
                    opponent_percentage = total_matches / total_user_matches[0]
                    if opponent_percentage >= SUSPICIOUS_OPPONENT_PERCENTAGE and total_matches >= 10:
                        return True, f"🚨 {int(opponent_percentage*100)}% matches vs same opponent", {
                            'total': total_matches,
                            'percentage': opponent_percentage,
                            'wins': wins,
                            'losses': losses
                        }
                
                # Check 3: Suspicious win/loss balance (50-50 split suggests trading)
                if total_matches >= 6:
                    win_rate = wins / total_matches if total_matches > 0 else 0
                    # If win rate is very close to 50%, might be trading
                    if 0.45 <= win_rate <= 0.55 and total_matches >= 10:
                        return True, f"⚖️ Suspicious 50-50 balance ({wins}W-{losses}L)", {
                            'total': total_matches,
                            'wins': wins,
                            'losses': losses,
                            'win_rate': win_rate
                        }
                
                return False, "", {'total': total_matches, 'wins': wins, 'losses': losses}
            
    except Exception as e:
        logger.error(f"Error checking match patterns for {player1_id} vs {player2_id}: {e}", exc_info=True)
        return False, "", {}

async def detect_win_trading(player1_id: str, player2_id: str) -> tuple[bool, str]:
    """
    Analyze recent matches between two players for win trading patterns
    Returns: (is_win_trading, details)
    """
    try:
        conn = get_db_connection()
        if not conn:
            return False, ""
        
        with conn.cursor() as cur:
            # Get last 10 matches between these players
            cur.execute("""
                SELECT winner_id, match_date
                FROM match_history_detailed
                WHERE (player1_id::bigint = %s AND player2_id::bigint = %s)
                   OR (player1_id::bigint = %s AND player2_id::bigint = %s)
                ORDER BY match_date DESC
                LIMIT 10
            """, (int(player1_id), int(player2_id), int(player2_id), int(player1_id)))
            
            matches = cur.fetchall()
            if len(matches) < WIN_TRADING_CONSECUTIVE_THRESHOLD:
                return False, ""
            
            # Check for alternating wins pattern
            alternating_count = 0
            for i in range(len(matches) - 1):
                if matches[i][0] != matches[i+1][0]:
                    alternating_count += 1
                else:
                    alternating_count = 0
                
                if alternating_count >= WIN_TRADING_CONSECUTIVE_THRESHOLD:
                    return True, f"Alternating wins detected ({alternating_count+1} consecutive)"
            
            return False, ""
            
    except Exception as e:
        logger.error(f"Error detecting win trading: {e}")
        return False, ""

async def calculate_trust_score(user_id: str) -> int:
    """
    Calculate user's trust score based on behavior patterns
    Returns: trust_score (0-100)
    """
    try:
        conn = get_db_connection()
        if not conn:
            return 50  # Default
        
        base_score = 50
        adjustments = []
        
        with conn.cursor() as cur:
            # Get user's match statistics
            cur.execute("""
                SELECT total_matches, wins, losses, rating
                FROM career_stats
                WHERE user_id::bigint = %s
            """, (int(user_id),))
            stats = cur.fetchone()
            if not stats:
                return 50
            
            total_matches, wins, losses, rating = stats
            
            # Factor 1: Unique opponents (diversity bonus)
            cur.execute("""
                SELECT COUNT(DISTINCT opponent_id) 
                FROM match_patterns 
                WHERE player_id::bigint = %s
            """, (int(user_id),))
            unique_opponents = cur.fetchone()[0] or 0
            opponent_bonus = min(unique_opponents * TRUST_SCORE_ADJUSTMENTS['unique_opponent'], 30)
            adjustments.append(('Unique opponents', opponent_bonus))
            
            # Factor 2: Check for flagged activities
            cur.execute("""
                SELECT COUNT(*), SUM(trust_score_impact)
                FROM suspicious_activities
                WHERE user_id::bigint = %s AND cleared = FALSE
            """, (int(user_id),))
            flag_result = cur.fetchone()
            if flag_result and flag_result[0] > 0:
                flag_penalty = flag_result[1] or 0
                adjustments.append(('Flagged activities', flag_penalty))
            else:
                # No flags bonus
                adjustments.append(('Clean record', TRUST_SCORE_ADJUSTMENTS['no_flags']))
            
            # Factor 3: Check for suspicious patterns
            cur.execute("""
                SELECT COUNT(*)
                FROM match_patterns
                WHERE player_id::bigint = %s AND is_flagged = TRUE
            """, (int(user_id),))
            flagged_patterns = cur.fetchone()[0] or 0
            if flagged_patterns > 0:
                adjustments.append(('Suspicious patterns', -25 * flagged_patterns))
            
            # Calculate final score
            final_score = base_score + sum(adj[1] for adj in adjustments)
            final_score = max(0, min(100, final_score))  # Clamp between 0-100
            
            # Update in database
            cur.execute("""
                UPDATE career_stats
                SET trust_score = %s
                WHERE user_id::bigint = %s
            """, (final_score, int(user_id)))
            conn.commit()
            
            logger.info(f"Trust score for {user_id}: {final_score} (adjustments: {adjustments})")
            return final_score
            
    except Exception as e:
        logger.error(f"Error calculating trust score: {e}")
        return 50  # Default on error

async def get_rating_multiplier(user_id: str) -> float:
    """
    Get rating multiplier based on user's total match count
    New players get reduced rating impact to prevent smurfing
    """
    try:
        conn = get_db_connection()
        if not conn:
            return 1.0
        
        with conn.cursor() as cur:
            cur.execute("""
                SELECT total_matches FROM career_stats WHERE user_id::bigint = %s
            """, (int(user_id),))
            result = cur.fetchone()
            if not result:
                return 0.30  # New player, 30% multiplier
            
            total_matches = result[0] or 0
            
            # Find appropriate multiplier
            for (min_matches, max_matches), multiplier in RATING_MULTIPLIER_BY_MATCHES.items():
                if min_matches <= total_matches <= max_matches:
                    return multiplier
            
            return 1.0  # Default full multiplier
            
    except Exception as e:
        logger.error(f"Error getting rating multiplier: {e}")
        return 1.0

async def flag_suspicious_activity(user_id: str, activity_type: str, opponent_id: str = None, 
                                   details: str = "", trust_impact: int = 0):
    """
    Log suspicious activity and adjust trust score
    """
    try:
        conn = get_db_connection()
        if not conn:
            return
        
        with conn.cursor() as cur:
            # Insert into suspicious_activities
            cur.execute("""
                INSERT INTO suspicious_activities 
                (user_id, activity_type, opponent_id, details, trust_score_impact)
                VALUES (%s, %s, %s, %s, %s)
            """, (user_id, activity_type, opponent_id, details, trust_impact))
            
            # Update trust score
            cur.execute("""
                UPDATE career_stats
                SET trust_score = GREATEST(0, trust_score + %s),
                    account_flagged = TRUE
                WHERE user_id = %s
            """, (trust_impact, user_id))
            
            conn.commit()
            logger.warning(f"🚨 Flagged activity: {activity_type} by user {user_id}")
            
            # Notify admins
            await notify_admins_suspicious(user_id, activity_type, details, opponent_id)
            
    except Exception as e:
        logger.error(f"Error flagging suspicious activity: {e}")

async def notify_admins_suspicious(user_id: str, activity_type: str, details: str, opponent_id: str = None):
    """
    Notify bot admins about suspicious activity
    NOTE: This function is called from async context, bot instance is available
    """
    try:
        if not BOT_ADMINS:
            return
        
        # Skip notification for now - will be sent via /flaggedmatches
        # To enable, pass bot instance through context or store globally
        logger.warning(f"🚨 Suspicious activity flagged: {activity_type} by {user_id} vs {opponent_id}")
        logger.warning(f"Details: {details}")
        
        # Admins can review via /flaggedmatches command
                
    except Exception as e:
        logger.error(f"Error notifying admins: {e}")

async def record_match_detailed(game: dict, winner_id: str, match_type: str = 'ranked'):
    """
    Record match in detailed history for pattern analysis
    """
    try:
        conn = get_db_connection()
        if not conn:
            return
        
        game_id = game.get('id', f"{game['creator']}_{game.get('joiner', 'unknown')}")
        player1_id = game['creator']
        player2_id = game.get('joiner', '')
        
        # Calculate match duration
        match_duration = int(time.time() - game.get('start_time', time.time()))
        total_balls = game.get('balls', 0) + game.get('first_innings_balls', 0)
        
        # Get rating changes
        rating_change_p1 = game.get('p1_rating_change', 0)
        rating_change_p2 = game.get('p2_rating_change', 0)
        
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO match_history_detailed
                (match_id, player1_id, player2_id, winner_id, match_type,
                 rating_change_p1, rating_change_p2, match_duration, total_balls)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (match_id) DO NOTHING
            """, (game_id, player1_id, player2_id, winner_id, match_type,
                  rating_change_p1, rating_change_p2, match_duration, total_balls))
            conn.commit()
            
    except Exception as e:
        logger.error(f"Error recording match details: {e}")

# --- Database Handler Class ---
class DatabaseHandler:
    def __init__(self):
        self.pool = None
        try:
            self._init_pool()
            if not self._verify_tables():
                self._init_tables()
            self.load_registered_users()
        except Exception as e:
            logger.error(f"❌ CRITICAL: Failed to initialize database: {e}")
            logger.error("Please check your database configuration:")
            logger.error("- Ensure DB_PORT is 6543 (Transaction Mode), not 5432 (Session Mode)")
            logger.error("- Verify DATABASE_URL or DB_HOST/DB_USER/DB_PASSWORD are correct")
            logger.error("- Check Supabase connection pooler is enabled")
            raise SystemExit(1)  # Exit immediately with error code

    def load_registered_users(self):
        """Load registered users from database into memory"""
        global REGISTERED_USERS
        try:
            conn = self.get_connection()
            if not conn:
                return
                
            with conn.cursor() as cur:
                cur.execute("SELECT telegram_id FROM users")
                users = cur.fetchall()
                for user in users:
                    REGISTERED_USERS.add(str(user[0]))
                logger.info(f"Loaded {len(REGISTERED_USERS)} registered users from database")
        except Exception as e:
            logger.error(f"Error loading registered users: {e}")
        finally:
            if conn:
                self.return_connection(conn)

    def _init_pool(self) -> bool:
        """Initialize connection pool with proper error handling"""
        try:
            if not all([DB_CONFIG['user'], DB_CONFIG['password'], DB_CONFIG['host']]):
                logger.error("Database configuration missing. Check your .env file")
                return False
                
            # Create connection pool with retry logic
            retry_count = 0
            max_retries = 3
            
            while retry_count < max_retries:
                try:
                    self.pool = SimpleConnectionPool(
                        DB_POOL_MIN,
                        DB_POOL_MAX,
                        **DB_CONFIG
                    )
                    
                    # Test the connection
                    test_conn = self.pool.getconn()
                    with test_conn.cursor() as cur:
                        cur.execute('SELECT 1')
                    self.pool.putconn(test_conn)
                    
                    logger.info("Database pool created successfully")
                    return True
                    
                except Exception as e:
                    retry_count += 1
                    logger.error(f"Connection attempt {retry_count} failed: {e}")
                    if retry_count < max_retries:
                        time.sleep(5)  # Wait 5 seconds before retrying
                        continue
                    break
                    
            logger.error("Failed to create connection pool after all retries")
            return False
            
        except Exception as e:
            logger.error(f"Failed to create connection pool: {e}")
            self.pool = None
            return False

    def check_connection(self) -> bool:
        """Test database connection"""
        if not self.pool:
            return False
            
        try:
            # Get a connection from the pool
            conn = self.pool.getconn()
            try:
                # Test the connection
                with conn.cursor() as cur:
                    cur.execute('SELECT 1')
                    cur.fetchone()
                return True
            finally:
                # Always return the connection to the pool
                self.pool.putconn(conn)
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False

    def get_connection(self) -> Optional[psycopg2.extensions.connection]:
        """Get a connection from the pool"""
        try:
            if not self.pool:
                if not self._init_pool():
                    return None
            return self.pool.getconn()
        except Exception as e:
            logger.error(f"Error getting connection: {e}")
            return None

    def return_connection(self, conn: psycopg2.extensions.connection):
        """Return a connection to the pool"""
        if self.pool:
            self.pool.putconn(conn)

    def close(self):
        """Close all database connections"""
        if self.pool:
            self.pool.closeall()
            self.pool = None

    def register_user(self, telegram_id: int, username: str = None, first_name: str = None) -> bool:
        """Register a new user or update existing user"""
        try:
            conn = self.get_connection()
            if not conn:
                return False
                
            try:
                with conn.cursor() as cur:
                    # First make sure the users table exists
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS users (
                            telegram_id BIGINT PRIMARY KEY,
                            username VARCHAR(255),
                            first_name VARCHAR(255),
                            registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    """)

                    # Insert or update user
                    cur.execute("""
                        INSERT INTO users (telegram_id, username, first_name, last_active)
                        VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                        ON CONFLICT (telegram_id) 
                        DO UPDATE SET 
                            username = EXCLUDED.username,
                            first_name = EXCLUDED.first_name,
                            last_active = CURRENT_TIMESTAMP
                        RETURNING telegram_id
                    """, (telegram_id, username, first_name))
                    conn.commit()
                    
                    # Add to in-memory set
                    REGISTERED_USERS.add(str(telegram_id))
                    return True
            finally:
                self.return_connection(conn)
                
        except Exception as e:
            logger.error(f"Error registering user: {e}")
            return False

    def log_command(self, telegram_id: int, command: str, chat_type: str, success: bool = True, error_message: str = None) -> bool:
        """Log command usage"""
        try:
            # Validate telegram_id is not None
            if telegram_id is None:
                logger.error("Cannot log command: telegram_id is None")
                return False
                
            conn = self.get_connection()
            if not conn:
                return False
                
            try:
                with conn.cursor() as cur:
                    # First make sure the command_logs table exists
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS command_logs (
                            id SERIAL PRIMARY KEY,
                            telegram_id BIGINT,
                            command VARCHAR(50),
                            chat_type VARCHAR(20),
                            success BOOLEAN DEFAULT TRUE,
                            error_message TEXT,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            FOREIGN KEY (telegram_id) REFERENCES users(telegram_id) ON DELETE CASCADE
                        )
                    """)

                    # Ensure user exists before logging (auto-register if needed)
                    cur.execute("""
                        INSERT INTO users (telegram_id, username, first_name, registered_at)
                        VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                        ON CONFLICT (telegram_id) DO NOTHING
                    """, (int(telegram_id), 'Unknown', 'Unknown'))

                    # Log the command
                    cur.execute("""
                        INSERT INTO command_logs 
                        (telegram_id, command, chat_type, success, error_message, created_at)
                        VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    """, (int(telegram_id), command, chat_type, success, error_message))
                    conn.commit()
                    return True
            finally:
                self.return_connection(conn)
                
        except Exception as e:
            logger.error(f"Error logging command: {e}")
            return False

    async def save_match_async(self, match_data: dict) -> bool:
        """Async version of save match with proper error handling"""
        try:
            connection = self.get_connection()
            if not connection:
                return False

            match_summary = {
                'match_id': match_data.get('match_id'),
                'user_id': match_data.get('user_id'),
                'game_mode': match_data.get('mode', 'classic'),
                'timestamp': datetime.now().isoformat(),
                'teams': {
                    'team1': match_data.get('creator_name', ''),
                    'team2': match_data.get('joiner_name', '')
                },
                'innings': {
                    'first': match_data.get('first_innings_score', 0),
                    'second': match_data.get('score', {}).get('innings2', 0)
                },
                'result': match_data.get('result', ''),
                'stats': {
                    'boundaries': match_data.get('boundaries', 0),
                    'sixes': match_data.get('sixes', 0),
                    'dot_balls': match_data.get('dot_balls', 0),
                    'best_over': match_data.get('best_over', 0)
                }
            }

            with connection.cursor() as cur:
                # Ensure user exists first
                cur.execute("""
                    INSERT INTO users (telegram_id, first_name)
                    VALUES (%s, %s)
                    ON CONFLICT (telegram_id) DO NOTHING
                """, (match_data.get('user_id'), match_data.get('user_name', 'Unknown')))

                # Fixed INSERT statement that matches table structure
                cur.execute("""
                    INSERT INTO scorecards 
                    (match_id, user_id, game_mode, match_data)
                    VALUES (%s, %s, %s, %s::jsonb)
                    ON CONFLICT (match_id) 
                    DO UPDATE SET
                        match_data = EXCLUDED.match_data,
                        game_mode = EXCLUDED.game_mode
                """, (
                    match_summary['match_id'],
                    match_summary['user_id'],
                    match_summary['game_mode'],
                    json.dumps(match_summary)
                ))

                connection.commit()
                return True

        except Exception as e:
            logger.error(f"Database save error: {e}")
            if connection:
                connection.rollback()
            return False
        finally:
            if connection:
                self.return_connection(connection)

    def get_user_matches(self, user_id: str, limit: int = 10) -> list:
        """Get user's match history"""
        try:
            conn = self.get_connection()
            if not conn:
                return []
                
            try:
                with conn.cursor() as cur:
                    # Use match_data instead of direct columns
                    cur.execute("""
                        SELECT 
                            match_id,
                            match_data->>'timestamp' as timestamp,
                            match_data->>'teams' as teams,
                            match_data->>'innings1' as innings1,
                            match_data->>'innings2' as innings2,
                            match_data->>'result' as result
                        FROM scorecards 
                        WHERE user_id = %s
                        ORDER BY created_at DESC
                        LIMIT %s
                    """, (user_id, limit))
                    
                    matches = []
                    for row in cur.fetchall():
                        match_data = row[1] if row[1] else {}
                        matches.append({
                            'match_id': row[0],
                            'timestamp': row[1],
                            'teams': row[2],
                            'innings1': row[3],
                            'innings2': row[4],
                            'result': row[5]
                        })
                    return matches
            finally:
                self.return_connection(conn)
                
        except Exception as e:
            logger.error(f"Error getting user matches: {e}")
            return []
    def _init_tables(self) -> bool:
        """Initialize database tables with all required columns"""
        try:
            conn = self.get_connection()
            if not conn:
                return False

            with conn.cursor() as cur:
                # Create schema version table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS schema_version (
                        version INTEGER PRIMARY KEY
                    );

                    -- Update users table with ban functionality
                    ALTER TABLE users 
                    ADD COLUMN IF NOT EXISTS is_banned BOOLEAN DEFAULT FALSE,
                    ADD COLUMN IF NOT EXISTS ban_reason TEXT,
                    ADD COLUMN IF NOT EXISTS banned_at TIMESTAMP,
                    ADD COLUMN IF NOT EXISTS banned_by BIGINT;

                    -- Update player_stats table with enhanced stats
                    DROP TABLE IF EXISTS player_stats;
                    CREATE TABLE player_stats (
                        user_id BIGINT PRIMARY KEY REFERENCES users(telegram_id),
                        matches_played INTEGER DEFAULT 0,
                        matches_won INTEGER DEFAULT 0,
                        total_runs INTEGER DEFAULT 0,
                        total_wickets INTEGER DEFAULT 0,
                        highest_score INTEGER DEFAULT 0,
                        best_bowling VARCHAR(20),
                        total_fours INTEGER DEFAULT 0,
                        total_sixes INTEGER DEFAULT 0,
                        fifties INTEGER DEFAULT 0,
                        hundreds INTEGER DEFAULT 0,
                        average DECIMAL(10,2) DEFAULT 0,
                        strike_rate DECIMAL(10,2) DEFAULT 0,
                        last_five_scores TEXT DEFAULT '[]',
                        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );

                    -- Create ranked_queue table for Phase 2 matchmaking
                    CREATE TABLE IF NOT EXISTS ranked_queue (
                        user_id BIGINT PRIMARY KEY,
                        username TEXT NOT NULL,
                        rating INTEGER NOT NULL,
                        rank_tier TEXT NOT NULL,
                        joined_at TIMESTAMP DEFAULT NOW(),
                        searching_since TIMESTAMP DEFAULT NOW()
                    );

                    -- Update schema version
                    INSERT INTO schema_version (version) 
                    VALUES (2) 
                    ON CONFLICT (version) DO UPDATE SET version = 2;
                """)
                conn.commit()
                return True
                
        except Exception as e:
            logger.error(f"Error initializing tables: {e}")
            if conn:
                conn.rollback()
            return False
        finally:
            if conn:
                self.return_connection(conn)

    def save_match(self, match_data: dict) -> bool:
        """Save match with proper error handling"""
        try:
            conn = self.get_connection()
            if not conn:
                return False

            with conn.cursor() as cur:
                # Ensure user exists first
                cur.execute("""
                    INSERT INTO users (telegram_id, first_name)
                    VALUES (%s, %s)
                    ON CONFLICT (telegram_id) DO NOTHING
                """, (match_data['user_id'], match_data.get('user_name', 'Unknown')))

                # Fixed INSERT statement for regular save
                cur.execute("""
                    INSERT INTO scorecards 
                    (match_id, user_id, game_mode, match_data)
                    VALUES (%s, %s, %s, %s::jsonb)
                    ON CONFLICT (match_id) 
                    DO UPDATE SET
                        match_data = EXCLUDED.match_data,
                        game_mode = EXCLUDED.game_mode,
                        created_at = CURRENT_TIMESTAMP
                """, (
                    match_data['match_id'],
                    match_data['user_id'],
                    match_data.get('game_mode', 'classic'),
                    json.dumps(match_data)
                ))

                conn.commit()
                return True

        except Exception as e:
            logger.error(f"Database save error: {e}")
            if conn:
                conn.rollback()
            return False
        finally:
            if conn:
                self.return_connection(conn)

    def _verify_tables(self) -> bool:
        """Check if required tables exist"""
        try:
            conn = self.get_connection()
            if not conn:
                return False

            with conn.cursor() as cur:
                cur.execute("""
                    SELECT COUNT(*) FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name IN ('users', 'scorecards');
                """)
                count = cur.fetchone()[0]
                return count == 2

        except Exception as e:
            logger.error(f"Error verifying tables: {e}")
            return False
        finally:
            if conn:
                self.return_connection(conn)

    def get_bot_stats(self) -> dict:
        """Get bot statistics"""
        try:
            conn = self.get_connection()
            if not conn:
                return {}
                
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT total_users, total_games_played, active_games, total_commands_used, uptime_start, last_updated
                    FROM bot_stats
                    ORDER BY last_updated DESC
                    LIMIT 1
                """)
                
                stats = cur.fetchone()
                if stats:
                    return {
                        'total_users': stats[0],
                        'total_games_played': stats[1],
                        'active_games': stats[2],
                        'total_commands_used': stats[3],
                        'uptime_start': stats[4],
                        'last_updated': stats[5]
                    }
                return {}
        except Exception as e:
            logger.error(f"Error getting bot stats: {e}")
            return {}
        finally:
            if conn:
                self.return_connection(conn)

    def get_authorized_groups(self) -> list:
        """Get all authorized groups"""
        try:
            conn = self.get_connection()
            if not conn:
                return []
                
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT group_id, group_name, added_by, added_at, is_active
                    FROM authorized_groups
                    WHERE is_active = TRUE
                """)
                
                groups = cur.fetchall()
                return [
                    {
                        'group_id': group[0],
                        'group_name': group[1],
                        'added_by': group[2],
                        'added_at': group[3],
                        'is_active': group[4]
                    }
                    for group in groups
                ]
        except Exception as e:
            logger.error(f"Error getting authorized groups: {e}")
            return []
        finally:
            if conn:
                self.return_connection(conn)

    def get_admins(self) -> list:
        """Get all bot admins"""
        try:
            conn = self.get_connection()
            if not conn:
                return []
                
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT admin_id, added_by, added_at, is_super_admin
                    FROM bot_admins
                """)
                
                admins = cur.fetchall()
                return [
                    {
                        'admin_id': admin[0],
                        'added_by': admin[1],
                        'added_at': admin[2],
                        'is_super_admin': admin[3]
                    }
                    for admin in admins
                ]
        except Exception as e:
            logger.error(f"Error getting admins: {e}")
            return []
        finally:
            if conn:
                self.return_connection(conn)

    def add_admin(self, admin_id: int, added_by: int, is_super_admin: bool = False) -> bool:
        """Add a new admin"""
        try:
            conn = self.get_connection()
            if not conn:
                return False
                
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO bot_admins (admin_id, added_by, is_super_admin)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (admin_id) DO NOTHING
                """, (admin_id, added_by, is_super_admin))
                
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error adding admin: {e}")
            if conn:
                conn.rollback()
            return False
        finally:
            if conn:
                self.return_connection(conn)

    def remove_admin(self, admin_id: int) -> bool:
        """Remove an admin"""
        try:
            conn = self.get_connection()
            if not conn:
                return False
                
            with conn.cursor() as cur:
                cur.execute("""
                    DELETE FROM bot_admins
                    WHERE admin_id = %s
                """, (admin_id,))
                
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error removing admin: {e}")
            if conn:
                conn.rollback()
            return False
        finally:
            if conn:
                self.return_connection(conn)

    def add_group(self, group_id: int, group_name: str, added_by: int) -> bool:
        """Add a new authorized group"""
        try:
            conn = self.get_connection()
            if not conn:
                return False
                
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO authorized_groups (group_id, group_name, added_by)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (group_id) DO NOTHING
                """, (group_id, group_name, added_by))
                
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error adding group: {e}")
            if conn:
                conn.rollback()
            return False
        finally:
            if conn:
                self.return_connection(conn)

    def remove_group(self, group_id: int) -> bool:
        """Remove an authorized group"""
        try:
            conn = self.get_connection()
            if not conn:
                return False
                
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE authorized_groups
                    SET is_active = FALSE
                    WHERE group_id = %s
                """, (group_id,))
                
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error removing group: {e}")
            if conn:
                conn.rollback()
            return False
        finally:
            if conn:
                self.return_connection(conn)

# Initialize database connection after class definition
db = DatabaseHandler()  # Create an instance of DatabaseHandler
if not db.check_connection():  # Check if the connection is successful
    logger.error("Database connection failed!")
    exit(1)  # Exit if the connection fails

# Update the database initialization to use telegram_id instead of user_id
def init_database():
    """Initialize database tables if they don't exist"""
    connection = get_db_connection()
    if not connection:
        logger.error("Could not connect to database for initialization")
        return False
        
    try:
        with connection.cursor() as cursor:
            # Read and execute the SQL file
            sql_file_path = Path(__file__).parent / "SETUP.sql"
            if not sql_file_path.exists():
                logger.error("setup_database.sql file not found")
                return False
                
            with open(sql_file_path, 'r') as sql_file:
                # Remove any comments and empty lines
                sql_commands = []
                for line in sql_file:
                    line = line.strip()
                    if line and not line.startswith('--'):
                        sql_commands.append(line)
                
                # Join commands and split by semicolon
                sql_script = ' '.join(sql_commands)
                commands = [cmd.strip() for cmd in sql_script.split(';') if cmd.strip()]
                
                # Execute each command separately
                for command in commands:
                    try:
                        cursor.execute(command)
                    except psycopg2.Error as e:
                        logger.error(f"Error executing SQL command: {e}")
                        logger.error(f"Failed command: {command}")
                        connection.rollback()
                        return False
                        
            connection.commit()
            logger.info("Database initialized successfully")
            return True
            
    except Exception as e:
        logger.error(f"Database initialization error: {e}")
        if connection:
            connection.rollback()
        return False
    finally:
        if connection:
            return_db_connection(connection)

# --- Game Commands ---
def is_registered(user_id: str) -> bool:
    """Check if user is registered"""
    return user_id in REGISTERED_USERS

@require_subscription
@check_blacklist()
async def gameon(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if check_maintenance(update):
        await update.message.reply_text(
            escape_markdown_v2_custom(
                "🛠️ *Bot is currently under maintenance*\n"
                "Please try again later."
            ),
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return
    try:
        user_id = str(update.effective_user.id)
        
        # Flood control check
        if not check_flood_limit(user_id):
            await update.message.reply_text(
                escape_markdown_v2_custom(
                    f"{UI_THEMES['accents']['error']} ⏱️ You're sending commands too fast!\n"
                    f"Please wait a moment before trying again."
                ),
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return
        
        logger.info(f"User {update.effective_user.id} initiated game")
        db.log_command(
            telegram_id=update.effective_user.id,
            command="gameon",
            chat_type=update.effective_chat.type
        )
        
        if not is_registered(user_id):
            await update.message.reply_text(
                escape_markdown_v2_custom(f"{UI_THEMES['accents']['error']} You need to register first!\nSend /start to me in private chat to register."),
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return

        if update.effective_chat.type == ChatType.PRIVATE:
            await update.message.reply_text(
                escape_markdown_v2_custom(f"{UI_THEMES['accents']['error']} Please add me to a group to play!"),
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return

        # Store the creator's ID in the callback data
        keyboard = [
            [InlineKeyboardButton("🏏 Player vs Player", callback_data=f"matchtype_pvp_{user_id}")],
            [InlineKeyboardButton("👥 Team vs Team", callback_data=f"matchtype_team_{user_id}")]
        ]

        await update.message.reply_text(
            "🏟️  *CRICKET SAGA ARENA*\n"
            "══════════════════════\n\n"
            "⚔️ *PLAYER VS PLAYER*\n"
            "Challenge a friend to a 1v1 duel.\n\n"
            "👥 *TEAM BATTLE*\n"
            "Squad play. Captains lead the charge.\n\n"
            "👇 *Choose match type:*",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN_V2
        )

    except Exception as e:
        logger.error(f"Error in gameon: {e}")
        db.log_command(
            telegram_id=update.effective_user.id,
            command="gameon",
            chat_type=update.effective_chat.type,
            success=False,
            error_message=str(e)
        )
        raise

# --- Game State Management ---
# Add this new helper function near the top
def generate_match_id() -> str:
    """Generate a unique match ID with millisecond precision"""
    # Use milliseconds to prevent collision if two games start in same second
    timestamp_ms = int(time.time() * 1000)
    random_num = random.randint(100, 999)
    return f"M{timestamp_ms}{random_num}"

# Update create_game function
def create_game(creator_id: str, creator_name: str, chat_id: int) -> str:
    """Create a new game with proper initialization and validation"""
    # Check for existing active game in this chat
    existing_game_id = get_active_game_id(chat_id)
    if existing_game_id:
        logger.warning(f"Active game {existing_game_id} already exists in chat {chat_id}")
        # Clean up if game is stale (older than 1 hour)
        existing_game = games.get(existing_game_id)
        if existing_game:
            created_at = existing_game.get('created_at', time.time())
            if time.time() - created_at > 3600:  # 1 hour
                logger.info(f"Cleaning up stale game {existing_game_id}")
                del games[existing_game_id]
            else:
                raise Exception(f"Active game already exists in this chat. Game ID: {existing_game_id}")
    
    # Generate unique game ID using chat_id and timestamp for better uniqueness
    game_id = f"{abs(chat_id)}_{int(time.time() * 1000) % 1000000}"
    # Fallback to ensure uniqueness if somehow collision occurs
    while game_id in games:
        game_id = f"{abs(chat_id)}_{int(time.time() * 1000) % 1000000}_{random.randint(0, 99)}"
        
    games[game_id] = {
        'chat_id': chat_id,
        'creator': creator_id,
        'creator_name': truncate_text(creator_name, 25),  # Prevent UI overflow
        'status': 'config',
        'score': {'innings1': 0, 'innings2': 0},
        'wickets': 0,
        'balls': 0,
        'current_innings': 1,
        'this_over': [],
        'match_id': generate_match_id(),
        'first_innings_boundaries': 0,
        'first_innings_sixes': 0,
        'second_innings_boundaries': 0,
        'second_innings_sixes': 0,
        'over_scores': {},
        'dot_balls': 0,
        'created_at': time.time(),  # Track game creation time
        'last_activity': time.time(),  # Track last activity for cleanup
        'batsman_ready': False  # Initialize batsman ready flag
    }
    
    logger.info(f"✅ Created game {game_id} in chat {chat_id}")
    return game_id

# --- Game Mechanics ---
# Update handle_mode for better classic mode setup
async def handle_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = str(query.from_user.id)
    
    try:
        await query.answer()
    except Exception:
        pass  # Query too old, continue anyway
    
    try:
        # Parse callback_data: "mode_{game_id}_{mode}_{creator_id}" or "mode_{game_id}_{mode}"
        parts = query.data.split('_')
        mode = parts[-2] if len(parts) > 3 else parts[-1]
        creator_id_from_data = parts[-1] if len(parts) > 3 else None
        game_id = '_'.join(parts[1:-2]) if len(parts) > 3 else '_'.join(parts[1:-1])
        
        if game_id not in games:
            await query.edit_message_text(
                escape_markdown_v2_custom("❌ Game not found!"),
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return
            
        game = games[game_id]
        
        # Only game creator can configure settings
        if user_id != game['creator']:
            try:
                await query.answer(
                    "⚠️ You are not the host! Only the game creator can configure settings.",
                    show_alert=True
                )
            except Exception:
                pass
            return
        game['mode'] = mode
        game['status'] = 'setup'
        game['current_innings'] = 1
        game['score'] = {'innings1': 0, 'innings2': 0}
        game['wickets'] = 0
        game['balls'] = 0
        game['this_over'] = []
        
        if mode == 'survival':
            game['max_wickets'] = 1
            game['max_overs'] = float('inf')
            keyboard = [[InlineKeyboardButton("🤝 Join Game", callback_data=f"join_{game_id}")]]
            mode_info = "🎯 Survival Mode (1 wicket)"
        elif mode == 'quick':
            game['max_wickets'] = float('inf')
            keyboard = get_overs_keyboard(game_id)
            mode_info = f"⚡ Quick Mode ({INFINITY_SYMBOL} wickets)"
        else:  # classic
            keyboard = get_wickets_keyboard(game_id)
            mode_info = "🏏 Classic Mode"
            
        # Add explanatory text for setup
        if mode == 'classic':
            mode_message = (
                f"🏏 *CLASSIC MODE SETUP*\n"
                f"━━━━━━━━━━━━━━━━\n\n"
                f"• *Host:* {escape_markdown_v2_custom(game['creator_name'])}\n\n"
                f"Select number of wickets \\(1\\-10\\):"
            )
        elif mode == 'quick':
            mode_message = (
                f"⚡ *QUICK MODE SETUP*\n"
                f"━━━━━━━━━━━━━━━━\n\n"
                f"• *Host:* {escape_markdown_v2_custom(game['creator_name'])}\n\n"
                f"Select number of overs \\(1\\-50\\):"
            )
        else:
            mode_message = MESSAGE_STYLES['game_start'].format(
                mode=game['mode'].title(),
                host=escape_markdown_v2_custom(game['creator_name'])
            )

        await query.edit_message_text(
            mode_message,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN_V2
        )
    except telegram.error.BadRequest as e:
        if "message is not modified" in str(e).lower():
            # User clicked the same button again, ignore silently
            pass
        else:
            logger.error(f"Error in handle_mode: {e}")
            await handle_error(query, game_id if 'game_id' in locals() else None)
    except Exception as e:
        logger.error(f"Error in handle_mode: {e}")
        await handle_error(query, game_id if 'game_id' in locals() else None)

async def handle_wickets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = str(query.from_user.id)
    
    try:
        await query.answer()
    except Exception:
        pass  # Query too old, continue anyway
    
    try:
        # Parse callback_data: "wickets_{game_id}_{wickets}"
        parts = query.data.split('_')
        wickets = parts[-1]
        game_id = '_'.join(parts[1:-1])
        game = games[game_id]
        
        # Only game creator can configure settings
        if user_id != game['creator']:
            try:
                await query.answer(
                    "⚠️ You are not the host! Only the game creator can configure settings.",
                    show_alert=True
                )
            except Exception:
                pass
            return
        
        game['max_wickets'] = int(wickets)
        
        keyboard = [
            [
                InlineKeyboardButton("5 🎯", callback_data=f"overs_{game_id}_5"),
                InlineKeyboardButton("10 🎯", callback_data=f"overs_{game_id}_10"),
            ],
            [
                InlineKeyboardButton("15 🎯", callback_data=f"overs_{game_id}_15"),
                InlineKeyboardButton("20 🎯", callback_data=f"overs_{game_id}_20"),
            ],
            [InlineKeyboardButton("📝 Custom Overs", callback_data=f"custom_{game_id}_overs")]
        ]
        
        message_text = (
            f"🏏 *CLASSIC MODE SETUP*\n"
            f"━━━━━━━━━━━━━━━━\n\n"
            f"• *Wickets:* {wickets}\n\n"
            f"Now select number of overs \\(1\\-50\\):"
        )
        
        try:
            await query.edit_message_text(
                message_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN_V2
            )
        except telegram.error.BadRequest as e:
            if "message is not modified" in str(e).lower():
                pass  # Message already has this content, ignore
            else:
                raise
        
    except Exception as e:
        logger.error(f"Error in handle_wickets: {e}")
        await handle_error(query, game_id if 'game_id' in locals() else None)

async def handle_overs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle overs selection callback (fixed typo from handle_vers)"""
    query = update.callback_query
    user_id = str(query.from_user.id)
    
    try:
        await query.answer()
    except Exception:
        pass  # Query too old, continue anyway
    
    try:
        # Parse callback_data: "overs_{game_id}_{overs}"
        parts = query.data.split('_')
        overs = parts[-1]
        game_id = '_'.join(parts[1:-1])
        if game_id not in games:
            await query.edit_message_text(
                escape_markdown_v2_custom("❌ Game not found!"),
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return
            
        game = games[game_id]
        
        # Only game creator can configure settings
        if user_id != game['creator']:
            try:
                await query.answer(
                    "⚠️ You are not the host! Only the game creator can configure settings.",
                    show_alert=True
                )
            except Exception:
                pass
            return
        game['max_overs'] = int(overs)
        game['status'] = 'waiting'
        
        # Ensure max_wickets is set for different modes
        if game['mode'] == 'quick':
            game['max_wickets'] = float('inf')
        elif game['mode'] == 'survival':
            game['max_wickets'] = 1
        
        keyboard = [[InlineKeyboardButton("🤝 Join Match", callback_data=f"join_{game_id}")]]
        
        mode_title = escape_markdown_v2_custom(game['mode'].title())
        wickets_display = str(game['max_wickets']) if game['max_wickets'] != float('inf') else INFINITY_SYMBOL
        host_name = escape_markdown_v2_custom(game['creator_name'])
        
        message_text = (
            f"*🏏 Game Ready\\!*\n"
            f"{MATCH_SEPARATOR}\n"
            f"*Mode:* {mode_title}\n"
            f"*Wickets:* {wickets_display}\n"
            f"*Overs:* {overs}\n"
            f"*Host:* {host_name}\n\n"
            f"*Waiting for opponent\\.\\.\\.*"
        )
        
        await query.edit_message_text(
            message_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN_V2
        )
        
    except Exception as e:
        logger.error(f"Error in handle_overs: {e}")
        await handle_error(query, game_id if 'game_id' in locals() else None)

# Update handle_custom function with proper escaping
async def handle_custom(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle custom input request with improved UI and proper escaping"""
    query = update.callback_query
    await query.answer()
    
    try:
        # Parse callback_data: "custom_{game_id}_{setting}"
        parts = query.data.split('_')
        setting = parts[-1]
        game_id = '_'.join(parts[1:-1])
        game = games[game_id]
        
        context.user_data['awaiting_input'] = {
            'game_id': game_id,
            'setting': setting,
            'chat_id': query.message.chat_id,
            'message_id': query.message.message_id
        }
        
        setting_title = "OVERS" if setting == "overs" else "WICKETS"
        max_value = GAME_MODES[game['mode']]['max_overs'] if setting == "overs" else GAME_MODES[game['mode']]['max_wickets']
        
        if max_value == float('inf'):
            max_value = 50 if setting == "overs" else 10
        
        mode_title = escape_markdown_v2_custom(game['mode'].title())
        
        message_text = (
            f"{UI_THEMES['primary']['separator']}\n"
            f"📝 *{setting_title}*\n"
            f"{UI_THEMES['primary']['section_sep']}\n\n"
            f"{UI_THEMES['accents']['alert']} Reply with a number *\\(1\\-{max_value}\\)*\n"
            f"{UI_THEMES['primary']['bullet']} Mode: *{mode_title}*\n"
            f"{UI_THEMES['primary']['footer']}"
        )
        
        sent_msg = await query.message.edit_text(
            message_text,
            parse_mode=ParseMode.MARKDOWN_V2
        )
        
        context.user_data['awaiting_input']['prompt_message_id'] = sent_msg.message_id
        logger.info(f"Custom {setting} input requested for game {game_id}")
        
    except Exception as e:
        logger.error(f"Error in handle_custom: {e}")
        error_msg = escape_markdown_v2_custom(
            f"{UI_THEMES['accents']['error']} An error occurred\\. Please try again\\."
        )
        await query.message.edit_text(
            error_msg,
            parse_mode=ParseMode.MARKDOWN_V2
        )

# Update handle_join function to properly store player names
async def handle_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = str(query.from_user.id)
    
    try:
        # Parse callback_data: "join_{game_id}"
        parts = query.data.split('_')
        game_id = '_'.join(parts[1:])
        
        if game_id not in games:
            await query.answer("❌ Game not found!")
            return
            
        game = games[game_id]
        
        if user_id == game['creator']:
            await query.answer("❌ You can't join your own game!", show_alert=True)
            return
            
        if 'joiner' in game:
            await query.answer("❌ Game already has two players!", show_alert=True)
            return
            
        # Store full player details
        game['joiner'] = user_id
        game['joiner_name'] = query.from_user.first_name
        if query.from_user.username:
            game['joiner_username'] = query.from_user.username
            
        game['status'] = 'toss'
        
        # Store initial game state
        game.update({
            'current_innings': 1,
            'score': {'innings1': 0, 'innings2': 0},
            'wickets': 0,
            'balls': 0,
            'boundaries': 0,
            'sixes': 0,
            'this_over': []
        })
        
        keyboard = [
            [
                InlineKeyboardButton("ODD", callback_data=f"toss_{game_id}_odd"),
                InlineKeyboardButton("EVEN", callback_data=f"toss_{game_id}_even")
            ]
        ]
        
        # Set who should choose odd/even
        game['choosing_player'] = game['joiner']
        game['choosing_player_name'] = game['joiner_name']
        
        # Tag both users - escape names for MarkdownV2
        creator_name_escaped = escape_markdown_v2_custom(game['creator_name'])
        joiner_name_escaped = escape_markdown_v2_custom(game['joiner_name'])
        creator_mention = f"[{creator_name_escaped}](tg://user?id={game['creator']})"
        joiner_mention = f"[{joiner_name_escaped}](tg://user?id={game['joiner']})"
        
        message_text = (
            f"⚔️ *MATCH LOCKED \\!* ⚔️\n"
            f"═══════════════════════\n\n"
            f"🔴 *{creator_mention}*  *VS*  🔵 *{joiner_mention}*\n\n"
            f"📍 *Mode:* {escape_markdown_v2_custom(game['mode'].title())}\n"
            f"🎯 *Overs:* {game['max_overs']}  |  🏏 *Wickets:* {str(game['max_wickets']) if game['max_wickets'] != float('inf') else INFINITY_SYMBOL}\n\n"
            f"🎲 *TOSS TIME\\!*\n"
            f"👉 {joiner_mention}, call *ODD* or *EVEN*\\!"
        )
        
        await query.edit_message_text(
            message_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN_V2
        )
        
    except Exception as e:
        logger.error(f"Error in handle_join: {e}")
        await handle_error(query, game_id if 'game_id' in locals() else None)

async def handle_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = str(query.from_user.id)
    
    try:
        # Parse callback_data: "choice_{game_id}_{choice}"
        # game_id might contain underscores (e.g., "challenge_CH1234")
        parts = query.data.split('_')
        choice = parts[-1]  # Last part is always the choice (bat/bowl)
        game_id = '_'.join(parts[1:-1])  # Everything between "choice" and choice is game_id
        game = games[game_id]
        
        if user_id != str(game['toss_winner']):
            await query.answer("❌ Only toss winner can choose!", show_alert=True)
            return
            
        await query.answer()
        
        if choice == 'bat':
            game['batsman'] = game['toss_winner']
            game['batsman_name'] = game['toss_winner_name']
            game['bowler'] = game['joiner'] if game['toss_winner'] == game['creator'] else game['creator']
            game['bowler_name'] = game['joiner_name'] if game['toss_winner'] == game['creator'] else game['creator_name']
        else:
            game['bowler'] = game['toss_winner']
            game['bowler_name'] = game['toss_winner_name']
            game['batsman'] = game['joiner'] if game['toss_winner'] == game['creator'] else game['creator']
            game['batsman_name'] = game['joiner_name'] if game['toss_winner'] == game['creator'] else game['creator_name']
        
        keyboard = get_batting_keyboard(game_id)
        
        await safe_edit_message(
            query.message,
            f"*🏏 Match Starting!*\n"
            f"{MATCH_SEPARATOR}\n"
            f"{game['toss_winner_name']} chose to {choice} first\n\n"
            f"🎮 {game['batsman_name']}'s turn to bat!",
            keyboard=InlineKeyboardMarkup(keyboard)
        )
        
    except Exception as e:
        logger.error(f"Error in handle_choice: {e}")
        await handle_error(query, game_id if 'game_id' in locals() else None)

# Update handle_bat function to match working version from Backup.py
async def handle_bat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = str(query.from_user.id)
    
    try:
        # Parse callback_data: "bat_{game_id}_{runs}"
        parts = query.data.split('_')
        runs_str = parts[-1]
        game_id = '_'.join(parts[1:-1])
        runs = int(runs_str)
        
        if game_id not in games:
            try:
                await query.answer("❌ Game not found!", show_alert=True)
            except Exception:
                pass
            return
            
        game = games[game_id]
        
        if user_id != str(game['batsman']):
            try:
                await query.answer(f"❌ Not your turn! It's {game['batsman_name']}'s turn to bat!", show_alert=True)
            except Exception:
                pass
            return
        
        # Check cooldown timer
        current_time = time.time()
        if user_id in user_action_cooldown:
            time_since_last = current_time - user_action_cooldown[user_id]
            if time_since_last < ACTION_COOLDOWN_SECONDS:
                wait_time = int(ACTION_COOLDOWN_SECONDS - time_since_last)
                try:
                    await query.answer(f"⏳ Wait {wait_time} sec", show_alert=False)
                except Exception:
                    pass
                return
        
        # Update cooldown timer
        user_action_cooldown[user_id] = current_time
        
        try:
            await query.answer()
        except Exception:
            pass  # Query too old, continue anyway
        
        game['batsman_choice'] = runs
        game['batsman_ready'] = True  # Flag that batsman has made a choice
        
        keyboard = get_bowling_keyboard(game_id)
        
        current_score = game['score'][f'innings{game["current_innings"]}']
        
        # Use random batting message with player name
        batting_msg = random.choice(ACTION_MESSAGES['batting']).format(game['batsman_name'])
        
        # Visual Over (last 6 balls max)
        visual_over = " ".join([{'0': '0️⃣', '1': '1️⃣', '2': '2️⃣', '3': '3️⃣', '4': '4️⃣', '6': '6️⃣', 'W': '🔴'}.get(str(b), str(b)) for b in game.get('this_over', [])])
        if not visual_over: visual_over = "New Over"

        # Stats Logic
        if game['current_innings'] == 1:
            # Projected Score
            crr = safe_division(current_score, game['balls']/6, 0)
            projected = int(crr * game['max_overs'])
            stats_line = f"⚡ *Runs/Over:* {crr:.1f}  |  🔮 *Projected:* {projected}"
        else:
            # Chase Equation
            needed = game['target'] - current_score
            rem_balls = (game['max_overs'] * 6) - game['balls']
            stats_line = f"🎯 *Target:* {game['target']}  |  *Need {needed} off {rem_balls}*"

        await safe_edit_message(
            query.message,
            f"🏟️  *CRICKET SAGA LIVE*\n"
            f"═══════════════════════════\n"
            f"🔴 *{game['batsman_name']}* vs 🔵 *{game['bowler_name']}*\n\n"
            f"          💥 *BATSMAN READY* 💥\n"
            f"    \"{batting_msg}\"\n\n"
            f"📊 *SCORE: {current_score}/{game['wickets']}*  ({game['balls']//6}.{game['balls']%6} Overs)\n"
            f"{stats_line}\n\n"
            f"This Over: {visual_over}\n"
            f"═══════════════════════════\n"
            f"👇 *Next Ball:* Select your shot...",
            keyboard=InlineKeyboardMarkup(keyboard)
        )
        
    except Exception as e:
        logger.error(f"Error in handle_bat: {e}")
        await handle_error(query, game_id if 'game_id' in locals() else None)

# Update handle_bowl function to use new messages
async def handle_bowl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = str(query.from_user.id)
    
    try:
        # Parse callback_data: "bowl_{game_id}_{bowl_num}"
        parts = query.data.split('_')
        bowl_num_str = parts[-1]
        game_id = '_'.join(parts[1:-1])
        bowl_num = int(bowl_num_str)
        
        if game_id not in games:
            try:
                await query.answer("❌ Game not found!", show_alert=True)
            except Exception:
                pass
            return
            
        game = games[game_id]
        
        if 'this_over' not in game:
            game['this_over'] = []
            
        current_score = game['score'][f'innings{game["current_innings"]}']
        
        if user_id != str(game['bowler']):
            try:
                await query.answer(f"❌ Not your turn! It's {game['bowler_name']}'s turn to bowl!", show_alert=True)
            except Exception:
                pass
            return
        
        # Check if batsman has made a choice
        if not game.get('batsman_ready', False):
            try:
                await query.answer("⏳ Waiting for batsman to choose...", show_alert=False)
            except Exception:
                pass
            return
        
        # Check cooldown timer
        current_time = time.time()
        if user_id in user_action_cooldown:
            time_since_last = current_time - user_action_cooldown[user_id]
            if time_since_last < ACTION_COOLDOWN_SECONDS:
                wait_time = int(ACTION_COOLDOWN_SECONDS - time_since_last)
                try:
                    await query.answer(f"⏳ Wait {wait_time} sec", show_alert=False)
                except Exception:
                    pass
                return
        
        # Update cooldown timer
        user_action_cooldown[user_id] = current_time
            
        try:
            await query.answer()
        except Exception:
            pass  # Query too old, continue anyway
        
        runs = game['batsman_choice']
        game['batsman_ready'] = False  # Clear flag so bowler can't use old choice

        # Determine result text early
        if bowl_num == runs:
            result_text = random.choice(COMMENTARY_PHRASES['wicket']).format(f"*{game['bowler_name']}*")
        else:
            if runs == 4:
                result_text = random.choice(COMMENTARY_PHRASES['run_4']).format(f"*{game['batsman_name']}*")
            elif runs == 6:
                result_text = random.choice(COMMENTARY_PHRASES['run_6']).format(f"*{game['batsman_name']}*")
            else:
                result_text = random.choice(COMMENTARY_PHRASES[f'run_{runs}']).format(f"*{game['batsman_name']}*")
        
        # Combine bowling and delivery into single message to reduce API calls
        combined_action = random.choice(ACTION_MESSAGES['bowling']).format(game['bowler_name']) + " ⚡"
        await safe_edit_message(query.message, combined_action)
        await asyncio.sleep(BALL_ANIMATION_DELAY)  # Single delay instead of multiple
        
        if bowl_num == runs:
            game['wickets'] += 1
            commentary = result_text
            game['this_over'].append('W')
            if should_end_innings(game):
                game['this_over'] = []
        else:
            game['score'][f'innings{game["current_innings"]}'] += runs
            current_score = game['score'][f'innings{game["current_innings"]}']
            game['this_over'].append(str(runs))
            if runs == 4:
                if game['current_innings'] == 1:
                    game['first_innings_boundaries'] = game.get('first_innings_boundaries', 0) + 1
                else:
                    game['second_innings_boundaries'] = game.get('second_innings_boundaries', 0) + 1
            elif runs == 6:
                if game['current_innings'] == 1:
                    game['first_innings_sixes'] = game.get('first_innings_sixes', 0) + 1
                else:
                    game['second_innings_sixes'] = game.get('second_innings_sixes', 0) + 1

            # Track current over score
            current_over = game['balls'] // 6
            if 'over_scores' not in game:
                game['over_scores'] = {}
            game['over_scores'][current_over] = game['over_scores'].get(current_over, 0) + runs
            commentary = result_text

        game['balls'] += 1
        
        current_score = game['score'][f'innings{game["current_innings"]}']
        
        # Check if innings should end first, before showing over complete
        if should_end_innings(game):
            if game['current_innings'] == 1:
                await handle_innings_change(query.message, game, game_id)
                return
            else:
                is_chase_successful = current_score >= game.get('target', float('inf'))
                await handle_game_end(query, game, current_score, is_chase_successful, context)
                return
        
        # Only show over complete if innings didn't end
        if game['balls'] % 6 == 0:
            over_commentary = random.choice(COMMENTARY_PHRASES['over_complete'])
            current_over = ' '.join(game['this_over'])
            game['this_over'] = []
            
            await safe_edit_message(
                query.message,
                f"*🏏 Over Complete!*\n"
                f"{MATCH_SEPARATOR}\n"
                f"Score: {current_score}/{game['wickets']}\n"
                f"Last Over: {current_over}\n\n"
                f"{over_commentary}\n\n"
                f"*Taking a short break between overs...*",
                keyboard=None
            )
            await asyncio.sleep(OVER_BREAK_DELAY)
        else:
            over_commentary = ""

        keyboard = get_batting_keyboard(game_id)
        
        if game['current_innings'] == 1:
            # Projected Score
            crr = safe_division(current_score, game['balls']/6, 0)
            if game['balls'] > 0:
                projected = int(crr * game['max_overs'])
                stats_line = f"⚡ *Runs/Over:* {crr:.1f}  |  🔮 *Projected:* {projected}"
            else:
                stats_line = f"⚡ *Runs/Over:* 0.0  |  🔮 *Projected:* TBD"
        else:
            # Chase Equation
            needed = game['target'] - current_score
            rem_balls = (game['max_overs'] * 6) - game['balls']
            stats_line = f"🎯 *Target:* {game['target']}  |  *Need {needed} off {rem_balls}*"

        # Visual Over
        visual_over = " ".join([{'0': '0️⃣', '1': '1️⃣', '2': '2️⃣', '3': '3️⃣', '4': '4️⃣', '6': '6️⃣', 'W': '🔴'}.get(str(b), str(b)) for b in game.get('this_over', [])])
        if not visual_over: visual_over = "New Over"

        status_text = (
            f"🏟️  *CRICKET SAGA LIVE*\n"
            f"═══════════════════════════\n"
            f"🔴 *{game['batsman_name']}* vs 🔵 *{game['bowler_name']}*\n\n"
            f"          {combined_action}\n"
            f"    \"{commentary}\"\n\n"
            f"📊 *SCORE: {current_score}/{game['wickets']}*  ({game['balls']//6}.{game['balls']%6} Overs)\n"
            f"{stats_line}\n\n"
            f"This Over: {visual_over}\n"
            f"═══════════════════════════\n"
            f"👇 *Next Ball:* Select your shot..."
        )
        
        await safe_edit_message(
            query.message,
            status_text,
            keyboard=InlineKeyboardMarkup(keyboard)
        )
        
    except Exception as e:
        logger.error(f"Error in handle_bowl: {e}")
        await handle_error(query, game_id if 'game_id' in locals() else None)

async def handle_innings_change(msg, game: dict, game_id: str):
    store_first_innings(game)
    
    # Store who batted first BEFORE swapping roles
    game['first_innings_batsman'] = game['batsman']
    game['first_innings_batsman_name'] = game['batsman_name']
    
    game['current_innings'] = 2
    game['wickets'] = 0
    game['balls'] = 0
    game['this_over'] = []
    game['batsman_ready'] = False  # Reset ready flag for new innings
    
    temp_batsman = game['batsman']
    temp_batsman_name = game['batsman_name']
    
    game['batsman'] = game['bowler']
    game['batsman_name'] = game['bowler_name']
    game['bowler'] = temp_batsman
    game['bowler_name'] = temp_batsman_name
    
    innings_commentary = random.choice(COMMENTARY_PHRASES['innings_end'])
    
    # Determine if batsman was out or innings ended normally (use stored name from before swap)
    batsman_out_text = ""
    batsman_name_escaped = escape_markdown_v2_custom(game['first_innings_batsman_name'])
    batsman_next_escaped = escape_markdown_v2_custom(game['batsman_name'])
    # Prepare overs string and escape reserved chars
    overs_raw = f"{game['first_innings_overs']}"
    overs_escaped = overs_raw.replace('.', '\\.')
    # Prepare score string
    score_str = f"{game['first_innings_score']}/{game['first_innings_wickets']}"
    # Prepare required rate string and escape period
    required_rate_raw = f"{game['target'] / game['max_overs']:.2f}"
    required_rate_escaped = required_rate_raw.replace('.', '\\.')
    # Prepare target string
    target_raw = f"{game['target']}"
    target_escaped = target_raw.replace('-', '\\-').replace('+', '\\+')
    # Escape exclamation and period in batsman_out_text
    if game['wickets'] >= game.get('max_wickets', 10):
        batsman_out_text = f"🏏 *{batsman_name_escaped}* got out\!\n\n"
    elif game['balls'] >= game['max_overs'] * 6:
        batsman_out_text = f"🏏 Innings ended\\. *{batsman_name_escaped}* finished not out\\.\n\n"

    # Add 1st innings batsman name line
    batsman_line = f"👤 *Batsman:* {batsman_name_escaped}\n"

    await safe_edit_message(msg,
        f"🏁 *1st INNINGS SUMMARY*\n"
        f"═══════════════════════\n\n"
        f"🏏 *Batting Star:* {batsman_name_escaped}\n"
        f"📊 *Score:* {score_str}  in  {overs_escaped} overs\n"
        f"🎯 *Target Set:* {target_escaped}\n"
        f"📈 *Required Rate:* {required_rate_escaped} RPO\n"
        f"═══════════════════════\n\n"
        f"{batsman_out_text}"
        f"🔥 *CHASE ON\\!* \n"
        f"🎮 *{batsman_next_escaped}*, you're up\\!",
        keyboard=InlineKeyboardMarkup(get_batting_keyboard(game_id)))

# Update handle_game_end to format match summary properly
# ===== PHASE 2: RANKED MATCHMAKING FUNCTIONS =====

async def add_to_ranked_queue(user_id: int, username: str, rating: int, rank_tier: str, message) -> bool:
    """Add a player to the ranked matchmaking queue"""
    try:
        # Check if already in queue
        if user_id in ranked_queue:
            return False
        
        # Add to in-memory queue
        ranked_queue[user_id] = {
            'username': username,
            'rating': rating,
            'rank_tier': rank_tier,
            'joined_at': time.time(),
            'message': message
        }
        
        # Add to database for persistence
        conn = get_db_connection()
        if conn:
            try:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO ranked_queue (user_id, username, rating, rank_tier)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (user_id) DO UPDATE
                        SET username = EXCLUDED.username,
                            rating = EXCLUDED.rating,
                            rank_tier = EXCLUDED.rank_tier,
                            searching_since = NOW()
                    """, (user_id, username, rating, rank_tier))
                    conn.commit()
            finally:
                return_db_connection(conn)
        
        logger.info(f"✅ {username} (ID: {user_id}) joined ranked queue - Rating: {rating} ({rank_tier})")
        return True
    except Exception as e:
        logger.error(f"Error adding to ranked queue: {e}")
        return False

async def remove_from_ranked_queue(user_id: int) -> bool:
    """Remove a player from the ranked matchmaking queue"""
    try:
        # Remove from in-memory queue
        if user_id in ranked_queue:
            username = ranked_queue[user_id]['username']
            del ranked_queue[user_id]
            logger.info(f"🚫 {username} (ID: {user_id}) left ranked queue")
        
        # Cancel any active search task
        if user_id in queue_search_tasks:
            queue_search_tasks[user_id].cancel()
            del queue_search_tasks[user_id]
        
        # Remove from database
        conn = get_db_connection()
        if conn:
            try:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM ranked_queue WHERE user_id = %s", (user_id,))
                    conn.commit()
            finally:
                return_db_connection(conn)
        
        return True
    except Exception as e:
        logger.error(f"Error removing from ranked queue: {e}")
        return False

async def find_ranked_opponent(user_id: int, user_rating: int) -> Optional[dict]:
    """Find a suitable opponent from the ranked queue (FIFO order)"""
    try:
        min_rating = user_rating - RANKED_RATING_RANGE
        max_rating = user_rating + RANKED_RATING_RANGE
        
        # Sort queue by timestamp to ensure first-come-first-serve
        sorted_queue = sorted(
            ranked_queue.items(),
            key=lambda x: x[1].get('joined_at', 0)
        )
        
        # Search sorted queue (first-come-first-serve)
        for opponent_id, opponent_data in sorted_queue:
            if opponent_id == user_id:
                continue
            
            # Check if opponent is already in a game
            opponent_in_game = False
            for game_id, game in games.items():
                if game.get('creator') == opponent_id or game.get('joiner') == opponent_id:
                    opponent_in_game = True
                    break
            
            if opponent_in_game:
                continue
            
            # Check if players have challenge cooldown with each other
            cooldown = await check_challenge_cooldown(user_id, opponent_id)
            if cooldown > 0:
                logger.info(f"⏳ Skipping match: Users {user_id} and {opponent_id} have {cooldown}s cooldown")
                continue
            
            # Also check reverse cooldown
            reverse_cooldown = await check_challenge_cooldown(opponent_id, user_id)
            if reverse_cooldown > 0:
                logger.info(f"⏳ Skipping match: Users {opponent_id} and {user_id} have {reverse_cooldown}s cooldown")
                continue
            
            opponent_rating = opponent_data['rating']
            if min_rating <= opponent_rating <= max_rating:
                # Found a match!
                logger.info(f"🎯 Match found: User {user_id} ({user_rating}) vs User {opponent_id} ({opponent_rating})")
                return {
                    'user_id': opponent_id,
                    'username': opponent_data['username'],
                    'rating': opponent_rating,
                    'rank_tier': opponent_data['rank_tier'],
                    'message': opponent_data.get('message')
                }
        
        return None
    except Exception as e:
        logger.error(f"Error finding ranked opponent: {e}")
        return None

async def create_ranked_match(player1_data: dict, player2_data: dict, chat_id: int):
    """Create a ranked match between two players"""
    try:
        # Check if either player is already in a game (prevent duplicate game creation)
        for game_id, game in games.items():
            if (game.get('creator') == player1_data['user_id'] or game.get('joiner') == player1_data['user_id'] or
                game.get('creator') == player2_data['user_id'] or game.get('joiner') == player2_data['user_id']):
                logger.warning(f"🚫 Game already exists for these players, skipping duplicate creation")
                return None
        
        # Remove both players from queue FIRST to prevent race condition
        await remove_from_ranked_queue(player1_data['user_id'])
        await remove_from_ranked_queue(player2_data['user_id'])
        
        # Use player1's chat_id as the game_id to ensure single game
        game_key = str(chat_id)
        
        # Double-check game doesn't exist
        if game_key in games:
            logger.warning(f"🚫 Game {game_key} already exists, aborting")
            return None
        
        # Generate match ID
        match_id = f"R{random.randint(1000, 9999)}"
        
        # Initialize game state with ranked flag
        games[game_key] = {
            'match_id': match_id,
            'creator': player1_data['user_id'],
            'creator_name': player1_data['username'],
            'joiner': player2_data['user_id'],
            'joiner_name': player2_data['username'],
            'status': 'toss',
            'chat_id': chat_id,
            'mode': 'blitz',  # Ranked matches use Blitz mode (3 wickets, 3 overs)
            'max_wickets': 3,
            'max_overs': 3,
            'ranked_match': True,  # CRITICAL FLAG: Marks this as a rated match
            'player1_rating': player1_data['rating'],
            'player2_rating': player2_data['rating'],
            'score': {'innings1': 0, 'innings2': 0},
            'balls': 0,
            'wickets': 0,
            'current_innings': 1,
            'first_innings_score': 0,
            'first_innings_wickets': 0,
            'first_innings_balls': 0,
            'first_innings_boundaries': 0,
            'first_innings_sixes': 0,
            'second_innings_boundaries': 0,
            'second_innings_sixes': 0,
            'dot_balls': 0,
            'batsman_choice': None,
            'batsman_ready': False
        }
        
        logger.info(f"🏆 Ranked match created: {match_id} - {player1_data['username']} vs {player2_data['username']}")
        return match_id
    except Exception as e:
        logger.error(f"Error creating ranked match: {e}")
        return None

async def update_search_message(user_id: int, message, username: str, rating: int, rank_tier: str):
    """Periodically update the search status message with elapsed time"""
    try:
        start_time = ranked_queue[user_id]['joined_at']
        
        # Log to admin
        await send_admin_log(
            f"User: {username} | ID: {user_id} | Action: Joined ranked queue | Rating: {rating} ({rank_tier})",
            log_type="match"
        )
        
        while user_id in ranked_queue:
            elapsed = int(time.time() - start_time)
            
            # Check for timeout
            if elapsed >= RANKED_SEARCH_TIMEOUT:
                await handle_queue_timeout(user_id, message)
                return
            
            # Update message every 5 seconds
            min_rating = rating - RANKED_RATING_RANGE
            max_rating = rating + RANKED_RATING_RANGE
            
            search_text = (
                f"🔍 *Searching for Opponent*\\.\\.\\.\n"
                f"━━━━━━━━━━━━━━\n"
                f"⚔️ Your Rating: {rating} \\({escape_markdown_v2_custom(rank_tier)}\\)\n"
                f"🎯 Looking for: {min_rating}\\-{max_rating} range\n"
                f"⏱️ Searching\\.\\.\\. {elapsed}s\n\n"
                f"_Use /cancel\\_queue to stop searching_"
            )
            
            try:
                await message.edit_text(search_text, parse_mode=ParseMode.MARKDOWN_V2)
            except BadRequest:
                pass  # Ignore if message not modified
            
            await asyncio.sleep(5)
    except asyncio.CancelledError:
        logger.info(f"Search task cancelled for user {user_id}")
    except Exception as e:
        logger.error(f"Error updating search message: {e}")

async def handle_queue_timeout(user_id: int, message):
    """Handle queue timeout after 2 minutes"""
    try:
        user_data = ranked_queue.get(user_id)
        if not user_data:
            return
        
        # Remove from queue
        await remove_from_ranked_queue(user_id)
        
        # Send timeout message
        timeout_text = (
            f"⏰ *Search Timeout*\n"
            f"━━━━━━━━━━━━━━\n"
            f"No opponents found in your rank range\\.\n\n"
            f"🎯 Your Rating: {user_data['rating']} \\({escape_markdown_v2_custom(user_data['rank_tier'])}\\)\n"
            f"🔍 Searched: {user_data['rating'] - RANKED_RATING_RANGE}\\-{user_data['rating'] + RANKED_RATING_RANGE} range\n"
            f"⏱️ Duration: 2m 0s\n\n"
            f"_Try again later when more players are online\\!_"
        )
        
        try:
            await message.edit_text(timeout_text, parse_mode=ParseMode.MARKDOWN_V2)
        except:
            await message.reply_text(timeout_text, parse_mode=ParseMode.MARKDOWN_V2)
    except Exception as e:
        logger.error(f"Error handling queue timeout: {e}")

def get_rank_up_message(new_tier: str, username: str, user_id: int, new_rating: int) -> str:
    """Generate rank-up celebration message based on tier"""
    user_mention = f'<a href="tg://user?id={user_id}">{username}</a>'
    
    tier_messages = {
        "Silver": {
            "emoji": "🥈",
            "title": "SILVER RANK ACHIEVED!",
            "message": "You've climbed out of Bronze! Keep pushing forward!"
        },
        "Gold": {
            "emoji": "🥇",
            "title": "GOLD RANK ACHIEVED!",
            "message": "You're shining bright! The competition heats up from here!"
        },
        "Platinum": {
            "emoji": "💿",
            "title": "PLATINUM RANK ACHIEVED!",
            "message": "Elite territory! You're among the top players now!"
        },
        "Diamond": {
            "emoji": "💎",
            "title": "DIAMOND RANK ACHIEVED!",
            "message": "Brilliant performance! Only the best make it this far!"
        },
        "Ruby": {
            "emoji": "🔴",
            "title": "RUBY RANK ACHIEVED!",
            "message": "Legendary status! You're approaching the pinnacle!"
        },
        "Immortal": {
            "emoji": "⭐",
            "title": "IMMORTAL RANK ACHIEVED!",
            "message": "🎉 IMMORTAL! You've reached the highest tier! 🎉"
        }
    }
    
    tier_info = tier_messages.get(new_tier)
    if not tier_info:
        return None
    
    celebration = (
        f"{tier_info['emoji']} <b>{tier_info['title']}</b> {tier_info['emoji']}\n"
        f"━━━━━━━━━━━━━━\n\n"
        f"Congratulations {user_mention}!\n\n"
        f"{tier_info['message']}\n\n"
        f"<b>New Rating:</b> {new_rating}\n"
        f"<b>Current Rank:</b> {new_tier}\n\n"
        f"🚀 Keep climbing!"
    )
    
    return celebration

async def handle_game_end(query, game: dict, current_score: int, is_chase_successful: bool, context: ContextTypes.DEFAULT_TYPE = None):
    """Handle game end with improved match summary format"""
    try:
        match_id = game.get('match_id', f"M{random.randint(1000, 9999)}")
        date = datetime.now().strftime('%d %b %Y')

        # Calculate innings stats safely
        first_innings_overs = f"{game.get('first_innings_balls', 0)//6}.{game.get('first_innings_balls', 0)%6}"
        second_innings_overs = f"{game['balls']//6}.{game['balls']%6}"
        
        # Calculate boundaries and sixes for both innings
        first_innings_boundaries = game.get('first_innings_boundaries', 0)
        first_innings_sixes = game.get('first_innings_sixes', 0)
        second_innings_boundaries = game.get('second_innings_boundaries', 0)
        second_innings_sixes = game.get('second_innings_sixes', 0)
        
        total_boundaries = first_innings_boundaries + second_innings_boundaries
        total_sixes = first_innings_sixes + second_innings_sixes

        # Calculate run rates safely
        first_innings_rr = safe_division(game['first_innings_score'], game.get('first_innings_balls', 0)/6, 0)
        second_innings_rr = safe_division(current_score, game['balls']/6, 0)
        avg_rr = (first_innings_rr + second_innings_rr) / 2

        # Find best over score
        best_over_score = max(game.get('over_scores', {0: 0}).values(), default=0)
        
        # Determine result and winning details
        runs_short = game['target'] - current_score - 1
        
        # Check for draw
        if runs_short == 0:
            # Draw match - both teams scored same
            winner = "Match Drawn"
            result_text = "Scores Level 🤝"
            winning_shot_line = ""
        elif is_chase_successful:
            wickets_left = game['max_wickets'] - game['wickets']
            winner = game['batsman_name']
            result_text = f"won by {wickets_left} wicket" + ("s" if wickets_left != 1 else "")
            # Determine winning shot (only for successful chase)
            if game.get('this_over') and len(game['this_over']) > 0:
                last_ball = game['this_over'][-1]
                if last_ball == '6':
                    winning_shot = "Six 💥"
                elif last_ball == '4':
                    winning_shot = "Four 🏏"
                elif last_ball == 'W':
                    winning_shot = "Wicket 🎯"
                elif last_ball == '0':
                    winning_shot = "Dot Ball"
                else:
                    winning_shot = f"{last_ball} Run" + ("s" if last_ball != '1' else "")
            else:
                winning_shot = "Match Won"
            winning_shot_line = f"*💥 Winning Shot: {winning_shot}*\n\n"
        else:
            winner = game['bowler_name']
            result_text = f"won by {runs_short} run" + ("s" if runs_short != 1 else "")
            winning_shot_line = ""

        # Get who actually batted first (after innings change, they're the bowler)
        first_batsman = game.get('first_innings_batsman_name', game['bowler_name'])
        second_batsman = game['batsman_name']  # Current batsman is the chaser
        
        # Calculate strike rates
        first_balls = game.get('first_innings_balls', 1)
        first_sr = round((game['first_innings_score'] / first_balls * 100), 1) if first_balls > 0 else 0.0
        second_balls = game['balls'] if game['balls'] > 0 else 1
        second_sr = round((current_score / second_balls * 100), 1) if second_balls > 0 else 0.0
        
        # New format with strike rates
        final_message = (
            f"🏆  *MATCH RESULT*\n"
            f"════════════════\n\n"
            f"🔴 *{first_batsman}* vs 🔵 *{second_batsman}*\n\n"
            f"📊 *SCORECARD*\n"
            f"• *{first_batsman}*: {game['first_innings_score']}/{game['first_innings_wickets']} \\({first_innings_overs}\\)\n"
            f"  SR: {first_sr} \\| 6s: {game.get('first_innings_sixes', 0)}\n\n"
            f"• *{second_batsman}*: {current_score}/{game['wickets']} \\({second_innings_overs}\\)\n"
            f"  SR: {second_sr} \\| 6s: {game.get('second_innings_sixes', 0)}\n\n"
            f"🎉 *WINNER: {escape_markdown_v2_custom(winner)}*\n"
            f"{result_text} \\! 🎊"
        )

        # Send message with proper escaping
        await query.message.edit_text(
            escape_markdown_v2_custom(final_message),
            parse_mode=ParseMode.MARKDOWN_V2
        )
        
        # Update the match data to include the new stats
        match_data = {
            'match_id': match_id,
            'user_id': game.get('creator'),  # Add user_id for database save
            'date': date,
            'mode': game['mode'],
            'player1_id': game.get('creator'),  # Add player IDs
            'player2_id': game.get('joiner'),   # Add player IDs
            'teams': {
                'team1': game['creator_name'],
                'team2': game['joiner_name']
            },
            'innings1': {
                'score': game['first_innings_score'],
                'wickets': game['first_innings_wickets'],
                'overs': first_innings_overs,
                'run_rate': first_innings_rr,
                'boundaries': first_innings_boundaries,
                'sixes': first_innings_sixes
            },
            'innings2': {
                'score': current_score,
                'wickets': game['wickets'],
                'overs': second_innings_overs,
                'run_rate': second_innings_rr,
                'boundaries': second_innings_boundaries,
                'sixes': second_innings_sixes
            },
            'stats': {
                'total_boundaries': total_boundaries,
                'total_sixes': total_sixes,
                'best_over': best_over_score,
                'dot_balls': game.get('dot_balls', 0),
                'average_rr': avg_rr
            },
            'result': f"{winner} {result_text}"
        }

        # NOTE: Match is NOT auto-saved. Use /save command to save match history.

        # Cleanup game state
        if str(game['chat_id']) in games:
            del games[str(game['chat_id'])]

        # Save player stats for both players
        try:
            # Update batsman (current chaser) stats
            # They batted in 2nd innings and bowled in 1st innings
            await update_player_stats(
                user_id=game['batsman'],
                balls_faced=game['balls'],
                runs_scored=current_score,
                wickets=game.get('first_innings_wickets', 0),  # Wickets they took as bowler in 1st innings
                boundaries=game.get('second_innings_boundaries', 0),
                sixes=game.get('second_innings_sixes', 0),
                dot_balls=0,
                is_winner=is_chase_successful
            )
            
            # Update bowler (first innings batsman) stats
            # They batted in 1st innings and bowled in 2nd innings
            await update_player_stats(
                user_id=game['bowler'],
                balls_faced=game.get('first_innings_balls', 0),
                runs_scored=game.get('first_innings_score', 0),
                wickets=game['wickets'],  # Wickets they took as bowler in 2nd innings
                boundaries=game.get('first_innings_boundaries', 0),
                sixes=game.get('first_innings_sixes', 0),
                dot_balls=game.get('dot_balls', 0),
                is_winner=not is_chase_successful
            )
        except Exception as e:
            logger.error(f"Error updating player stats: {e}")

        # PHASE 2: Update ELO ratings for ranked matches
        if game.get('ranked_match', False) or game.get('is_ranked', False):
            try:
                # Use actual game roles (who batted first vs second)
                first_batsman_id = game['bowler']  # Bowler in 2nd innings = batted first
                second_batsman_id = game['batsman']  # Batsman in 2nd innings = chasing
                first_batsman_name = game['bowler_name']
                second_batsman_name = game['batsman_name']
                
                # Get ratings (stored by user_id, not by batting order)
                player1_id = game['creator']
                player2_id = game['joiner']
                player1_rating = game.get('player1_rating') or game.get('p1_rating', 1000)
                player2_rating = game.get('player2_rating') or game.get('p2_rating', 1000)
                
                # Map ratings to actual batting order
                if first_batsman_id == player1_id:
                    first_batsman_rating = player1_rating
                    second_batsman_rating = player2_rating
                else:
                    first_batsman_rating = player2_rating
                    second_batsman_rating = player1_rating
                
                # Determine winner based on chase result
                # Winner = 1 means first batsman wins (chase failed)
                # Winner = 2 means second batsman wins (chase succeeded)
                if runs_short == 0:
                    winner = 0  # Draw
                elif is_chase_successful:
                    winner = 2  # Second batsman (chaser) wins
                else:
                    winner = 1  # First batsman wins (defended score)
                
                # Get player stats for advanced rating calculation
                player1_stats = await get_career_stats(str(player1_id))
                player2_stats = await get_career_stats(str(player2_id))
                first_batsman_stats = player1_stats if first_batsman_id == player1_id else player2_stats
                second_batsman_stats = player2_stats if first_batsman_id == player1_id else player1_stats
                
                # Get dynamic K-factors based on each player's rank and match count
                first_batsman_k = get_k_factor_by_rank(
                    first_batsman_stats.get('rank_tier', 'Gold I'),
                    first_batsman_stats.get('total_ranked_matches', 0)
                )
                second_batsman_k = get_k_factor_by_rank(
                    second_batsman_stats.get('rank_tier', 'Gold I'),
                    second_batsman_stats.get('total_ranked_matches', 0)
                )
                
                # Calculate base ELO changes (using average K for calculation)
                avg_k = (first_batsman_k + second_batsman_k) / 2
                rating_change_first, rating_change_second = calculate_elo_change(
                    first_batsman_rating, second_batsman_rating, winner, k_factor=int(avg_k)
                )
                
                # Apply individual K-factor adjustments
                # Scale changes proportionally to each player's K-factor
                if avg_k > 0:
                    rating_change_first = int(rating_change_first * (first_batsman_k / avg_k))
                    rating_change_second = int(rating_change_second * (second_batsman_k / avg_k))
                
                # Calculate win streak bonuses (flat additions, not multipliers)
                first_streak_bonus = calculate_win_streak_bonus(
                    first_batsman_stats.get('current_streak', 0),
                    first_batsman_stats.get('rank_tier', 'Gold I'),
                    winner == 1,
                    first_batsman_stats.get('total_ranked_matches', 0)
                )
                second_streak_bonus = calculate_win_streak_bonus(
                    second_batsman_stats.get('current_streak', 0),
                    second_batsman_stats.get('rank_tier', 'Gold I'),
                    winner == 2,
                    second_batsman_stats.get('total_ranked_matches', 0)
                )
                
                # Add streak bonuses to winners only (already returns 0 for losers)
                rating_change_first += first_streak_bonus
                rating_change_second += second_streak_bonus
                
                # Log advanced rating info
                logger.info(
                    f"Advanced Rating: P1 K={first_batsman_k} streak_bonus={first_streak_bonus} | "
                    f"P2 K={second_batsman_k} streak_bonus={second_streak_bonus}"
                )
                
                # Map rating changes back to creator/joiner for database storage
                if first_batsman_id == player1_id:
                    rating_change_p1 = rating_change_first
                    rating_change_p2 = rating_change_second
                else:
                    rating_change_p1 = rating_change_second
                    rating_change_p2 = rating_change_first
                
                # ========== ANTI-CHEAT PROCESSING ==========
                
                # Check for suspicious match patterns
                is_suspicious_p1, reason_p1, pattern_p1 = await check_match_patterns(player1_id, player2_id)
                is_suspicious_p2, reason_p2, pattern_p2 = await check_match_patterns(player2_id, player1_id)
                
                # Check for win trading
                is_win_trading, win_trade_details = await detect_win_trading(player1_id, player2_id)
                
                # Get rating multipliers (anti-smurf)
                multiplier_p1 = await get_rating_multiplier(player1_id)
                multiplier_p2 = await get_rating_multiplier(player2_id)
                
                # Get trust scores (for tracking only, no penalties)
                trust_p1 = await calculate_trust_score(player1_id)
                trust_p2 = await calculate_trust_score(player2_id)
                
                # NO PENALTIES - All multipliers set to 1.0
                trust_mult_p1 = 1.0
                trust_mult_p2 = 1.0
                pattern_mult = 1.0
                multiplier_p1 = 1.0
                multiplier_p2 = 1.0
                
                # Apply multipliers (all 1.0, so rating_change stays unchanged)
                final_change_p1 = int(rating_change_p1 * multiplier_p1 * trust_mult_p1 * pattern_mult)
                final_change_p2 = int(rating_change_p2 * multiplier_p2 * trust_mult_p2 * pattern_mult)
                
                # Log adjustments if any
                if final_change_p1 != rating_change_p1 or final_change_p2 != rating_change_p2:
                    logger.warning(
                        f"⚠️ Rating adjusted: P1 {rating_change_p1}→{final_change_p1} "
                        f"(x{multiplier_p1:.2f} x{trust_mult_p1:.2f} x{pattern_mult:.2f}), "
                        f"P2 {rating_change_p2}→{final_change_p2} "
                        f"(x{multiplier_p2:.2f} x{trust_mult_p2:.2f} x{pattern_mult:.2f})"
                    )
                
                # Flag suspicious activities
                if is_suspicious_p1:
                    await flag_suspicious_activity(
                        player1_id, 'opponent_frequency', player2_id,
                        reason_p1, TRUST_SCORE_ADJUSTMENTS['excessive_rematches']
                    )
                if is_suspicious_p2:
                    await flag_suspicious_activity(
                        player2_id, 'opponent_frequency', player1_id,
                        reason_p2, TRUST_SCORE_ADJUSTMENTS['excessive_rematches']
                    )
                if is_win_trading:
                    await flag_suspicious_activity(
                        player1_id, 'win_trading', player2_id,
                        f"Win trading detected: {win_trade_details}",
                        TRUST_SCORE_ADJUSTMENTS['alternating_wins']
                    )
                    await flag_suspicious_activity(
                        player2_id, 'win_trading', player1_id,
                        f"Win trading detected: {win_trade_details}",
                        TRUST_SCORE_ADJUSTMENTS['alternating_wins']
                    )
                
                # Record match in detailed history for pattern tracking
                winner_id = player1_id if winner == 1 else (player2_id if winner == 2 else None)
                game['p1_rating_change'] = final_change_p1
                game['p2_rating_change'] = final_change_p2
                await record_match_detailed(game, winner_id, 'ranked')
                
                # ========== END ANTI-CHEAT PROCESSING ==========
                
                # Use final adjusted changes
                rating_change_p1 = final_change_p1
                rating_change_p2 = final_change_p2
                
                # Map final changes back to batting order for display
                if first_batsman_id == player1_id:
                    final_change_first = final_change_p1
                    final_change_second = final_change_p2
                else:
                    final_change_first = final_change_p2
                    final_change_second = final_change_p1
                
                # Update ratings in database
                conn = get_db_connection()
                if conn:
                    try:
                        with conn.cursor() as cur:
                            # Update player 1 rating with verification
                            new_rating_p1 = player1_rating + rating_change_p1
                            new_rank_p1 = get_rank_from_rating(new_rating_p1)
                            
                            # Update win streak for player 1
                            # Get current stats for player 1 (reuse from earlier fetch)
                            p1_current_stats = player1_stats
                            if winner == 1:
                                # Winner: increment streak
                                new_streak_p1 = p1_current_stats.get('current_streak', 0) + 1
                                streak_type_p1 = 'win'
                            else:
                                # Loser: reset streak
                                new_streak_p1 = 0
                                streak_type_p1 = 'none'
                            
                            cur.execute("""
                                UPDATE career_stats 
                                SET rating = rating + %s,
                                    rank_tier = %s,
                                    username = %s,
                                    total_matches = total_matches + 1,
                                    wins = wins + %s,
                                    losses = losses + %s,
                                    current_streak = %s,
                                    streak_type = %s,
                                    updated_at = CURRENT_TIMESTAMP
                                WHERE user_id = %s
                                RETURNING user_id, rating, total_matches, wins, losses, current_streak
                            """, (rating_change_p1, new_rank_p1, game['creator_name'], 
                                  1 if winner == 1 else 0, 1 if winner == 2 else 0,
                                  new_streak_p1, streak_type_p1, player1_id))
                            p1_result = cur.fetchone()
                            if not p1_result:
                                logger.error(f"❌ Failed to update stats for player1_id={player1_id}")
                                await send_admin_log(
                                    f"DB ERROR: Failed to update stats for user {game['creator_name']} (ID: {player1_id}) in match #{match_id}",
                                    log_type="db_error"
                                )
                            else:
                                logger.info(f"✅ P1 updated: rating={p1_result[1]}, matches={p1_result[2]}, wins={p1_result[3]}, streak={p1_result[5]}")
                            
                            # Update player 2 rating with verification
                            new_rating_p2 = player2_rating + rating_change_p2
                            new_rank_p2 = get_rank_from_rating(new_rating_p2)
                            
                            # Update win streak for player 2
                            # Get current stats for player 2 (reuse from earlier fetch)
                            p2_current_stats = player2_stats
                            if winner == 2:
                                # Winner: increment streak
                                new_streak_p2 = p2_current_stats.get('current_streak', 0) + 1
                                streak_type_p2 = 'win'
                            else:
                                # Loser: reset streak
                                new_streak_p2 = 0
                                streak_type_p2 = 'none'
                            
                            cur.execute("""
                                UPDATE career_stats 
                                SET rating = rating + %s,
                                    rank_tier = %s,
                                    username = %s,
                                    total_matches = total_matches + 1,
                                    wins = wins + %s,
                                    losses = losses + %s,
                                    current_streak = %s,
                                    streak_type = %s,
                                    updated_at = CURRENT_TIMESTAMP
                                WHERE user_id = %s
                                RETURNING user_id, rating, total_matches, wins, losses, current_streak
                            """, (rating_change_p2, new_rank_p2, game['joiner_name'],
                                  1 if winner == 2 else 0, 1 if winner == 1 else 0,
                                  new_streak_p2, streak_type_p2, player2_id))
                            p2_result = cur.fetchone()
                            if not p2_result:
                                logger.error(f"❌ Failed to update stats for player2_id={player2_id}")
                                await send_admin_log(
                                    f"DB ERROR: Failed to update stats for user {game['joiner_name']} (ID: {player2_id}) in match #{match_id}",
                                    log_type="db_error"
                                )
                            else:
                                logger.info(f"✅ P2 updated: rating={p2_result[1]}, matches={p2_result[2]}, wins={p2_result[3]}, streak={p2_result[5]}")
                            
                            # Save to ranked_matches table
                            cur.execute("""
                                INSERT INTO ranked_matches 
                                (player1_id, player2_id, winner_id, p1_rating_before, p1_rating_after,
                                 p1_rating_change, p2_rating_before, p2_rating_after, p2_rating_change,
                                 p1_score, p1_wickets, p1_overs, p2_score, p2_wickets, p2_overs, match_date)
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                            """, (player1_id, player2_id, player1_id if winner == 1 else player2_id,
                                  player1_rating, new_rating_p1, rating_change_p1,
                                  player2_rating, new_rating_p2, rating_change_p2,
                                  game['first_innings_score'], game['first_innings_wickets'], 
                                  float(first_innings_overs.replace(' ov', '')),
                                  current_score, game['wickets'], 
                                  float(second_innings_overs.replace(' ov', ''))))
                            
                            conn.commit()
                            
                            # Store rating changes for separate message
                            game['rating_changes'] = {
                                'player1_change': rating_change_p1,
                                'player2_change': rating_change_p2,
                                'player1_old': player1_rating,
                                'player2_old': player2_rating,
                                'player1_new': new_rating_p1,
                                'player2_new': new_rating_p2,
                                'new_rank_p1': new_rank_p1,
                                'new_rank_p2': new_rank_p2
                            }
                            
                            logger.info(f"📊 Ranked match {match_id}: P1 {rating_change_p1:+d}, P2 {rating_change_p2:+d}")
                            
                    except Exception as db_error:
                        logger.error(f"Database update error: {db_error}", exc_info=True)
                        await send_admin_log(
                            f"DB ERROR: Failed to save match #{match_id} results | Error: {str(db_error)[:100]}",
                            log_type="db_error"
                        )
                    finally:
                        if conn:
                            return_db_connection(conn)
                            conn = None
                
                # Send rating changes as separate message AFTER database commit
                try:
                    logger.info(f"Attempting to send rating message to chat {query.message.chat_id}")
                    
                    # Determine winner for display
                    winner_name = second_batsman_name if is_chase_successful else first_batsman_name
                    winner_id = second_batsman_id if is_chase_successful else first_batsman_id
                    loser_name = first_batsman_name if is_chase_successful else second_batsman_name
                    loser_id = first_batsman_id if is_chase_successful else second_batsman_id
                    
                    # Get FINAL ADJUSTED rating changes for winner and loser
                    if winner_id == first_batsman_id:
                        winner_change = final_change_first
                        loser_change = final_change_second
                        winner_old = first_batsman_rating
                        loser_old = second_batsman_rating
                    else:
                        winner_change = final_change_second
                        loser_change = final_change_first
                        winner_old = second_batsman_rating
                        loser_old = first_batsman_rating
                    
                    winner_new = winner_old + winner_change
                    loser_new = loser_old + loser_change
                    winner_rank = get_rank_from_rating(winner_new)
                    loser_rank = get_rank_from_rating(loser_new)
                    
                    # Log match result to admin
                    await send_admin_log(
                        f"Match #{match_id} Complete | Winner: {winner_name} | "
                        f"Score: {game['score']['innings1']}-{game['score']['innings2']} | "
                        f"{winner_name}: {winner_old}→{winner_new} ({winner_change:+d}) | "
                        f"{loser_name}: {loser_old}→{loser_new} ({loser_change:+d})",
                        log_type="match"
                    )
                    
                    # Tag users
                    winner_mention = f'<a href="tg://user?id={winner_id}">{winner_name}</a>'
                    loser_mention = f'<a href="tg://user?id={loser_id}">{loser_name}</a>'
                    
                    rating_message = (
                        f"<b>📊 RANKED MATCH COMPLETE - #{match_id}</b>\n\n"
                        f"<b>Rating Changes:</b>\n"
                        f"🔹 {winner_mention} 🏆\n"
                        f"   {winner_old} → {winner_new} ({winner_change:+d})\n"
                        f"   {winner_rank}\n\n"
                        f"🔸 {loser_mention}\n"
                        f"   {loser_old} → {loser_new} ({loser_change:+d})\n"
                        f"   {loser_rank}"
                    )
                    
                    logger.info(f"Sending rating message: {rating_message}")
                    await context.bot.send_message(
                        chat_id=query.message.chat_id,
                        text=rating_message,
                        parse_mode=ParseMode.HTML
                    )
                    logger.info("✅ Rating message sent successfully!")
                    
                    # PHASE 4: Check for rank-up celebrations
                    # Recalculate ranks from new ratings (already have winner_new, loser_new)
                    old_rank_winner = get_rank_from_rating(winner_old)
                    new_rank_winner = get_rank_from_rating(winner_new)
                    old_rank_loser = get_rank_from_rating(loser_old)
                    new_rank_loser = get_rank_from_rating(loser_new)
                    
                    # Extract tier name (e.g., "Silver" from "Silver II")
                    def get_tier_name(rank_str):
                        return rank_str.split()[0] if rank_str else ""
                    
                    old_tier_winner = get_tier_name(old_rank_winner)
                    new_tier_winner = get_tier_name(new_rank_winner)
                    old_tier_loser = get_tier_name(old_rank_loser)
                    new_tier_loser = get_tier_name(new_rank_loser)
                    
                    # Send rank-up celebration for winner
                    if old_tier_winner != new_tier_winner and new_tier_winner:
                        celebration = get_rank_up_message(new_tier_winner, winner_name, winner_id, winner_new)
                        if celebration:
                            await asyncio.sleep(1)  # Small delay after rating message
                            await context.bot.send_message(
                                chat_id=query.message.chat_id,
                                text=celebration,
                                parse_mode=ParseMode.HTML
                            )
                    
                    # Send rank-up celebration for loser (if they ranked up somehow)
                    if old_tier_loser != new_tier_loser and new_tier_loser:
                        celebration = get_rank_up_message(new_tier_loser, loser_name, loser_id, loser_new)
                        if celebration:
                            await asyncio.sleep(1)
                            await context.bot.send_message(
                                chat_id=query.message.chat_id,
                                text=celebration,
                                parse_mode=ParseMode.HTML
                            )
                    
                except Exception as rating_error:
                    logger.error(f"Error sending rating message: {rating_error}", exc_info=True)
                    
            except Exception as e:
                logger.error(f"Error updating ranked match ratings: {e}", exc_info=True)
        
        # NOTE: Career/ranking updates happen ONLY in /ranked matches (Phase 2)
        # Regular /gameon matches DO NOT affect ratings

    except Exception as e:
        logger.error(f"Error in handle_game_end: {e}", exc_info=True)
        # Send simplified error message if formatting fails
        await query.message.edit_text(
            "🏏 *Game Complete\\!*\n\n"
            "❗ Some details couldn't be displayed\n"
            "Use /save to save this match",
            parse_mode=ParseMode.MARKDOWN_V2
        )

# --- Admin Commands ---
async def add_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add a group with persistence"""
    if not check_admin(str(update.effective_user.id)):
        await update.message.reply_text("❌ Unauthorized")
        return
    
    if not context.args:
        await update.message.reply_text("Usage: /addgroup <group_id>")
        return
    
    AUTHORIZED_GROUPS.add(int(context.args[0]))  
    await update.message.reply_text("✅ Group added to authorized list")

async def remove_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove a group from authorized list with improved error handling"""
    if not check_admin(str(update.effective_user.id)):
        await update.message.reply_text("❌ Unauthorized")
        return
        
    if not context.args:
        await update.message.reply_text(
            escape_markdown_v2_custom("*Usage:* /removegroup <group_id>"),
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return
        
    try:
        group_id = int(context.args[0])
        if group_id not in AUTHORIZED_GROUPS:
            await update.message.reply_text(
                escape_markdown_v2_custom("❌ Group not found in authorized list!"),
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return
            
        AUTHORIZED_GROUPS.remove(group_id)
        await update.message.reply_text(
            escape_markdown_v2_custom("✅ Group removed successfully!"),
            parse_mode=ParseMode.MARKDOWN_V2
        )
        
    except ValueError:
        await update.message.reply_text(
            escape_markdown_v2_custom("❌ Invalid group ID format!"),
            parse_mode=ParseMode.MARKDOWN_V2
        )
    except Exception as e:
        logger.error(f"Error removing group: {e}")
        await update.message.reply_text(
            escape_markdown_v2_custom("❌ Error removing group!"),
            parse_mode=ParseMode.MARKDOWN_V2
        )

# Merge broadcast_message() and broadcast() into one function
async def get_bot_members() -> dict:
    """Get all users and groups where bot is present"""
    try:
        members = {
            'users': set(),  # Store user IDs and names
            'groups': set(), # Store group IDs and names
            'details': {}    # Store detailed info about users/groups
        }
        
        # Get users from database
        conn = get_db_connection()
        if conn:
            with conn.cursor() as cur:
                # Get registered users
                cur.execute("""
                    SELECT telegram_id, username, first_name 
                    FROM users
                    WHERE is_banned = FALSE
                """)
                for user in cur.fetchall():
                    members['users'].add(user[0])
                    members['details'][user[0]] = {
                        'type': 'user',
                        'username': user[1],
                        'name': user[2],
                        'link': f"@{user[1]}" if user[1] else f"tg://user?id={user[0]}"
                    }
                
                # Get authorized groups
                cur.execute("""
                    SELECT group_id, group_name
                    FROM authorized_groups 
                    WHERE is_active = TRUE
                """)
                for group in cur.fetchall():
                    members['groups'].add(group[0])
                    members['details'][group[0]] = {
                        'type': 'group',
                        'name': group[1],
                        'link': f"tg://group?id={group[0]}"
                    }
                    
        return members
    except Exception as e:
        logger.error(f"Error getting bot members: {e}")
        return {'users': set(), 'groups': set(), 'details': {}}

# Update broadcast function to use new member list
async def broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Broadcast a message to all users and groups"""
    if not check_admin(str(update.effective_user.id)):
        await update.message.reply_text("❌ Unauthorized")
        return

    user = update.effective_user
    await send_admin_log(
        f"CMD: /broadcast by {user.first_name} (@{user.username or 'no_username'}, ID: {user.id})",
        log_type="command",
        chat_context=get_chat_context(update)
    )

    # Only proceed if message is replied to
    if not update.message.reply_to_message:
        await update.message.reply_text(
            escape_markdown_v2_custom("Please reply to a message to broadcast it"),
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return

    status_msg = await update.message.reply_text("📢 Broadcasting message...")
    user_success = 0
    user_failed = 0
    group_success = 0
    group_failed = 0

    try:
        conn = get_db_connection()
        if not conn:
            await status_msg.edit_text("❌ Database connection failed")
            return

        with conn.cursor() as cur:
            # Get all active users
            cur.execute("SELECT telegram_id FROM users WHERE is_banned = FALSE")
            users = [row[0] for row in cur.fetchall()]

            # Broadcast to users
            for user_id in users:
                try:
                    await context.bot.copy_message(
                        chat_id=user_id,
                        from_chat_id=update.effective_chat.id,
                        message_id=update.message.reply_to_message.message_id
                    )
                    user_success += 1
                    await asyncio.sleep(0.05)  # Rate limiting
                except Exception as e:
                    user_failed += 1
                    logger.error(f"Failed to send to user {user_id}: {e}")
            
            # Broadcast to groups from database
            cur.execute("SELECT group_id FROM authorized_groups WHERE is_active = TRUE")
            groups = [row[0] for row in cur.fetchall()]
            
            for group_id in groups:
                try:
                    await context.bot.copy_message(
                        chat_id=group_id,
                        from_chat_id=update.effective_chat.id,
                        message_id=update.message.reply_to_message.message_id
                    )
                    group_success += 1
                    await asyncio.sleep(0.05)  # Rate limiting
                except Exception as e:
                    group_failed += 1
                    logger.error(f"Failed to send to group {group_id}: {e}")

            await status_msg.edit_text(
                escape_markdown_v2_custom(
                    f"📢 Broadcast Complete\n\n"
                    f"👥 Users:\n"
                    f"✅ Success: {user_success}\n"
                    f"❌ Failed: {user_failed}\n\n"
                    f"👥 Groups:\n"
                    f"✅ Success: {group_success}\n"
                    f"❌ Failed: {group_failed}"
                ),
                parse_mode=ParseMode.MARKDOWN_V2
            )
    except Exception as e:
        logger.error(f"Broadcast error: {e}")
        await status_msg.edit_text(
            escape_markdown_v2_custom("❌ Broadcast failed"),
            parse_mode=ParseMode.MARKDOWN_V2
        )
    finally:
        if conn:
            return_db_connection(conn)

# Replace both stats and botstats with this enhanced version
@check_blacklist()
async def botstats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show comprehensive bot statistics"""
    if not check_admin(str(update.effective_user.id)):
        await update.message.reply_text("❌ Unauthorized")
        return
    
    user = update.effective_user
    await send_admin_log(
        f"CMD: /botstats by {user.first_name} (@{user.username or 'no_username'}, ID: {user.id})",
        log_type="command",
        chat_context=get_chat_context(update)
    )
    
    try:
        conn = get_db_connection()
        if not conn:
            await update.message.reply_text("❌ Database connection error")
            return

        with conn.cursor() as cur:
            # Get user stats
            cur.execute("SELECT COUNT(*) FROM users")
            total_users = cur.fetchone()[0] or 0
            
            cur.execute("SELECT COUNT(*) FROM users WHERE is_banned = TRUE")
            banned_users = cur.fetchone()[0] or 0
            
            # Get match stats
            cur.execute("SELECT COUNT(*) FROM scorecards")
            total_matches = cur.fetchone()[0] or 0
            
            # Get career stats
            cur.execute("SELECT COUNT(*) FROM career_stats")
            ranked_players = cur.fetchone()[0] or 0
            
            # Current active stats
            active_games = len(games)
            queue_size = len(ranked_queue)
            registered_users = len(REGISTERED_USERS)
            admins_count = len(BOT_ADMINS)
            groups_count = len(AUTHORIZED_GROUPS)

            stats_msg = (
                f"📊 *BOT STATISTICS*\n"
                f"━━━━━━━━━━━━━━━━\n\n"
                f"*👥 USERS*\n"
                f"• Total Registered: {registered_users}\n"
                f"• Database Users: {total_users}\n"
                f"• Banned: {banned_users}\n\n"
                f"*🎮 MATCHES*\n"
                f"• Total Played: {total_matches}\n"
                f"• Ranked Players: {ranked_players}\n\n"
                f"*⚡ LIVE STATUS*\n"
                f"• Active Games: {active_games}\n"
                f"• Queue Size: {queue_size}\n\n"
                f"*⚙️ CONFIGURATION*\n"
                f"• Admins: {admins_count}\n"
                f"• Auth Groups: {groups_count}\n"
                f"• Test Mode: {'ON' if TEST_MODE else 'OFF'}\n"
                f"• Maintenance: {'ON' if MAINTENANCE_MODE else 'OFF'}"
            )

            await update.message.reply_text(
                escape_markdown_v2_custom(stats_msg),
                parse_mode=ParseMode.MARKDOWN_V2
            )
            
    except Exception as e:
        logger.error(f"Error in botstats: {e}")
        await update.message.reply_text("❌ Error fetching statistics")
    finally:
        if conn:
            return_db_connection(conn)

# ========================================
# NEW ADMIN COMMANDS - USER & GROUP MANAGEMENT
# ========================================

@check_blacklist()
async def listusers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all registered users"""
    if not check_admin(str(update.effective_user.id)):
        await update.message.reply_text("❌ Unauthorized")
        return
    
    user = update.effective_user
    await send_admin_log(
        f"CMD: /listusers by {user.first_name} (@{user.username or 'no_username'}, ID: {user.id})",
        log_type="command",
        chat_context=get_chat_context(update)
    )
    
    try:
        conn = get_db_connection()
        if not conn:
            await update.message.reply_text("❌ Database connection error")
            return

        with conn.cursor() as cur:
            # Get total users count
            cur.execute("SELECT COUNT(*) FROM users WHERE is_banned = FALSE")
            total_users = cur.fetchone()[0]
            
            # Get users with stats
            cur.execute("""
                SELECT u.telegram_id, u.username, u.first_name, 
                       cs.rating, cs.rank_tier, cs.total_matches
                FROM users u
                LEFT JOIN career_stats cs ON u.telegram_id = cs.user_id
                WHERE u.is_banned = FALSE
                ORDER BY cs.rating DESC NULLS LAST
                LIMIT 20
            """)
            users = cur.fetchall()
            
            msg = f"👥 *REGISTERED USERS* ({total_users} total)\n"
            msg += "━━━━━━━━━━━━━━━━\n\n"
            
            for i, user_data in enumerate(users, 1):
                user_id, username, first_name, rating, rank, matches = user_data
                
                # Escape special characters for Markdown
                first_name_safe = first_name.replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace('`', '\\`') if first_name else "Unknown"
                username_str = f"@{username}" if username else "No username"
                rating_str = f"{rating} ({rank})" if rating else "Not ranked"
                matches_str = f"{matches}M" if matches else "0M"
                
                msg += f"{i}. {first_name_safe}\n"
                msg += f"   {username_str} | ID: `{user_id}`\n"
                msg += f"   {rating_str} | Matches: {matches_str}\n\n"
            
            if total_users > 20:
                msg += f"\n_Showing top 20 of {total_users} users_"
            
            await update.message.reply_text(
                msg,
                parse_mode=ParseMode.MARKDOWN
            )
            
    except Exception as e:
        logger.error(f"Error in listusers: {e}")
        await update.message.reply_text("❌ Error fetching users")
    finally:
        if conn:
            return_db_connection(conn)

@check_blacklist()
async def listgroups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all authorized groups"""
    if not check_admin(str(update.effective_user.id)):
        await update.message.reply_text("❌ Unauthorized")
        return
    
    user = update.effective_user
    await send_admin_log(
        f"CMD: /listgroups by {user.first_name} (@{user.username or 'no_username'}, ID: {user.id})",
        log_type="command",
        chat_context=get_chat_context(update)
    )
    
    try:
        conn = get_db_connection()
        if not conn:
            await update.message.reply_text("❌ Database connection error")
            return

        with conn.cursor() as cur:
            # Get all groups
            cur.execute("""
                SELECT group_id, group_name, added_by, is_active, added_at
                FROM authorized_groups
                ORDER BY added_at DESC
            """)
            groups = cur.fetchall()
            
            if not groups:
                await update.message.reply_text("📢 No groups found in database")
                return
            
            active_groups = [g for g in groups if g[3]]
            inactive_groups = [g for g in groups if not g[3]]
            
            msg = f"📢 *AUTHORIZED GROUPS*\n"
            msg += "━━━━━━━━━━━━━━━━\n\n"
            
            msg += f"🟢 *Active Groups* ({len(active_groups)})\n"
            for group in active_groups:
                group_id, group_name, added_by, is_active, added_at = group
                msg += f"• {group_name}\n"
                msg += f"  ID: `{group_id}`\n"
                msg += f"  Added: {added_at.strftime('%Y-%m-%d')}\n\n"
            
            if inactive_groups:
                msg += f"\n🔴 *Inactive Groups* ({len(inactive_groups)})\n"
                for group in inactive_groups:
                    group_id, group_name, _, _, _ = group
                    msg += f"• {group_name} (`{group_id}`)\n"
            
            await update.message.reply_text(
                msg,
                parse_mode=ParseMode.MARKDOWN
            )
            
    except Exception as e:
        logger.error(f"Error in listgroups: {e}")
        await update.message.reply_text("❌ Error fetching groups")
    finally:
        if conn:
            return_db_connection(conn)

@check_blacklist()
async def scangroups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show instructions for auto-tracking groups"""
    if not check_admin(str(update.effective_user.id)):
        await update.message.reply_text("❌ Unauthorized")
        return
    
    user = update.effective_user
    await send_admin_log(
        f"CMD: /scangroups by {user.first_name} (@{user.username or 'no_username'}, ID: {user.id})",
        log_type="command",
        chat_context=get_chat_context(update)
    )
    
    try:
        conn = get_db_connection()
        if not conn:
            await update.message.reply_text("❌ Database connection error")
            return
        
        with conn.cursor() as cur:
            # Count active groups
            cur.execute("SELECT COUNT(*) FROM authorized_groups WHERE is_active = TRUE")
            active_count = cur.fetchone()[0]
            
            # Count total groups
            cur.execute("SELECT COUNT(*) FROM authorized_groups")
            total_count = cur.fetchone()[0]
        
        msg = (
            "🔍 *GROUP AUTO-TRACKING*\n\n"
            f"📊 Current Status:\n"
            f"• Active Groups: {active_count}\n"
            f"• Total Groups: {total_count}\n\n"
            "✅ *Auto-Tracking Enabled*\n"
            "Groups are automatically saved when:\n"
            "• Anyone uses ANY command in the group\n"
            "• Bot is added to new groups\n\n"
            "💡 *To Register Existing Groups:*\n"
            "1. Go to each group\n"
            "2. Send ANY command (like /help)\n"
            "3. Group is auto-saved instantly!\n\n"
            "Use /listgroups to see all saved groups."
        )
        
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
        
    except Exception as e:
        logger.error(f"Error in scangroups: {e}")
        await update.message.reply_text("❌ Error checking groups")
    finally:
        if conn:
            return_db_connection(conn)

@check_blacklist()
async def userstats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Quick stats about users and groups"""
    if not check_admin(str(update.effective_user.id)):
        await update.message.reply_text("❌ Unauthorized")
        return
    
    user = update.effective_user
    await send_admin_log(
        f"CMD: /userstats by {user.first_name} (@{user.username or 'no_username'}, ID: {user.id})",
        log_type="command",
        chat_context=get_chat_context(update)
    )
    
    try:
        conn = get_db_connection()
        if not conn:
            await update.message.reply_text("❌ Database connection error")
            return

        with conn.cursor() as cur:
            # Get user stats
            cur.execute("SELECT COUNT(*) FROM users WHERE is_banned = FALSE")
            total_users = cur.fetchone()[0]
            
            cur.execute("SELECT COUNT(*) FROM users WHERE is_banned = TRUE")
            banned_users = cur.fetchone()[0]
            
            cur.execute("SELECT COUNT(*) FROM career_stats WHERE total_matches > 0")
            active_players = cur.fetchone()[0]
            
            # Get group stats
            cur.execute("SELECT COUNT(*) FROM authorized_groups WHERE is_active = TRUE")
            active_groups = cur.fetchone()[0]
            
            cur.execute("SELECT COUNT(*) FROM authorized_groups WHERE is_active = FALSE")
            inactive_groups = cur.fetchone()[0]
            
            msg = "📊 *USER & GROUP STATS*\n"
            msg += "━━━━━━━━━━━━━━━━\n\n"
            msg += "*👥 Users*\n"
            msg += f"• Total Registered: {total_users}\n"
            msg += f"• Active Players: {active_players}\n"
            msg += f"• Banned: {banned_users}\n\n"
            msg += "*📢 Groups*\n"
            msg += f"• Active: {active_groups}\n"
            msg += f"• Inactive: {inactive_groups}\n"
            msg += f"• Total: {active_groups + inactive_groups}"
            
            await update.message.reply_text(
                msg,
                parse_mode=ParseMode.MARKDOWN
            )
            
    except Exception as e:
        logger.error(f"Error in userstats: {e}")
        await update.message.reply_text("❌ Error fetching stats")
    finally:
        if conn:
            return_db_connection(conn)

# ========================================
# ANTI-CHEAT ADMIN COMMANDS
# ========================================

@check_blacklist()
async def flaggedmatches(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """View all flagged suspicious activities"""
    if not check_admin(str(update.effective_user.id)):
        await update.message.reply_text("❌ Unauthorized")
        return
    
    user = update.effective_user
    await send_admin_log(
        f"CMD: /flaggedmatches by {user.first_name} (@{user.username or 'no_username'}, ID: {user.id})",
        log_type="command",
        chat_context=get_chat_context(update)
    )
    
    try:
        conn = get_db_connection()
        if not conn:
            await update.message.reply_text("❌ Database connection error")
            return
        
        with conn.cursor() as cur:
            # Get unreviewed flagged activities
            cur.execute("""
                SELECT id, user_id, activity_type, opponent_id, details,
                       trust_score_impact, flagged_at
                FROM suspicious_activities
                WHERE reviewed = FALSE
                ORDER BY flagged_at DESC
                LIMIT 10
            """)
            flags = cur.fetchall()
            
            if not flags:
                await update.message.reply_text(
                    escape_markdown_v2_custom("✅ No flagged activities to review!"),
                    parse_mode=ParseMode.MARKDOWN_V2
                )
                return
            
            message = f"🚨 *FLAGGED ACTIVITIES*\n━━━━━━━━━━━━━━━━\n\n"
            
            for flag_id, user_id, activity_type, opponent_id, details, impact, flagged_at in flags:
                message += (
                    f"*ID {flag_id}*\n"
                    f"• User: `{user_id}`\n"
                    f"• Type: {escape_markdown_v2_custom(activity_type)}\n"
                    f"• Opponent: `{opponent_id or 'N/A'}`\n"
                    f"• Impact: {impact}\n"
                    f"• Details: {escape_markdown_v2_custom(details[:50])}\\.\\.\\.\\n"
                    f"• Time: {escape_markdown_v2_custom(str(flagged_at))[:19]}\n\n"
                )
            
            message += f"_Use /reviewmatch <id> to review specific flag\\._"
            
            await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN_V2)
            
    except Exception as e:
        logger.error(f"Error in flaggedmatches: {e}")
        await update.message.reply_text("❌ Error fetching flagged matches")
    finally:
        if conn:
            return_db_connection(conn)

@check_blacklist()
async def reviewmatch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Review a specific flagged activity - Usage: /reviewmatch <flag_id>"""
    if not check_admin(str(update.effective_user.id)):
        await update.message.reply_text("❌ Unauthorized")
        return
    
    user = update.effective_user
    await send_admin_log(
        f"CMD: /reviewmatch by {user.first_name} (@{user.username or 'no_username'}, ID: {user.id})",
        log_type="command",
        chat_context=get_chat_context(update)
    )
    
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text(
            "📋 *Usage:* `/reviewmatch <flag_id>`",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return
    
    flag_id = int(context.args[0])
    
    try:
        conn = get_db_connection()
        if not conn:
            await update.message.reply_text("❌ Database connection error")
            return
        
        with conn.cursor() as cur:
            # Get flag details
            cur.execute("""
                SELECT user_id, activity_type, opponent_id, details,
                       trust_score_impact, flagged_at, reviewed
                FROM suspicious_activities
                WHERE id = %s
            """, (flag_id,))
            
            flag = cur.fetchone()
            if not flag:
                await update.message.reply_text(
                    escape_markdown_v2_custom(f"❌ Flag ID {flag_id} not found"),
                    parse_mode=ParseMode.MARKDOWN_V2
                )
                return
            
            user_id, activity_type, opponent_id, details, impact, flagged_at, reviewed = flag
            
            # Get user stats
            cur.execute("""
                SELECT username, trust_score, total_matches, rating, rating_suspended
                FROM career_stats cs
                JOIN users u ON u.telegram_id = cs.user_id
                WHERE cs.user_id = %s
            """, (user_id,))
            user_stats = cur.fetchone()
            
            # Get match history with this opponent
            if opponent_id:
                cur.execute("""
                    SELECT total_matches, wins, losses, matches_last_24h
                    FROM match_patterns
                    WHERE player_id = %s AND opponent_id = %s
                """, (user_id, opponent_id))
                pattern = cur.fetchone()
            else:
                pattern = None
            
            message = (
                f"🔍 *FLAG REVIEW \\#{flag_id}*\n"
                f"━━━━━━━━━━━━━━━━\n\n"
                f"*🚨 Activity Details*\n"
                f"• Type: {escape_markdown_v2_custom(activity_type)}\n"
                f"• User: `{user_id}`\n"
                f"• Opponent: `{opponent_id or 'N/A'}`\n"
                f"• Trust Impact: {impact}\n"
                f"• Flagged: {escape_markdown_v2_custom(str(flagged_at))[:19]}\n"
                f"• Status: {'✅ Reviewed' if reviewed else '⏳ Pending'}\n\n"
                f"*📋 Details*\n"
                f"{escape_markdown_v2_custom(details)}\n\n"
            )
            
            if user_stats:
                username, trust_score, total_matches, rating, suspended = user_stats
                message += (
                    f"*👤 User Stats*\n"
                    f"• Username: {escape_markdown_v2_custom(username or 'N/A')}\n"
                    f"• Trust Score: {trust_score}\n"
                    f"• Total Matches: {total_matches}\n"
                    f"• Rating: {rating}\n"
                    f"• Suspended: {'⛔ YES' if suspended else '✅ NO'}\n\n"
                )
            
            if pattern:
                total, wins, losses, recent = pattern
                message += (
                    f"*📊 Match Pattern*\n"
                    f"• Total vs Opponent: {total}\n"
                    f"• Wins: {wins} \\| Losses: {losses}\n"
                    f"• Last 24h: {recent}\n\n"
                )
            
            message += (
                f"*⚙️ Actions*\n"
                f"• `/clearflag {flag_id}` \\- Clear flag\n"
                f"• `/suspendrating {user_id}` \\- Suspend rating\n"
            )
            
            await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN_V2)
            
    except Exception as e:
        logger.error(f"Error in reviewmatch: {e}")
        await update.message.reply_text("❌ Error reviewing match")
    finally:
        if conn:
            return_db_connection(conn)

@check_blacklist()
async def clearflag(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Clear a false positive flag - Usage: /clearflag <flag_id>"""
    if not check_admin(str(update.effective_user.id)):
        await update.message.reply_text("❌ Unauthorized")
        return
    
    user = update.effective_user
    await send_admin_log(
        f"CMD: /clearflag by {user.first_name} (@{user.username or 'no_username'}, ID: {user.id})",
        log_type="command",
        chat_context=get_chat_context(update)
    )
    
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text(
            "📋 *Usage:* `/clearflag <flag_id>`",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return
    
    flag_id = int(context.args[0])
    admin_id = str(update.effective_user.id)
    
    try:
        conn = get_db_connection()
        if not conn:
            await update.message.reply_text("❌ Database connection error")
            return
        
        with conn.cursor() as cur:
            # Mark as reviewed and cleared
            cur.execute("""
                UPDATE suspicious_activities
                SET reviewed = TRUE,
                    cleared = TRUE,
                    reviewed_by = %s,
                    reviewed_at = NOW(),
                    admin_action = 'Cleared as false positive'
                WHERE id = %s
                RETURNING user_id, trust_score_impact
            """, (admin_id, flag_id))
            
            result = cur.fetchone()
            if not result:
                await update.message.reply_text(
                    escape_markdown_v2_custom(f"❌ Flag ID {flag_id} not found")
                )
                return
            
            user_id, trust_impact = result
            
            # Restore trust score
            if trust_impact < 0:
                cur.execute("""
                    UPDATE career_stats
                    SET trust_score = LEAST(100, trust_score - %s)
                    WHERE user_id = %s
                """, (trust_impact, user_id))
            
            conn.commit()
            
            await update.message.reply_text(
                escape_markdown_v2_custom(f"✅ Flag #{flag_id} cleared successfully!"),
                parse_mode=ParseMode.MARKDOWN_V2
            )
            
    except Exception as e:
        logger.error(f"Error in clearflag: {e}")
        await update.message.reply_text("❌ Error clearing flag")
    finally:
        if conn:
            return_db_connection(conn)

@check_blacklist()
async def suspendrating(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Suspend user's rating changes - Usage: /suspendrating <user_id> [reason]"""
    if not check_admin(str(update.effective_user.id)):
        await update.message.reply_text("❌ Unauthorized")
        return
    
    user = update.effective_user
    await send_admin_log(
        f"CMD: /suspendrating by {user.first_name} (@{user.username or 'no_username'}, ID: {user.id})",
        log_type="command",
        chat_context=get_chat_context(update)
    )
    
    if not context.args:
        await update.message.reply_text(
            "📋 *Usage:* `/suspendrating <user_id> [reason]`",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return
    
    user_id = context.args[0]
    reason = " ".join(context.args[1:]) if len(context.args) > 1 else "Admin action"
    
    try:
        conn = get_db_connection()
        if not conn:
            await update.message.reply_text("❌ Database connection error")
            return
        
        with conn.cursor() as cur:
            # Suspend rating
            cur.execute("""
                UPDATE career_stats
                SET rating_suspended = TRUE,
                    suspension_reason = %s
                WHERE user_id = %s
                RETURNING username
            """, (reason, user_id))
            
            result = cur.fetchone()
            if not result:
                await update.message.reply_text(
                    escape_markdown_v2_custom(f"❌ User {user_id} not found")
                )
                return
            
            conn.commit()
            
            await update.message.reply_text(
                escape_markdown_v2_custom(
                    f"⛔ Rating suspended for user {user_id}\n"
                    f"Reason: {reason}"
                ),
                parse_mode=ParseMode.MARKDOWN_V2
            )
            
    except Exception as e:
        logger.error(f"Error in suspendrating: {e}")
        await update.message.reply_text("❌ Error suspending rating")
    finally:
        if conn:
            return_db_connection(conn)

@check_blacklist()
async def unsuspendrating(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove rating suspension - Usage: /unsuspendrating <user_id>"""
    if not check_admin(str(update.effective_user.id)):
        await update.message.reply_text("❌ Unauthorized")
        return
    
    user = update.effective_user
    await send_admin_log(
        f"CMD: /unsuspendrating by {user.first_name} (@{user.username or 'no_username'}, ID: {user.id})",
        log_type="command",
        chat_context=get_chat_context(update)
    )
    
    if not context.args:
        await update.message.reply_text(
            "📋 *Usage:* `/unsuspendrating <user_id>`",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return
    
    user_id = context.args[0]
    
    try:
        conn = get_db_connection()
        if not conn:
            await update.message.reply_text("❌ Database connection error")
            return
        
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE career_stats
                SET rating_suspended = FALSE,
                    suspension_reason = NULL
                WHERE user_id = %s
                RETURNING username
            """, (user_id,))
            
            result = cur.fetchone()
            if not result:
                await update.message.reply_text(
                    escape_markdown_v2_custom(f"❌ User {user_id} not found")
                )
                return
            
            conn.commit()
            
            await update.message.reply_text(
                escape_markdown_v2_custom(f"✅ Rating suspension removed for user {user_id}"),
                parse_mode=ParseMode.MARKDOWN_V2
            )
            
    except Exception as e:
        logger.error(f"Error in unsuspendrating: {e}")
        await update.message.reply_text("❌ Error removing suspension")
    finally:
        if conn:
            return_db_connection(conn)

# Add persistent data storage
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    # Log command usage
    await send_admin_log(
        f"CMD: /start by {user.first_name} (@{user.username or 'no_username'}, ID: {user.id})",
        log_type="command",
        chat_context=get_chat_context(update)
    )
    
    # Check if user is member of required channels
    is_member, not_joined = await check_user_membership(user.id, context)
    
    if not is_member:
        # User hasn't joined required channels
        keyboard = [
            [
                InlineKeyboardButton("📢 Join Official Channel", url=CHANNEL_LINKS['official']),
                InlineKeyboardButton("💬 Join Community", url=CHANNEL_LINKS['community'])
            ],
            [
                InlineKeyboardButton("✅ I've Joined - Verify", callback_data="verify_subscription")
            ]
        ]
        
        await update.message.reply_text(
            escape_markdown_v2_custom(
                "🏏 Welcome to Cricket Saga!"
                "\n\n"
                "⚠️ To use this bot, you must join our channels:"
                "\n\n"
                "📢 Saga Arena | Official"
                "\n"
                "💬 Saga Arena • Community"
                "\n\n"
                "After joining both channels, click the 'I've Joined' button below to verify."
            ),
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return
    
    # Show initial message
    msg = await update.message.reply_text("🎮 Setting up your account...")

    try:
        # Try database registration first
        if db:
            success = db.register_user(
                telegram_id=user.id,
                username=user.username,
                first_name=user.first_name
            )
        else:
            # Fallback to in-memory registration
            success = True
            REGISTERED_USERS.add(str(user.id))
        
        if success:
            REGISTERED_USERS.add(str(user.id))
            
            welcome_message = (
                f"🎮  *CRICKET SAGA*  🎮\n"
                f"═══════════════════\n\n"
                f"👋 *Welcome, {escape_markdown_v2_custom(user.first_name)}\\!*\n\n"
                f"Ready to step onto the pitch\\?\n\n"
                f"🏏 *Quick Match*  •  Practice your shots\n"
                f"🏆 *Ranked*       •  Climb the ladder\n"
                f"📊 *Career*       •  Track your stats\n\n"
                f"👇 *Get Started:*\n"
                f"/gameon \\- Start a Match\n"
                f"/help   \\- View Commands"
            )

            
            await msg.edit_text(
                welcome_message,
                parse_mode=ParseMode.MARKDOWN_V2
            )
        else:
            raise Exception("Registration failed")
            
    except Exception as e:
        logger.error(f"Error in start command: {e}")
        # Add user to in-memory storage as fallback
        REGISTERED_USERS.add(str(user.id))
        await msg.edit_text(
            escape_markdown_v2_custom(
                f"*⚠️ Welcome, {user.first_name}!*👋\n\n"
                "*Registration partially completed.*🤔\n"
                "*Some features may be limited.*🚫\n\n"
                "*📌 Available Commands:*📚\n"
                "🏏 /gameon - Start a new match\n"
                "❓ /help - View commands"
            ),
            parse_mode=ParseMode.MARKDOWN_V2
        )


# --- Help Command ---
@require_subscription
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Display comprehensive help information"""
    user = update.effective_user
    await send_admin_log(
        f"CMD: /help by {user.first_name} (@{user.username or 'no_username'}, ID: {user.id})",
        log_type="command",
        chat_context=get_chat_context(update)
    )
    
    help_text = (
        "📚  *COMMAND CENTER*\n"
        "══════════════════\n\n"
        "🎮 *MATCHES*\n"
        "• /gameon   \\- Start Match / Practice\n"
        "• /ranked   \\- Join Ranked Queue\n"
        "• /challenge \\- Challenge Player\n\n"
        "👤 *PROFILE*\n"
        "• /profile  \\- Your Stats\n"
        "• /career   \\- Rank & Rating\n\n"
        "🏆 *LEADERBOARDS*\n"
        "• /leaderboard \\- Top Players\n"
        "• /ranks       \\- Tier Info"
    )
    
    await update.message.reply_text(
        help_text,
        parse_mode=ParseMode.MARKDOWN_V2
    )

# --- Admin Functions ---
async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add a new admin user - accepts user_id or username or reply"""
    if not check_admin(str(update.effective_user.id)):
        await update.message.reply_text("❌ Unauthorized")
        return
    
    user = update.effective_user
    await send_admin_log(
        f"CMD: /addadmin by {user.first_name} (@{user.username or 'no_username'}, ID: {user.id})",
        log_type="command",
        chat_context=get_chat_context(update)
    )
    
    admin_id = None
    
    # Check if replying to a message
    if update.message.reply_to_message:
        admin_id = str(update.message.reply_to_message.from_user.id)
    elif context.args:
        arg = context.args[0]
        # Remove @ if username provided
        if arg.startswith('@'):
            try:
                # Try to get user by username
                chat = await context.bot.get_chat(arg)
                admin_id = str(chat.id)
            except Exception as e:
                await update.message.reply_text(f"❌ Could not find user: {arg}")
                return
        else:
            # Assume it's a user ID
            admin_id = arg
    else:
        await update.message.reply_text(
            "Usage:\n"
            "/addadmin <user_id>\n"
            "/addadmin @username\n"
            "Or reply to a user's message with /addadmin"
        )
        return
    
    BOT_ADMINS.add(admin_id)
    await update.message.reply_text(f"✅ Admin added: {admin_id}")

async def stop_games(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stop all active games and clear queues"""
    if not check_admin(str(update.effective_user.id)):
        await update.message.reply_text("❌ Unauthorized")
        return
    
    user = update.effective_user
    await send_admin_log(
        f"CMD: /stopgames by {user.first_name} (@{user.username or 'no_username'}, ID: {user.id})",
        log_type="command",
        chat_context=get_chat_context(update)
    )
    
    game_count = len(games)
    queue_count = len(ranked_queue)
    
    games.clear()
    ranked_queue.clear()
    
    await update.message.reply_text(
        f"🛑 *ALL GAMES STOPPED*\n"
        f"━━━━━━━━━━━━━━━━\n\n"
        f"• Games cleared: {game_count}\n"
        f"• Queue cleared: {queue_count}",
        parse_mode=ParseMode.MARKDOWN_V2
    )

async def force_remove_player(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to forcefully remove a player from queue/matches/challenges"""
    if not check_admin(str(update.effective_user.id)):
        await update.message.reply_text("❌ Unauthorized")
        return
    
    admin_user = update.effective_user
    await send_admin_log(
        f"CMD: /forceremove by {admin_user.first_name} (@{admin_user.username or 'no_username'}, ID: {admin_user.id})",
        log_type="command",
        chat_context=get_chat_context(update)
    )
    
    # Check args
    if not context.args:
        await update.message.reply_text(
            "📋 *FORCE REMOVE PLAYER*\n"
            "━━━━━━━━━━━━━━━━\n\n"
            "*Usage:*\n"
            "`/forceremove <user_id>`\n\n"
            "*Example:*\n"
            "`/forceremove 123456789`\n\n"
            "This will remove the player from:\n"
            "• Ranked queue\n"
            "• Active games\n"
            "• Pending challenges\n"
            "• Challenge cooldowns",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return
    
    try:
        target_user_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid user ID\\! Must be a number\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return
    
    removed_items = []
    
    # 1. Remove from ranked queue
    if target_user_id in ranked_queue:
        username = ranked_queue[target_user_id].get('username', 'Unknown')
        await remove_from_ranked_queue(target_user_id)
        removed_items.append(f"Ranked queue ({username})")
        logger.info(f"👮 Admin force-removed {username} (ID: {target_user_id}) from ranked queue")
    
    # 2. Remove from active games
    games_removed = 0
    for game_id, game in list(games.items()):
        if game.get('creator') == target_user_id or game.get('joiner') == target_user_id:
            del games[game_id]
            games_removed += 1
    if games_removed > 0:
        removed_items.append(f"{games_removed} active game(s)")
        logger.info(f"👮 Admin force-removed user {target_user_id} from {games_removed} active game(s)")
    
    # 3. Remove pending challenges (as challenger or target)
    try:
        conn = get_db_connection()
        if conn:
            try:
                with conn.cursor() as cur:
                    # Count pending challenges
                    cur.execute("""
                        SELECT COUNT(*) FROM pending_challenges
                        WHERE (challenger_id = %s OR target_id = %s)
                        AND status = 'pending'
                    """, (target_user_id, target_user_id))
                    challenges_count = cur.fetchone()[0]
                    
                    if challenges_count > 0:
                        # Delete pending challenges
                        cur.execute("""
                            DELETE FROM pending_challenges
                            WHERE (challenger_id = %s OR target_id = %s)
                            AND status = 'pending'
                        """, (target_user_id, target_user_id))
                        conn.commit()
                        removed_items.append(f"{challenges_count} pending challenge(s)")
                        logger.info(f"👮 Admin force-removed {challenges_count} pending challenges for user {target_user_id}")
                    
                    # 4. Clear challenge cooldowns
                    cur.execute("""
                        DELETE FROM challenge_cooldowns
                        WHERE challenger_id = %s OR target_id = %s
                    """, (target_user_id, target_user_id))
                    cooldowns_removed = cur.rowcount
                    if cooldowns_removed > 0:
                        conn.commit()
                        removed_items.append(f"{cooldowns_removed} cooldown(s)")
                        logger.info(f"👮 Admin cleared {cooldowns_removed} challenge cooldowns for user {target_user_id}")
                        
            finally:
                return_db_connection(conn)
    except Exception as e:
        logger.error(f"Error removing challenges/cooldowns: {e}")
    
    # Send result
    if removed_items:
        items_list = "\n".join([f"• {item}" for item in removed_items])
        result_msg = (
            f"✅ *PLAYER FORCEFULLY REMOVED*\n"
            f"━━━━━━━━━━━━━━━━\n\n"
            f"*User ID:* `{target_user_id}`\n\n"
            f"*Removed from:*\n"
            f"{escape_markdown_v2_custom(items_list)}"
        )
        await send_admin_log(
            f"✅ Force-removed user {target_user_id}\n" + "\n".join(removed_items),
            log_type="success",
            chat_context=get_chat_context(update)
        )
    else:
        result_msg = (
            f"ℹ️ *NO ACTION NEEDED*\n"
            f"━━━━━━━━━━━━━━━━\n\n"
            f"*User ID:* `{target_user_id}`\n\n"
            f"Player is not in any queue, match, or challenge\\."
        )
    
    await update.message.reply_text(result_msg, parse_mode=ParseMode.MARKDOWN_V2)

async def reset_all_ratings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to reset all player ratings to 1000 for tournament"""
    if not check_admin(str(update.effective_user.id)):
        await update.message.reply_text("❌ Unauthorized")
        return
    
    admin_user = update.effective_user
    await send_admin_log(
        f"CMD: /resetratings by {admin_user.first_name} (@{admin_user.username or 'no_username'}, ID: {admin_user.id})",
        log_type="command",
        chat_context=get_chat_context(update)
    )
    
    # Confirmation check
    if not context.args or context.args[0].lower() != "confirm":
        await update.message.reply_text(
            "⚠️ *RESET ALL RATINGS*\n"
            "━━━━━━━━━━━━━━━━\n\n"
            "This will reset ALL players' ratings to:\n"
            "• Rating: 1000 \\(Silver III\\)\n"
            "• Wins/Losses: Unchanged\n"
            "• Match history: Preserved\n\n"
            "⚠️ *This action cannot be undone\\!*\n\n"
            "To confirm, use:\n"
            "`/resetratings confirm`",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return
    
    try:
        conn = get_db_connection()
        if not conn:
            await update.message.reply_text(
                "❌ Database connection failed\\!",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return
        
        try:
            with conn.cursor() as cur:
                # Count players before reset
                cur.execute("SELECT COUNT(*) FROM career_stats")
                total_players = cur.fetchone()[0]
                
                # Reset ALL stats to default tournament state
                cur.execute("""
                    UPDATE career_stats 
                    SET rating = 1000,
                        rank_tier = '🥈 Silver III',
                        total_matches = 0,
                        wins = 0,
                        losses = 0,
                        current_streak = 0,
                        highest_rating = 1000,
                        streak_type = NULL,
                        updated_at = CURRENT_TIMESTAMP
                """)
                
                affected_rows = cur.rowcount
                conn.commit()
                
                logger.info(f"🔄 Admin reset ALL stats for {affected_rows} players")
                
                result_msg = (
                    f"✅ *COMPLETE STATS RESET*\n"
                    f"━━━━━━━━━━━━━━━━\n\n"
                    f"• Total players: {total_players}\n"
                    f"• Players reset: {affected_rows}\n\n"
                    f"*Reset to defaults:*\n"
                    f"• Rating: 1000 \\(Silver III\\)\n"
                    f"• Wins: 0\n"
                    f"• Losses: 0\n"
                    f"• Matches: 0\n"
                    f"• Streak: 0\n\n"
                    f"✅ All players ready for tournament\\!"
                )
                
                await send_admin_log(
                    f"✅ Complete stats reset for {affected_rows} players\n"
                    f"Rating: 1000, Wins: 0, Losses: 0, Matches: 0\n"
                    f"Total players: {total_players}",
                    log_type="success",
                    chat_context=get_chat_context(update)
                )
                
        finally:
            return_db_connection(conn)
            
        await update.message.reply_text(result_msg, parse_mode=ParseMode.MARKDOWN_V2)
        
    except Exception as e:
        logger.error(f"Error resetting ratings: {e}")
        await update.message.reply_text(
            f"❌ Error resetting ratings: {escape_markdown_v2_custom(str(e))}",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        await send_admin_log(
            f"❌ Error resetting ratings: {str(e)}",
            log_type="error",
            chat_context=get_chat_context(update)
        )

async def recent_matches(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show last 10 matches of a player"""
    user = update.effective_user
    await send_admin_log(
        f"CMD: /recent by {user.first_name} (@{user.username or 'no_username'}, ID: {user.id})",
        log_type="command",
        chat_context=get_chat_context(update)
    )
    
    # Determine target user
    # Priority: 1. Reply to message, 2. username/@username/user_id, 3. Self
    if update.message.reply_to_message:
        # Check if replying to a user's message
        replied_user = update.message.reply_to_message.from_user
        target_user_id = str(replied_user.id)
        target_username = replied_user.first_name
    elif context.args:
        search_term = context.args[0]
        # Remove @ if present
        if search_term.startswith('@'):
            search_term = search_term[1:]
        
        # Try to find user by username or user_id
        try:
            conn = get_db_connection()
            if not conn:
                await update.message.reply_text("❌ Database connection failed!")
                return
            
            with conn.cursor(cursor_factory=DictCursor) as cur:
                # Check if it's a numeric ID or username
                if search_term.isdigit():
                    # Search by user_id
                    cur.execute("""
                        SELECT user_id, username FROM career_stats 
                        WHERE user_id = %s
                        LIMIT 1
                    """, (search_term,))
                else:
                    # Search by username
                    cur.execute("""
                        SELECT user_id, username FROM career_stats 
                        WHERE LOWER(username) = LOWER(%s)
                        LIMIT 1
                    """, (search_term,))
                
                user_result = cur.fetchone()
                
                if not user_result:
                    await update.message.reply_text(
                        f"❌ User `{escape_markdown_v2_custom(search_term)}` not found\\!",
                        parse_mode=ParseMode.MARKDOWN_V2
                    )
                    return_db_connection(conn)
                    return
                
                target_user_id = str(user_result['user_id'])
                target_username = user_result['username']
            return_db_connection(conn)
        except Exception as e:
            logger.error(f"Error finding user: {e}")
            await update.message.reply_text("❌ Error finding user!")
            return
    else:
        target_user_id = str(user.id)
        target_username = user.first_name
    
    try:
        conn = get_db_connection()
        if not conn:
            await update.message.reply_text("❌ Database connection failed!")
            return
        
        with conn.cursor(cursor_factory=DictCursor) as cur:
            # Get last 10 matches
            cur.execute("""
                SELECT 
                    player1_id, player2_id, winner_id,
                    p1_rating_before, p1_rating_after, p1_rating_change,
                    p2_rating_before, p2_rating_after, p2_rating_change,
                    p1_score, p1_wickets, p1_overs,
                    p2_score, p2_wickets, p2_overs,
                    match_date
                FROM ranked_matches
                WHERE player1_id = %s OR player2_id = %s
                ORDER BY match_date DESC
                LIMIT 10
            """, (target_user_id, target_user_id))
            matches = cur.fetchall()
            
            # Get current stats
            cur.execute("""
                SELECT rating, rank_tier, total_matches, wins, losses
                FROM career_stats WHERE user_id = %s
            """, (target_user_id,))
            stats = cur.fetchone()
            
            # Get usernames for opponents
            opponent_ids = set()
            for match in matches:
                if str(match['player1_id']) != target_user_id:
                    opponent_ids.add(match['player1_id'])
                if str(match['player2_id']) != target_user_id:
                    opponent_ids.add(match['player2_id'])
            
            # Fetch opponent names
            opponent_names = {}
            if opponent_ids:
                cur.execute("""
                    SELECT user_id, username FROM career_stats
                    WHERE user_id = ANY(%s)
                """, (list(opponent_ids),))
                for row in cur.fetchall():
                    opponent_names[str(row['user_id'])] = row['username']
        
        return_db_connection(conn)
        
        if not matches:
            await update.message.reply_text(
                f"📊 *MATCH HISTORY*\n"
                f"━━━━━━━━━━━━━━━━\n\n"
                f"No ranked matches found for {escape_markdown_v2_custom(target_username)}\\!",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return
        
        # Build message
        current_rating = stats['rating'] if stats else 1000
        current_tier = stats['rank_tier'] if stats else "Silver III"
        wins = stats['wins'] if stats else 0
        losses = stats['losses'] if stats else 0
        
        msg = (
            f"📊 *MATCH HISTORY*\n"
            f"━━━━━━━━━━━━━━━━\n\n"
            f"*Player:* {escape_markdown_v2_custom(target_username)}\n"
            f"*Current Rating:* {current_rating} \\({escape_markdown_v2_custom(current_tier)}\\)\n"
            f"*Record:* {wins}W \\- {losses}L\n\n"
            f"*Last 10 Matches:*\n"
            f"━━━━━━━━━━━━━━━━\n\n"
        )
        
        for idx, match in enumerate(matches, 1):
            # Determine if target was player1 or player2
            is_player1 = str(match['player1_id']) == target_user_id
            
            opponent_id = str(match['player2_id']) if is_player1 else str(match['player1_id'])
            opponent_name = opponent_names.get(opponent_id, "Unknown")
            
            # Get target's stats for this match
            if is_player1:
                rating_before = match['p1_rating_before']
                rating_after = match['p1_rating_after']
                rating_change = match['p1_rating_change']
                target_score = match['p1_score']
                target_wickets = match['p1_wickets']
                opp_score = match['p2_score']
                opp_wickets = match['p2_wickets']
                won = str(match['winner_id']) == target_user_id
            else:
                rating_before = match['p2_rating_before']
                rating_after = match['p2_rating_after']
                rating_change = match['p2_rating_change']
                target_score = match['p2_score']
                target_wickets = match['p2_wickets']
                opp_score = match['p1_score']
                opp_wickets = match['p1_wickets']
                won = str(match['winner_id']) == target_user_id
            
            # Result emoji
            result_emoji = "✅" if won else "❌"
            
            # Format result - calculate differences as absolute values to avoid minus signs
            if won:
                if target_score > opp_score:
                    runs_diff = abs(target_score - opp_score)
                    result = f"Won by {runs_diff} runs"
                else:
                    wickets_remaining = 10 - target_wickets
                    result = f"Won by {wickets_remaining} wkts"
            else:
                if opp_score > target_score:
                    runs_diff = abs(opp_score - target_score)
                    result = f"Lost by {runs_diff} runs"
                else:
                    wickets_remaining = 10 - opp_wickets
                    result = f"Lost by {wickets_remaining} wkts"
            
            # Format rating change - escape the + or - sign
            if rating_change > 0:
                change_str = f"\\+{rating_change}"
            elif rating_change < 0:
                change_str = f"\\-{abs(rating_change)}"
            else:
                change_str = "0"
            
            match_date = match['match_date'].strftime("%d %b")
            
            msg += (
                f"{result_emoji} *Match {idx}* \\({escape_markdown_v2_custom(match_date)}\\)\n"
                f"vs {escape_markdown_v2_custom(opponent_name)}\n"
                f"Score: {target_score}/{target_wickets} vs {opp_score}/{opp_wickets}\n"
                f"{escape_markdown_v2_custom(result)}\n"
                f"Rating: {rating_before} \\→ {rating_after} \\({change_str}\\)\n\n"
            )
        
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN_V2)
        
    except Exception as e:
        logger.error(f"Error showing recent matches: {e}")
        await update.message.reply_text(
            f"❌ Error: {escape_markdown_v2_custom(str(e))}",
            parse_mode=ParseMode.MARKDOWN_V2
        )

async def set_player_rating(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to manually set a player's rating"""
    if not check_admin(str(update.effective_user.id)):
        await update.message.reply_text("❌ Unauthorized")
        return
    
    admin_user = update.effective_user
    await send_admin_log(
        f"CMD: /setrating by {admin_user.first_name} (@{admin_user.username or 'no_username'}, ID: {admin_user.id})",
        log_type="command",
        chat_context=get_chat_context(update)
    )
    
    # Check args
    if len(context.args) < 2:
        await update.message.reply_text(
            "📝 *SET PLAYER RATING*\n"
            "━━━━━━━━━━━━━━━━\n\n"
            "*Usage:*\n"
            "`/setrating <user_id> <rating>`\n\n"
            "*Example:*\n"
            "`/setrating 123456789 1500`\n\n"
            "This will set the player's rating to 1500 and update their rank tier accordingly\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return
    
    try:
        target_user_id = context.args[0]
        new_rating = int(context.args[1])
        
        if new_rating < 0 or new_rating > 10000:
            await update.message.reply_text(
                "❌ Rating must be between 0 and 10000\\!",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return
        
        conn = get_db_connection()
        if not conn:
            await update.message.reply_text("❌ Database connection failed\\!")
            return
        
        try:
            with conn.cursor(cursor_factory=DictCursor) as cur:
                # Check if user exists
                cur.execute("""
                    SELECT user_id, username, rating FROM career_stats
                    WHERE user_id = %s
                """, (target_user_id,))
                user_data = cur.fetchone()
                
                if not user_data:
                    await update.message.reply_text(
                        f"❌ User ID `{escape_markdown_v2_custom(target_user_id)}` not found in database\\!",
                        parse_mode=ParseMode.MARKDOWN_V2
                    )
                    return_db_connection(conn)
                    return
                
                old_rating = user_data['rating']
                username = user_data['username']
                new_tier = get_rank_tier(new_rating)
                
                # Update rating
                cur.execute("""
                    UPDATE career_stats
                    SET rating = %s,
                        rank_tier = %s,
                        highest_rating = GREATEST(highest_rating, %s),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = %s
                """, (new_rating, new_tier, new_rating, target_user_id))
                
                conn.commit()
                
                logger.info(f"🔧 Admin manually set {username} (ID: {target_user_id}) rating: {old_rating} → {new_rating}")
                
                result_msg = (
                    f"✅ *RATING UPDATED*\n"
                    f"━━━━━━━━━━━━━━━━\n\n"
                    f"*Player:* {escape_markdown_v2_custom(username)}\n"
                    f"*User ID:* `{escape_markdown_v2_custom(target_user_id)}`\n\n"
                    f"*Old Rating:* {old_rating}\n"
                    f"*New Rating:* {new_rating}\n"
                    f"*New Tier:* {escape_markdown_v2_custom(new_tier)}\n\n"
                    f"✅ Rating manually updated by admin\\!"
                )
                
                await send_admin_log(
                    f"🔧 Manually set rating\n"
                    f"Player: {username} (ID: {target_user_id})\n"
                    f"Rating: {old_rating} → {new_rating}\n"
                    f"Tier: {new_tier}",
                    log_type="success",
                    chat_context=get_chat_context(update)
                )
                
        finally:
            return_db_connection(conn)
        
        await update.message.reply_text(result_msg, parse_mode=ParseMode.MARKDOWN_V2)
        
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid rating\\! Must be a number\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )
    except Exception as e:
        logger.error(f"Error setting rating: {e}")
        await update.message.reply_text(
            f"❌ Error: {escape_markdown_v2_custom(str(e))}",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        await send_admin_log(
            f"❌ Error setting rating: {str(e)}",
            log_type="error",
            chat_context=get_chat_context(update)
        )

# --- Scorecard Functions ---
# Add save_match function improvements
@require_subscription
async def save_match(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Save match result with custom name"""
    if not update.message.reply_to_message:
        await update.message.reply_text(
            escape_markdown_v2_custom("❌ Please reply to a match result message with /save <match_name>"),
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return

    try:
        # Get custom name from args or generate default
        match_name = ' '.join(context.args) if context.args else f"Match_{int(time.time())}"
        match_result = update.message.reply_to_message.text
        
        # Validate match result format - check for both old and new formats
        if not match_result or ("MATCH COMPLETE" not in match_result and "MATCH RESULT" not in match_result):
            await update.message.reply_text(
                escape_markdown_v2_custom(
                    "❌ Invalid match result!\n"
                    "Please reply to a valid match result message\n"
                    "Usage: Reply to result + /save <optional_name>"
                ),
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return
            
        # Validate match name length and characters
        if len(match_name) > 100:
            await update.message.reply_text(
                escape_markdown_v2_custom("❌ Match name too long! Maximum 100 characters."),
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return
            
        # Remove special characters from match name
        match_name = re.sub(r'[^a-zA-Z0-9\s_-]', '', match_name)
        if not match_name:
            match_name = f"Match_{int(time.time())}"

        # Parse match result and create match data
        match_data = {
            'match_id': f"M{int(time.time())}_{random.randint(1000, 9999)}",
            'user_id': update.effective_user.id,
            'match_name': match_name,  # Add custom name
            'game_mode': 'classic',
            'timestamp': datetime.now().isoformat(),
            'match_data': json.dumps({
                'full_text': match_result,
                'saved_at': datetime.now().isoformat(),
                'saved_by': update.effective_user.id,
                'match_name': match_name  # Include in match data
            })
        }

        # Try database save first
        success_db = False
        try:
            connection = get_db_connection()
            if connection:
                with connection.cursor() as cursor:
                    # First ensure user exists with all required fields
                    cursor.execute("""
                        INSERT INTO users (telegram_id, username, first_name, last_active)
                        VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                        ON CONFLICT (telegram_id) DO UPDATE
                        SET last_active = CURRENT_TIMESTAMP
                    """, (
                        update.effective_user.id,
                        update.effective_user.username or 'Unknown',
                        update.effective_user.first_name or 'Unknown'
                    ))

                    # Save match with custom name
                    cursor.execute("""
                        INSERT INTO scorecards 
                        (match_id, user_id, match_name, match_data, created_at)
                        VALUES (%s, %s, %s, %s::jsonb, CURRENT_TIMESTAMP)
                        RETURNING match_id
                    """, (
                        match_data['match_id'],
                        match_data['user_id'],
                        match_data['match_name'],
                        match_data['match_data']
                    ))
                    
                    connection.commit()
                    success_db = True
                    
        except Exception as e:
            logger.error(f"Database save error: {e}")
            if connection:
                connection.rollback()
        finally:
            if connection:
                return_db_connection(connection)

        # Try file save as backup
        success_file = False
        try:
            DATA_DIR.mkdir(exist_ok=True)
            
            # Load existing data
            existing_data = []
            if MATCH_HISTORY_FILE.exists():
                with open(MATCH_HISTORY_FILE, 'r', encoding='utf-8') as f:
                    try:
                        existing_data = json.load(f)
                    except json.JSONDecodeError:
                        existing_data = []
            
            # Add new match data
            existing_data.append(match_data)
            
            # Save updated data
            with open(MATCH_HISTORY_FILE, 'w', encoding='utf-8') as f:
                json.dump(existing_data, f, indent=2, default=str)
            
            success_file = True
            
        except Exception as e:
            logger.error(f"File save error: {e}")
            success_file = False

        if success_db or success_file:
            storage_type = "Database" if success_db else "Backup file"
            await update.message.reply_text(
                escape_markdown_v2_custom(
                    f"*✅ Match saved successfully as:*\n"
                    f"*Name:* {match_name}\n"
                    f"*Storage:* {storage_type}\n"
                    "*View your matches with /scorecard*"
                ),
                parse_mode=ParseMode.MARKDOWN_V2
            )
        else:
            await update.message.reply_text(
                escape_markdown_v2_custom("❌ Failed to save match. Please try again."),
                parse_mode=ParseMode.MARKDOWN_V2
            )

    except Exception as e:
        logger.error(f"Error in save_match: {e}")
        await update.message.reply_text(
            escape_markdown_v2_custom("❌ Error saving match. Please try again."),
            parse_mode=ParseMode.MARKDOWN_V2
        )

# Update view_scorecards query to show custom names
@require_subscription
async def view_scorecards(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's match history with custom names"""
    user_id = str(update.effective_user.id)
    
    # Restrict to private chat only
    if update.effective_chat.type != ChatType.PRIVATE:
        try:
            await update.message.reply_text(
                "⚠️ *Scorecard Feature*\n\n"
                "Please open a private chat with me to view your scorecards\\!\n\n"
                "Click here to message the bot privately\\.",
                parse_mode=ParseMode.MARKDOWN_V2
            )
        except Exception as e:
            # If Markdown fails, send plain text
            await update.message.reply_text(
                "⚠️ Scorecard Feature\n\n"
                "Please open a private chat with me to view your scorecards!\n\n"
                "Click here to message the bot privately."
            )
        return
    
    try:
        conn = get_db_connection()
        if not conn:
            return []
            
        with conn.cursor() as cur:
            # Updated query to include match_name
            cur.execute("""
                SELECT 
                    match_id,
                    created_at,
                    match_data,
                    match_name
                FROM scorecards 
                WHERE user_id = %s
                ORDER BY created_at DESC
                LIMIT 10
            """, (user_id,))
            
            matches = cur.fetchall()
            
        if not matches:
            message_text = escape_markdown_v2_custom("❌ No saved matches found!")
            if update.callback_query:
                await update.callback_query.message.edit_text(
                    message_text,
                    parse_mode=ParseMode.MARKDOWN_V2
                )
            else:
                await update.message.reply_text(
                    message_text,
                    parse_mode=ParseMode.MARKDOWN_V2
                )
            return

        # Create paginated keyboard
        keyboard = []
        matches_per_page = 5
        total_pages = (len(matches) + matches_per_page - 1) // matches_per_page
        current_page = context.user_data.get('scorecard_page', 0)
        
        start_idx = current_page * matches_per_page
        end_idx = start_idx + matches_per_page
        page_matches = matches[start_idx:end_idx]
        
        for match in page_matches:
            match_id = match[0]
            created_at = match[1]
            match_data = match[2]
            saved_name = match[3]  # Get the saved match name
            
            # Format date
            match_date = created_at.strftime('%d/%m/%Y')
            
            # Get match name - first try saved name, then from match data, then fallback
            match_name = saved_name
            if not match_name and isinstance(match_data, dict):
                match_name = match_data.get('match_name')
            if not match_name and match_data and isinstance(match_data, str):
                try:
                    match_data_dict = json.loads(match_data)
                    match_name = match_data_dict.get('match_name')
                except:
                    pass
            if not match_name:
                match_name = f"Match #{match_id}"
            
            # Create button with match name
            keyboard.append([
                InlineKeyboardButton(
                    f"📅 {match_date} - {match_name}",
                    callback_data=f"view_{match_id}"
                )
            ])

        # Add navigation buttons
        nav_buttons = []
        if current_page > 0:
            nav_buttons.append(
                InlineKeyboardButton("⬅️ Previous", callback_data="page_prev")
            )
        if current_page < total_pages - 1:
            nav_buttons.append(
                InlineKeyboardButton("➡️ Next", callback_data="page_next")
            )
        if nav_buttons:
            keyboard.append(nav_buttons)

        # Send or edit message
        message_text = escape_markdown_v2_custom(
            f"📊 *MATCH HISTORY*\n"
            f"━━━━━━━━━━━━━━━━\n\n"
            f"Page {current_page + 1}/{total_pages}\n\n"
            f"Select a match to view details:"
        )
        
        if update.callback_query:
            await update.callback_query.message.edit_text(
                message_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN_V2
            )
        else:
            await update.message.reply_text(
                message_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN_V2
            )
            
    except Exception as e:
        logger.error(f"Error in view_scorecards: {e}")
        error_text = escape_markdown_v2_custom("❌ Error loading matches. Please try again.")
        if update.callback_query:
            await update.callback_query.message.edit_text(
                error_text,
                parse_mode=ParseMode.MARKDOWN_V2
            )
        else:
            await update.message.reply_text(
                error_text,
                parse_mode=ParseMode.MARKDOWN_V2
            )
    finally:
        if conn:
            return_db_connection(conn)

# Add new function to delete match
async def delete_match(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Delete a match from both database and file storage"""
    query = update.callback_query
    await query.answer()
    
    _, match_id, _2 = query.data.split('_')
    match_id = match_id + '_'+_2
    user_id = str(query.from_user.id)
    
    try:
        # Delete from database
        success_db = False
        try:
            with db.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        DELETE FROM scorecards 
                        WHERE match_id = %s AND user_id = %s
                        RETURNING match_id
                    """, (match_id, user_id))
                    success_db = cur.fetchone() is not None
                    conn.commit()
            
            success_db = True
        except Error as e:
            logger.error(f"Database delete error: {e}")

        # Delete from file storage
        success_file = False
        try:
            if MATCH_HISTORY_FILE.exists():
                with open(MATCH_HISTORY_FILE, 'r', encoding='utf-8') as f:
                    matches = json.load(f)
                
                # Filter out the match to delete
                matches = [m for m in matches if not (
                    m['match_id'] == match_id and str(m['user_id']) == user_id
                )]
                
                with open(MATCH_HISTORY_FILE, 'w', encoding='utf-8') as f:
                    json.dump(matches, f, indent=2)
                success_file = True
                success_file = True
        except Exception as e:
            logger.error(f"File delete error: {e}")

        if success_db or success_file:
            # Show success message before refreshing list
            await query.message.edit_text(
                escape_markdown_v2_custom(
                    "*✅ Match deleted successfully*!👍\n"
                    "*Refreshing list*...."
                ),
                parse_mode=ParseMode.MARKDOWN_V2
            )
            await asyncio.sleep(1)  # Short delay for user feedback
            
            # Refresh the scorecards view
            await view_scorecards(update, context)
        else:
            await query.message.edit_text(
                escape_markdown_v2_custom(
                    "*❌ Failed to delete match!*😐\n"
                    "*Please try again later.*"
                ),
                parse_mode=ParseMode.MARKDOWN_V2,
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("◀️ Back to List", callback_data="list_matches")
                ]])
            )
    except Exception as e:
        logger.error(f"Error in delete_match: {e}")
        await query.message.edit_text(
            escape_markdown_v2_custom(
                "*❌ An error occurred while deleting the match*.😐\n"
                "*Please try again later*."
            ),
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ Back to List", callback_data="list_matches")
            ]])
        )

# Update view_single_scorecard function
async def view_single_scorecard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show details of a single match"""
    query = update.callback_query
    await query.answer()
    
    _,match_id,_2  = query.data.split('_')
    match_id = match_id + '_'+_2
    user_id = str(query.from_user.id)
    
    connection = get_db_connection()
    card = None
    
    if connection:
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT *
                    FROM scorecards 
                    WHERE user_id = %s AND match_id = %s
                """, (user_id, match_id))
                db_result = cursor.fetchone()
                if db_result:
                    card = db_result

        except Error as e:
            logger.error(f"Database error: {e}")
            # Fallback to in-memory
            for saved_card in in_memory_scorecards:
                if (str(saved_card['user_id']) == user_id and 
                    saved_card['match_data']['match_id'] == match_id):
                    card = saved_card['match_data']
                    break
        finally:
            connection.close()
    else:
        # Use in-memory storage
        for saved_card in in_memory_scorecards:
            if (str(saved_card['user_id']) == user_id and 
                saved_card['match_data']['match_id'] == match_id):
                card = saved_card['match_data']
                break

    if not card:
        await query.edit_message_text(
            escape_markdown_v2_custom("*❌ Match not found!*😐"),
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return

    # Create keyboard with delete button
    keyboard = [
        [InlineKeyboardButton("🗑️ Delete Match", callback_data=f"delete_{match_id}")],
        [InlineKeyboardButton("◀️ Back to List", callback_data="list_matches")]
    ]

    try:
        # Handle potential data formats with proper null checks
        res_view_score = ""
        
        # Safely get match_id, using card[1] or a fallback from the card dict
        match_id_str = str(card[1] if isinstance(card, tuple) else card.get('match_id', 'Unknown'))
        res_view_score += "*Match id *- " + match_id_str + "\n"
        
        # Safely get game mode
        game_mode = str(card[3] if isinstance(card, tuple) else card.get('game_mode', 'Classic'))
        res_view_score += "*Mode* - " + game_mode + "\n"
        
        # Safely handle match data
        if isinstance(card, tuple) and card[4]:
            match_data = card[4]
        else:
            match_data = card if isinstance(card, dict) else {}
        
        # Get timestamp with fallback
        timestamp = (match_data.get('saved_at', '') if isinstance(match_data, dict) else 
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        if timestamp:
            formatted_time = timestamp.replace("T", ", ").split(".")[0]
            res_view_score += "*Time* - " + formatted_time + "\n\n"
        
        # Get match summary with fallback
        summary = (match_data.get('full_text', '') if isinstance(match_data, dict) else 
                  str(match_data) if match_data else 'No match summary available')
        if summary:
            res_view_score += "*Summary*\n*" + summary + "*\n"
        
        # Escape the final formatted string
        res_view_score = escape_markdown_v2_custom(res_view_score)

        await query.edit_message_text(
            res_view_score,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN_V2
        )
        
    except Exception as e:
        logger.error(f"Error formatting match data: {e}")
        await query.edit_message_text(
            escape_markdown_v2_custom(
                "❌ Error displaying match details!\n"
                "Please try again or contact support."
            ),
            parse_mode=ParseMode.MARKDOWN_V2
        )

async def back_to_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Return to the match list view"""
    query = update.callback_query
    await query.answer()
    
    # Reset page number when returning to list
    context.user_data['scorecard_page'] = 0
    await view_scorecards(update, context)

# Update handle_input function
async def handle_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle numeric input with improved UI and flow"""
    if not update.message or not update.message.text:
        return
        
    # Check if this is a reply to our prompt
    if (not update.message.reply_to_message or 
        'awaiting_input' not in context.user_data or
        update.message.reply_to_message.message_id != context.user_data['awaiting_input'].get('prompt_message_id')):
        return
    
    try:
        input_data = context.user_data['awaiting_input']
        game_id = input_data['game_id']
        setting = input_data['setting']
        game = games[game_id]
        
        input_value = update.message.text.strip()
        if not input_value.isdigit():
            await update.message.reply_text(
                escape_markdown_v2_custom(f"{UI_THEMES['accents']['error']} Please enter a valid number!"),
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return
            
        value = int(input_value)
        max_value = 50 if setting == 'overs' else 10
        
        if value < 1 or value > max_value:
            await update.message.reply_text(
                f"{UI_THEMES['accents']['error']} Please enter a number between 1\\-{max_value}\\!",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return
        
        if setting == 'overs':
            game['max_overs'] = value
            game['status'] = 'waiting'
            keyboard = [[InlineKeyboardButton("🤝 Join Game", callback_data=f"join_{game_id}")]]
            message = (
                f"{UI_THEMES['primary']['separator']}\n"
                f"✅ *GAME SETTINGS*\n"
                f"{UI_THEMES['primary']['section_sep']}\n"
                f"*Mode:* {escape_markdown_v2_custom(game['mode'].title())}\n"
                f"*Overs:* {value}\n"
                f"*Wickets:* {game['max_wickets']}\n"
                f"*Host:* {escape_markdown_v2_custom(game['creator_name'])}\n"
                f"{UI_THEMES['primary']['section_sep']}\n"
                f"*Waiting for opponent\\.\\.\\.*\n"
                f"{UI_THEMES['primary']['footer']}"
            )
        else:  # wickets
            game['max_wickets'] = value
            keyboard = get_overs_keyboard(game_id)
            message = (
                f"{UI_THEMES['primary']['separator']}\n"
                f"✅ WICKETS SET: {value}\n"
                f"{UI_THEMES['primary']['section_sep']}\n"
                f"Select number of overs:\n"
                f"{UI_THEMES['primary']['footer']}"
            )
        
        # Clean up old messages
        try:
            await context.bot.delete_message(
                chat_id=update.effective_chat.id,
                message_id=input_data['prompt_message_id']
            )
        except:
            pass
        
        # Send new message
        await update.message.reply_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN_V2
        )
        
        del context.user_data['awaiting_input']
        logger.info(f"Custom {setting} set to {value} for game {game_id}")
        
    except Exception as e:
        logger.error(f"Error in handle_input: {e}")
        await update.message.reply_text(
            escape_markdown_v2_custom(f"{UI_THEMES['accents']['error']} An error occurred. Please try again or start a new game with /gameon"),
            parse_mode=ParseMode.MARKDOWN_V2
        )

# Remove duplicate handle_error() functions - Keep only the enhanced version
async def handle_error(query: CallbackQuery, game_id: str = None):
    """Enhanced error handler with game state recovery"""
    try:
        if not query or not query.message:
            logger.error("Invalid query object in error handler")
            return
            
        if game_id and game_id in games:
            game = games[game_id]
            if not validate_game_state(game):
                game['status'] = game.get('status', 'error')
                game['current_innings'] = game.get('current_innings', 1)
                game['score'] = game.get('score', {'innings1': 0, 'innings2': 0})
                game['wickets'] = game.get('wickets', 0)
                game['balls'] = game.get('balls', 0)
        
        keyboard = [[InlineKeyboardButton("🔄 Retry", callback_data=f"retry_{game_id}")]] if game_id else None
        
        error_msg = escape_markdown_v2_custom(
            "*⚠️ An error occurred!*😐\n\n"
            "*• The game state has been preserved*\n"
            "*• Click Retry to continue*\n"
            "*• Or start a new game with /gameon*"
        )
        
        await query.message.edit_text(
            error_msg,
            reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None,
            parse_mode=ParseMode.MARKDOWN_V2
        )
        
    except Exception as e:
        logger.error(f"Error in error handler: {e}")
        try:
            await query.answer(
                escape_markdown_v2_custom("Failed to handle error. Please start a new game."),
                show_alert=True
            )
        except:
            pass


# Add near other helper functions
def get_current_overs(game: dict) -> str:
    """Get formatted overs string"""
    if 'max_overs' not in game or game['max_overs'] == float('inf'):
        return INFINITY_SYMBOL
    return str(game['max_overs'])

# Merge safe_edit_message() and safe_edit_with_retry()
async def safe_edit_message(message, text: str, keyboard=None, max_retries=MAX_MESSAGE_RETRIES):
    """Edit message with retry logic and flood control"""
    for attempt in range(max_retries):
        try:
            # Don't double escape if text already contains escape sequences
            escaped_text = text if '\\' in text else escape_markdown_v2_custom(text)
            if keyboard:
                return await message.edit_text(
                    text=escaped_text,
                    reply_markup=keyboard,
                    parse_mode=ParseMode.MARKDOWN_V2
                )
            return await message.edit_text(
                text=escaped_text,
                parse_mode=ParseMode.MARKDOWN_V2
            )
        except telegram.error.RetryAfter as e:
            delay = FLOOD_CONTROL_BACKOFF[min(attempt, len(FLOOD_CONTROL_BACKOFF)-1)]
            logger.warning(f"Flood control hit, waiting {delay}s")
            await asyncio.sleep(delay)
        except telegram.error.TimedOut:
            await asyncio.sleep(1)
        except telegram.error.BadRequest as e:
            # Ignore "message not modified" errors
            if "message is not modified" in str(e).lower():
                return None
            logger.error(f"Error editing message: {e}")
            break
        except Exception as e:
            logger.error(f"Error editing message: {e}")
            break
    return None

async def handle_auto_retry(msg, game: dict, retries: int = 0):
    """Auto retry mechanism for failed actions"""
    if retries >= MAX_AUTO_RETRIES:
        await safe_edit_message(msg, escape_markdown_v2_custom(ERROR_MESSAGES['recovery']))
        return False
        
    try:
        await asyncio.sleep(RETRY_WAIT_TIME)
        return True
    except Exception as e:
        logger.error(f"Auto retry failed: {e}")
        return await handle_auto_retry(msg, game, retries + 1)

# Update the keyboard generation to avoid duplicates
def get_batting_keyboard(game_id: str) -> List[List[InlineKeyboardButton]]:
    """Generate batting keyboard with unique buttons"""
    return [
        [
            InlineKeyboardButton("1️⃣", callback_data=f"bat_{game_id}_1"),
            InlineKeyboardButton("2️⃣", callback_data=f"bat_{game_id}_2"),
            InlineKeyboardButton("3️⃣", callback_data=f"bat_{game_id}_3")
        ],
        [
            InlineKeyboardButton("4️⃣", callback_data=f"bat_{game_id}_4"),
            InlineKeyboardButton("5️⃣", callback_data=f"bat_{game_id}_5"),
            InlineKeyboardButton("6️⃣", callback_data=f"bat_{game_id}_6")
        ]
    ]

def get_bowling_keyboard(game_id: str) -> List[List[InlineKeyboardButton]]:
    """Generate bowling keyboard with unique buttons"""
    return [
        [
            InlineKeyboardButton("1️⃣", callback_data=f"bowl_{game_id}_1"),
            InlineKeyboardButton("2️⃣", callback_data=f"bowl_{game_id}_2"),
            InlineKeyboardButton("3️⃣", callback_data=f"bowl_{game_id}_3")
        ],
        [
            InlineKeyboardButton("4️⃣", callback_data=f"bowl_{game_id}_4"),
            InlineKeyboardButton("5️⃣", callback_data=f"bowl_{game_id}_5"),
            InlineKeyboardButton("6️⃣", callback_data=f"bowl_{game_id}_6")
        ]
    ]

# Add at the top with other imports
from functools import wraps

def check_blacklist():
    def decorator(func):
        @wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user_id = str(update.effective_user.id)
            if user_id in BLACKLISTED_USERS:
                await update.message.reply_text(
                    escape_markdown_v2_custom(
                        "❌ *You are blacklisted from using this bot*\n"
                        "📞 Contact admin @admin\\_username for appeal"
                    ),
                    parse_mode=ParseMode.MARKDOWN_V2
                )
                return
            return await func(update, context)
        return wrapper
    return decorator

# Add at top of file with other constants
async def handle_pagination(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle pagination for scorecards"""
        query = update.callback_query
        await query.answer()
        
        direction = query.data.split('_')[1]
        current_page = context.user_data.get('scorecard_page', 0)
        
        if direction == 'prev':
            context.user_data['scorecard_page'] = max(0, current_page - 1)
        else:  # next
            context.user_data['scorecard_page'] = current_page + 1
            
        await view_scorecards(update, context)

# Add these helper functions near the top after imports
def get_game_state_message(game: dict) -> str:
    """Generate formatted game state message"""
    batting_team = escape_markdown_v2_custom(game['batting_team'])
    bowling_team = escape_markdown_v2_custom(game['bowling_team'])
    score = game['score']
    wickets = game['wickets']
    overs = game.get('overs', 0)
    balls = game.get('balls', 0)
    target = game.get('target')
    
    state = escape_markdown_v2_custom(
        f"🏏 *{batting_team}* vs *{bowling_team}*\n"
        f"📊 *Score:* {score}/{wickets}\n"
        f"🎯 *Overs:* {overs}.{balls}\n"
    )
    
    if target:
        runs_needed = target - score
        balls_left = (game['total_overs'] * 6) - (overs * 6 + balls)
        if balls_left > 0:
            state += escape_markdown_v2_custom(
                f"🎯 *Target:* {target}\n"
                f"📈 *Need {runs_needed} runs from {balls_left} balls*"
            )
    
    return state
# Removed duplicate validate_game_state - using enhanced version above

# Add keyboard generator functions
def get_wickets_keyboard(game_id: str) -> List[List[InlineKeyboardButton]]:
    """Generate wickets selection keyboard with 1 wicket option"""
    return [
        [
            InlineKeyboardButton(f"1 🎯", callback_data=f"wickets_{game_id}_1"),
            InlineKeyboardButton(f"2 🎯", callback_data=f"wickets_{game_id}_2")
        ],
        [
            InlineKeyboardButton(f"5 🎯", callback_data=f"wickets_{game_id}_5"),
            InlineKeyboardButton(f"7 🎯", callback_data=f"wickets_{game_id}_7")
        ],
        [InlineKeyboardButton("📝 Custom (1-10)", callback_data=f"custom_{game_id}_wickets")]
    ]

def get_overs_keyboard(game_id: str) -> List[List[InlineKeyboardButton]]:
    """Generate overs selection keyboard with 1 over option"""
    return [
        [
            InlineKeyboardButton(f"1 🎯", callback_data=f"overs_{game_id}_1"),
            InlineKeyboardButton(f"2 🎯", callback_data=f"overs_{game_id}_2")
        ],
        [
            InlineKeyboardButton(f"5 🎯", callback_data=f"overs_{game_id}_5"),
            InlineKeyboardButton(f"10 🎯", callback_data=f"overs_{game_id}_10")
        ],
        [InlineKeyboardButton("📝 Custom (1-50)", callback_data=f"custom_{game_id}_overs")]
    ]

# Update the toss handling
async def handle_toss(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = str(query.from_user.id)
    
    try:
        # Parse callback_data: "toss_{game_id}_{choice}"
        # game_id might contain underscores (e.g., "challenge_CH1234")
        parts = query.data.split('_')
        choice = parts[-1]  # Last part is always the choice (odd/even)
        game_id = '_'.join(parts[1:-1])  # Everything between "toss" and choice is game_id
        game = games.get(game_id)
        
        if not game:
            await query.answer(
                "❌ Game not found!",
                show_alert=True
            )
            return
            
        if user_id != str(game['choosing_player']):
            await query.answer(
                f"❌ Only {game['choosing_player_name']} can choose!",
                show_alert=True
            )
            return
            
        await query.answer()
        
        # Show dice rolling animation
        msg = query.message
        await msg.edit_text(
            escape_markdown_v2_custom("🎲 Rolling first dice..."),
            parse_mode=ParseMode.MARKDOWN_V2
        )
        await asyncio.sleep(1)
        
        dice1 = random.randint(1, 6)
        await msg.edit_text(
            escape_markdown_v2_custom(f"First roll: {dice1}"),
            parse_mode=ParseMode.MARKDOWN_V2
        )
        await asyncio.sleep(1)
        
        await msg.edit_text(
            escape_markdown_v2_custom("🎲 Rolling second dice..."),
            parse_mode=ParseMode.MARKDOWN_V2
        )
        await asyncio.sleep(1)
        
        dice2 = random.randint(1, 6)
        total = dice1 + dice2
        is_odd = total % 2 == 1
       
        # Determine toss winner
        choice_correct = (choice == 'odd' and is_odd) or (choice == 'even' and not is_odd)
        toss_winner = game['choosing_player'] if choice_correct else (
            game['creator'] if game['choosing_player'] == game['joiner'] else game['creator']
        )
        toss_winner_name = game['creator_name'] if toss_winner == game['creator'] else game['joiner_name']
        
        # Update game state
        game['toss_winner'] = toss_winner
        game['toss_winner_name'] = toss_winner_name
        game['choosing_player'] = toss_winner  # Update choosing_player to toss winner
        game['choosing_player_name'] = toss_winner_name
        game['status'] = 'choosing'
        
        # Tag both users using HTML mentions
        creator_mention = f'<a href="tg://user?id={game["creator"]}">{game["creator_name"]}</a>'
        joiner_mention = f'<a href="tg://user?id={game["joiner"]}">{game["joiner_name"]}</a>'
        toss_winner_mention = creator_mention if toss_winner == game['creator'] else joiner_mention
        
        # Create properly formatted message text
        toss_msg = (
            f"<b>🏏 MATCH STARTED!</b>\n"
            f"{MATCH_SEPARATOR}\n"
            f"<b>Players:</b>\n"
            f"• {creator_mention}\n"
            f"• {joiner_mention}\n\n"
            f"<b>🎲 TOSS RESULT</b>\n"
            f"First Roll: {dice1}\n"
            f"Second Roll: {dice2}\n"
            f"Total: {total}\n\n"
            f"🏆 {toss_winner_mention} wins the toss!"
        )
        
        keyboard = [
            [
                InlineKeyboardButton("🏏 BAT", callback_data=f"choice_{game_id}_bat"),
                InlineKeyboardButton("⚾ BOWL", callback_data=f"choice_{game_id}_bowl")
            ]
        ]
        
        await msg.edit_text(
            toss_msg,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )
        
    except Exception as e:
        logger.error(f"Error in handle_toss: {e}")
        await handle_error(query, game_id if 'game_id' in locals() else None)

# Add function to handle game retry
async def handle_retry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle game retry attempts"""
    query = update.callback_query
    await query.answer()
    
    try:
        # Parse callback_data: "retry_{game_id}"
        parts = query.data.split('_')
        game_id = '_'.join(parts[1:])
        if game_id not in games:
            await query.edit_message_text(
                escape_markdown_v2_custom("❌ Game not found! Please start a new game."),
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return
            
        game = games[game_id]
        if not validate_game_state(game):
            await query.edit_message_text(
                escape_markdown_v2_custom("❌ Game state corrupted. Please start a new game."),
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return
            
        # Restore last valid game state
        status = game['status']
        if status == 'batting':
            keyboard = get_batting_keyboard(game_id)
            message = get_game_state_message(game)
        elif status == 'bowling':
            keyboard = get_bowling_keyboard(game_id)
            message = get_game_state_message(game)
        else:
            # Can't recover, start new game
            await query.edit_message_text(
                escape_markdown_v2_custom("❌ Cannot recover game state. Please start a new game."),
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return
            
        await query.edit_message_text(
            escape_markdown_v2_custom(message),
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN_V2
        )
        
    except Exception as e:
        logger.error(f"Error in handle_retry: {e}")
        await query.edit_message_text(
            escape_markdown_v2_custom("❌ Retry failed. Please start a new game."),
            parse_mode=ParseMode.MARKDOWN_V2
        )

def init_database_connection():
    """Initialize database connection with better error handling"""
    global db
    try:
        # Add retries for initial connection
        max_retries = 5
        retry_delay = 10
        
        # Use global db instance to avoid creating multiple pools
        global db
        
        for attempt in range(max_retries):
            try:
                logger.info(f"Database connection attempt {attempt + 1}")
                logger.info(f"Connecting to: {DB_CONFIG['host']}:{DB_CONFIG['port']}")
                
                # Only create new instance if db doesn't exist or is disconnected
                if not db or not db.check_connection():
                    db = DatabaseHandler()
                
                if db.check_connection():
                    logger.info("Successfully connected to database")
                    return True
                    
                logger.warning(f"Connection attempt {attempt + 1} failed, retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
                
            except Exception as e:
                logger.error(f"Database connection attempt {attempt + 1} failed: {str(e)}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                continue
                
        logger.error("All database connection attempts failed")
        return False
        
    except Exception as e:
        logger.error(f"Database initialization failed: {str(e)}")
        return False
    
async def test_db_connection(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Test database connection and schema"""
        if not check_admin(str(update.effective_user.id)):
            await update.message.reply_text("❌ Unauthorized")
            return
        
        user = update.effective_user
        await send_admin_log(
            f"CMD: /testdb by {user.first_name} (@{user.username or 'no_username'}, ID: {user.id})",
            log_type="command",
            chat_context=get_chat_context(update)
        )
            
        try:
            connection = get_db_connection()
            if not connection:
                await update.message.reply_text("❌ Database connection failed!")
                return
    
                
            with connection.cursor() as cursor:
                # Test users table
                cursor.execute("SELECT COUNT(*) FROM users")
                users_count = cursor.fetchone()[0]
                
                # Test scorecards table
                cursor.execute("SELECT COUNT(*) FROM scorecards")
                scorecards_count = cursor.fetchone()[0]
                
                await update.message.reply_text(
                    escape_markdown_v2_custom(
                        f"*✅ Database connected successfully!*👍\n"
                        f"*Users:* {users_count}\n"
                        f"*Scorecards:* {scorecards_count}"
                    ),
                    parse_mode=ParseMode.MARKDOWN_V2
                )
                
        except Exception as e:
            await update.message.reply_text(
                escape_markdown_v2_custom(
                    f"*❌ Database test failed:*\n{str(e)}"
                ),
                parse_mode=ParseMode.MARKDOWN_V2
            )
        finally:
            if connection:
                connection.close()

# Add near the top with other constants
FLOOD_CONTROL_DELAY = 21  # Seconds to wait when flood control is hit
MAX_MESSAGE_RETRIES = 3
FLOOD_CONTROL_BACKOFF = [15, 30, 60]  # Progressive backoff delays - Increased further to prevent rate limits

# Add new helper function
async def safe_edit_with_retry(message, text: str, keyboard=None, max_retries=MAX_MESSAGE_RETRIES):
    """Edit message with flood control handling and retry logic"""
    for attempt in range(max_retries):
        try:
            if keyboard:
                return await message.edit_text(
                    text,
                    reply_markup=keyboard,
                    parse_mode=ParseMode.MARKDOWN_V2
                )
            return await message.edit_text(
                text,
                parse_mode=ParseMode.MARKDOWN_V2
            )
        except telegram.error.RetryAfter as e:
            delay = FLOOD_CONTROL_BACKOFF[min(attempt, len(FLOOD_CONTROL_BACKOFF)-1)]
            logger.warning(f"Flood control hit, waiting {delay}s")
            await asyncio.sleep(delay)
        except telegram.error.TimedOut:
            await asyncio.sleep(1)
        except Exception as e:
            logger.error(f"Error editing message: {e}")
            break
    return None

def save_to_file(match_data: dict):
    """Save match data to backup file"""
    try:
        DATA_DIR.mkdir(exist_ok=True)
        
        # Load existing data
        existing_data = []
        if MATCH_HISTORY_FILE.exists():
            with open(MATCH_HISTORY_FILE, 'r', encoding='utf-8') as f:
                try:
                    existing_data = json.load(f)
                except json.JSONDecodeError:
                    existing_data = []
        
        # Add new match data
        existing_data.append(match_data)
        
        # Save updated data
        with open(MATCH_HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(existing_data, f, indent=2, default=str)
            
    except Exception as e:
        logger.error(f"Error saving to file: {e}")

# Add auto-save functionality
async def auto_save_match(game: dict, user_id: int):
    """Auto save match after key events"""
    try:
        match_data = {
            'match_id': game.get('match_id', generate_match_id()),
            'user_id': user_id,
            'timestamp': datetime.now().isoformat(),
            'teams': {
                'batting_first': game['creator_name'],
                'bowling_first': game['joiner_name']
            },
            'innings1': {
                'score': game['score']['innings1'],
                'wickets': game.get('first_innings_wickets', game['wickets']),
                'overs': f"{game['balls']//6}.{game['balls']%6}"
            },
            'innings2': {
                'score': game['score'].get('innings2', 0),
                'wickets': game['wickets'],
                'overs': f"{game['balls']//6}.{game['balls']%6}"
            },
            'game_mode': game['mode'],
            'match_data': json.dumps(game)
        }
        
        
        # Try database save first
        if not await db.save_match_async(match_data):
            # Fallback to file storage
            save_to_file(match_data)
            
    except Exception as e:
        logger.error(f"Error auto-saving match: {e}")

# Add function to properly format messages

# Add function to properly format messages
def format_game_message(text: str) -> str:
    """Format game messages with proper escaping and bold text"""
    # Bold important numbers and text
    bold_patterns = [
        (r'(\d+)/(\d+)', r'*\1/\2*'),  # Score/wickets
        (r'Over (\d+\.\d+)', r'Over *\1*'),  # Overs
        (r'(\d+) runs', r'*\1* runs'),  # Run counts
        (r'(\d+) wickets', r'*\1* wickets'),  # Wicket counts
        (r'Target: (\d+)', r'Target: *\1*'),  # Target
        (r'RRR: ([\d.]+)', r'RRR: *\1*')  # Required run rate
    ]
    
    for pattern, replacement in bold_patterns:
        text = re.sub(pattern, replacement, text)
    
    # Escape special characters for Markdown V2
    return escape_markdown(text, version=2)

def validate_config():
    required_vars = ['DB_NAME', 'DB_USER', 'DB_PASSWORD', 'DB_HOST']
    missing = [var for var in required_vars if var not in os.environ]
    if missing:
        raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

# Add this helper function near the top with other helper functions
def safe_division(numerator, denominator, default=0):
    """Safely perform division with fallback to default value"""
    try:
        if denominator == 0 or not denominator:
            return default
        return numerator / float(denominator)
    except (ValueError, TypeError):
        return default

# ===== PHASE 2: ELO RATING SYSTEM =====
def get_k_factor_by_rank(rank_tier: str, total_ranked_matches: int) -> int:
    """
    Determine K-factor based on player's rank and placement status.
    
    Args:
        rank_tier: Player's current rank (e.g., 'Bronze I', 'Diamond III')
        total_ranked_matches: Total ranked matches played
    
    Returns:
        K-factor (16-48)
    """
    # Placement matches (first 5 games) - highest K for fast calibration
    if total_ranked_matches < 5:
        return 48
    
    # Extract rank tier (Bronze, Silver, Gold, etc.)
    rank_lower = rank_tier.lower()
    
    # Dynamic K-factor by rank
    if 'bronze' in rank_lower or 'silver' in rank_lower:
        return 40  # New players climb faster
    elif 'gold' in rank_lower or 'platinum' in rank_lower:
        return 32  # Standard competitive rate
    elif 'diamond' in rank_lower or 'ruby' in rank_lower:
        return 24  # High ranks stabilize
    elif 'immortal' in rank_lower:
        return 16  # Top ranks are very stable
    else:
        return 32  # Default fallback

def calculate_win_streak_bonus(current_streak: int, rank_tier: str, is_winner: bool, total_ranked_matches: int) -> int:
    """
    Calculate flat bonus for win streaks.
    
    Args:
        current_streak: Player's current win streak (0+)
        rank_tier: Player's current rank
        is_winner: Whether player won this match
        total_ranked_matches: Total ranked matches played
    
    Returns:
        Flat bonus to add to rating change (0-4)
    """
    # No bonus if not a win
    if not is_winner:
        return 0
    
    # No bonus during placement matches
    if total_ranked_matches < 5:
        return 0
    
    # No bonus for Platinum+ ranks
    rank_lower = rank_tier.lower()
    if 'platinum' in rank_lower or 'diamond' in rank_lower or 'ruby' in rank_lower or 'immortal' in rank_lower:
        return 0
    
    # Calculate flat bonus based on streak
    if current_streak >= 5:
        return 4  # Max bonus at 5+ streak
    elif current_streak >= 3:
        return 2  # Small bonus at 3-4 streak
    else:
        return 0  # No bonus yet

def calculate_elo_change(rating1: int, rating2: int, winner: int, k_factor: int = 32) -> tuple:
    """
    Calculate ELO rating changes for both players.
    
    Args:
        rating1: Player 1's current rating
        rating2: Player 2's current rating
        winner: 1 if player1 wins, 2 if player2 wins, 0 if draw
        k_factor: Maximum rating change (dynamic by rank, 16-48)
    
    Returns:
        Tuple of (player1_change, player2_change)
    
    Example:
        Player A (1250) beats Player B (1180)
        calculate_elo_change(1250, 1180, 1) -> (+14, -14)
        
        Draw: calculate_elo_change(1250, 1180, 0) -> (-3, +3)
    """
    # Calculate expected win probabilities
    expected1 = 1 / (1 + 10 ** ((rating2 - rating1) / 400))
    expected2 = 1 / (1 + 10 ** ((rating1 - rating2) / 400))
    
    # Actual scores (1 for win, 0 for loss, 0.5 for draw)
    if winner == 0:  # Draw
        actual1 = 0.5
        actual2 = 0.5
    elif winner == 1:
        actual1 = 1
        actual2 = 0
    else:  # winner == 2
        actual1 = 0
        actual2 = 1
    
    # Calculate rating changes
    change1 = int(k_factor * (actual1 - expected1))
    change2 = int(k_factor * (actual2 - expected2))
    
    return change1, change2

def get_target_info(game: dict) -> str:
    """Get formatted target information string"""
    if game['current_innings'] != 2 or 'target' not in game:
        return ""
        
    target = game['target']
    current_score = game['score']['innings2']
    runs_needed = target - current_score
    balls_left = (game['max_overs'] * 6) - game['balls']
    
    if balls_left > 0:
        required_rate = (runs_needed * 6) / max(balls_left, 1)  # Prevent division by zero
        return f"\n*Target:* {target}\n*Need:* {runs_needed} from {balls_left} balls\n*RRR:* {required_rate:.2f}"
    
    return f"\n*Target:* {target}\n*Need:* {runs_needed} runs"

# Add new admin commands after existing admin commands...

async def list_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all bot admins"""
    if not check_admin(str(update.effective_user.id)):
        await update.message.reply_text("❌ Unauthorized")
        return
    
    user = update.effective_user
    await send_admin_log(
        f"CMD: /listadmins by {user.first_name} (@{user.username or 'no_username'}, ID: {user.id})",
        log_type="command",
        chat_context=get_chat_context(update)
    )
        
    if not BOT_ADMINS:
        await update.message.reply_text(
            "👑 *BOT ADMINISTRATORS*\n"
            "━━━━━━━━━━━━━━━━\n\n"
            "No admins configured",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return
        
    admins_list = "👑 *BOT ADMINISTRATORS*\n━━━━━━━━━━━━━━━━\n\n"
    for admin_id in BOT_ADMINS:
        try:
            user = await context.bot.get_chat(int(admin_id))
            name = escape_markdown_v2_custom(user.first_name or "Unknown")
            username = f"@{user.username}" if user.username else "No username"
            admins_list += f"• {name} \\({escape_markdown_v2_custom(username)}\\)\n  ID: `{admin_id}`\n\n"
        except Exception as e:
            admins_list += f"• ID: `{admin_id}`\n  \\(User info unavailable\\)\n\n"
    
    await update.message.reply_text(admins_list, parse_mode=ParseMode.MARKDOWN_V2)
    
    await update.message.reply_text(
        admins_list,
        parse_mode=ParseMode.MARKDOWN_V2
    )

async def remove_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove an admin"""
    if not check_admin(str(update.effective_user.id)):
        await update.message.reply_text("❌ Unauthorized")
        return
    
    user = update.effective_user
    await send_admin_log(
        f"CMD: /removeadmin by {user.first_name} (@{user.username or 'no_username'}, ID: {user.id})",
        log_type="command",
        chat_context=get_chat_context(update)
    )
        
    if not context.args:
        await update.message.reply_text(
            escape_markdown_v2_custom("*Usage:* /removeadmin <user_id>"),
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return
        
    admin_to_remove = context.args[0]
    
    if admin_to_remove not in BOT_ADMINS:
        await update.message.reply_text(
            escape_markdown_v2_custom("❌ User is not an admin!"),
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return
        
    if len(BOT_ADMINS) <= 1:
        await update.message.reply_text(
            escape_markdown_v2_custom("❌ Cannot remove the last admin!"),
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return
        
    BOT_ADMINS.remove(admin_to_remove)
    await update.message.reply_text(
        escape_markdown_v2_custom("✅ Admin removed successfully!"),
        parse_mode=ParseMode.MARKDOWN_V2
    )

async def blacklist_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Blacklist a user from using the bot"""
    if not check_admin(str(update.effective_user.id)):
        await update.message.reply_text("❌ Unauthorized")
        return
    
    user = update.effective_user
    await send_admin_log(
        f"CMD: /blacklist by {user.first_name} (@{user.username or 'no_username'}, ID: {user.id})",
        log_type="command",
        chat_context=get_chat_context(update)
    )
        
    if not context.args:
        await update.message.reply_text(
            escape_markdown_v2_custom("*Usage:* /blacklist <user_id> [reason]"),
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return
        
    user_id = context.args[0]
    reason = ' '.join(context.args[1:]) if len(context.args) > 1 else "No reason provided"
    
    try:
        conn = get_db_connection()
        if not conn:
            await update.message.reply_text("❌ Database connection error")
            return
            
        with conn.cursor() as cur:
            # Update user's banned status
            cur.execute("""
                UPDATE users 
                SET is_banned = TRUE,
                    ban_reason = %s,
                    banned_at = CURRENT_TIMESTAMP,
                    banned_by = %s
                WHERE telegram_id = %s
                RETURNING telegram_id
            """, (reason, update.effective_user.id, user_id))
            
            if cur.fetchone():
                BLACKLISTED_USERS.add(user_id)
                conn.commit()
                
                await update.message.reply_text(
                    escape_markdown_v2_custom(f"✅ User {user_id} has been blacklisted\nReason: {reason}"),
                    parse_mode=ParseMode.MARKDOWN_V2
                )
            else:
                await update.message.reply_text(
                    escape_markdown_v2_custom("❌ User not found in database"),
                    parse_mode=ParseMode.MARKDOWN_V2
                )
                
    except Exception as e:
        logger.error(f"Error blacklisting user: {e}")
        await update.message.reply_text(
            escape_markdown_v2_custom("❌ Error blacklisting user"),
            parse_mode=ParseMode.MARKDOWN_V2
        )
    finally:
        if conn:
            return_db_connection(conn)

async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove a user from the blacklist"""
    if not check_admin(str(update.effective_user.id)):
        await update.message.reply_text("❌ Unauthorized")
        return
    
    user = update.effective_user
    await send_admin_log(
        f"CMD: /unban by {user.first_name} (@{user.username or 'no_username'}, ID: {user.id})",
        log_type="command",
        chat_context=get_chat_context(update)
    )
        
    if not context.args:
        await update.message.reply_text(
            escape_markdown_v2_custom("*Usage:* /unban <user_id>"),
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return
        
    user_id = context.args[0]
    
    try:
        conn = get_db_connection()
        if not conn:
            await update.message.reply_text("❌ Database connection error")
            return
            
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE users 
                SET is_banned = FALSE,
                    ban_reason = NULL,
                    banned_at = NULL,
                    banned_by = NULL
                WHERE telegram_id = %s
                RETURNING telegram_id
            """, (user_id,))
            
            if cur.fetchone():
                BLACKLISTED_USERS.discard(user_id)
                conn.commit()
                
                await update.message.reply_text(
                    escape_markdown_v2_custom(f"✅ User {user_id} has been unbanned"),
                    parse_mode=ParseMode.MARKDOWN_V2
                )
            else:
                await update.message.reply_text(
                    escape_markdown_v2_custom("❌ User not found in database"),
                    parse_mode=ParseMode.MARKDOWN_V2
                )
                
    except Exception as e:
        logger.error(f"Error unbanning user: {e}")
        await update.message.reply_text(
            escape_markdown_v2_custom("❌ Error unbanning user"),
            parse_mode=ParseMode.MARKDOWN_V2
        )
    finally:
        if conn:
            return_db_connection(conn)

async def toggle_maintenance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle maintenance mode"""
    if not check_admin(str(update.effective_user.id)):
        await update.message.reply_text("❌ Unauthorized")
        return
    
    user = update.effective_user
    await send_admin_log(
        f"CMD: /maintenance by {user.first_name} (@{user.username or 'no_username'}, ID: {user.id})",
        log_type="command",
        chat_context=get_chat_context(update)
    )
        
    global MAINTENANCE_MODE
    MAINTENANCE_MODE = not MAINTENANCE_MODE
    
    status = "enabled" if MAINTENANCE_MODE else "disabled"
    await update.message.reply_text(
        escape_markdown_v2_custom(f"✅ Maintenance mode {status}"),
        parse_mode=ParseMode.MARKDOWN_V2
    )
    
    if MAINTENANCE_MODE:
        # End all active games
        games.clear()
        
# Add after check_admin() function
def check_maintenance(update: Update) -> bool:
    """Check if bot is in maintenance mode"""
    if MAINTENANCE_MODE and not check_admin(str(update.effective_user.id)):
        return True
    return False

    """Save admin and group data to database"""
    try:
        conn = get_db_connection()
        if not conn:
            return

        with conn.cursor() as cur:
            # Save admins
            for admin_id in BOT_ADMINS:
                cur.execute("""
                    INSERT INTO bot_admins (admin_id, added_by)
                    VALUES (%s, %s)
                    ON CONFLICT (admin_id) DO NOTHING
                """, (admin_id, admin_id))

            # Save groups
            for group_id in AUTHORIZED_GROUPS:
                cur.execute("""
                    INSERT INTO authorized_groups (group_id, group_name, added_by)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (group_id) DO NOTHING
                """, (group_id, "Unknown", list(BOT_ADMINS)[0]))

            conn.commit()

    except Exception as e:
        logger.error(f"Error saving persistent data: {e}")
    finally:
        if conn:
            return_db_connection(conn)

async def get_player_stats(user_id: str) -> dict:
    try:
        conn = get_db_connection()
        if not conn:
            return default_stats()
            
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    matches_played,
                    matches_won,
                    total_runs_scored,
                    total_wickets_taken,
                    total_balls_faced,
                    highest_score,
                    total_boundaries,
                    total_sixes,
                    dot_balls,
                    fifties,
                    hundreds,
                    best_bowling,
                    last_five_scores
                FROM player_stats 
                WHERE user_id = %s
            """, (user_id,))
            
            result = cur.fetchone()
            if not result:
                return default_stats()
                
            return {
                'matches_played': result[0] or 0,
                'matches_won': result[1] or 0,
                'total_runs': result[2] or 0,
                'total_balls_faced': result[4] or 0,
                'wickets': result[3] or 0,
                'highest_score': result[5] or 0,
                'boundaries': result[6] or 0,
                'sixes': result[7] or 0,
                'dot_balls': result[8] or 0,
                'fifties': result[9] or 0,
                'hundreds': result[10] or 0,
                'best_bowling': result[11],
                'last_five_scores': result[12] or '[]',
                'batting_avg': safe_division(result[2], result[0], 0),
                'strike_rate': safe_division(result[2], result[4] or 1, 0) * 100,
                'bowling_avg': safe_division(result[2], result[3] or 1, 0)
            }
            
    except Exception as e:
        logger.error(f"Error getting player stats: {e}")
        return default_stats()
    finally:
        if conn:
            return_db_connection(conn)

@require_subscription
async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show enhanced player profile with improved UI"""
    user_id = str(update.effective_user.id)
    user_name = update.effective_user.first_name
    user = update.effective_user
    
    await send_admin_log(
        f"CMD: /profile by {user_name} (@{user.username or 'no_username'}, ID: {user_id})",
        log_type="command",
        chat_context=get_chat_context(update)
    )
    
    try:
        # Get career stats from career_stats table
        career_stats = await get_career_stats(user_id)
        
        # Get detailed player stats from player_stats table
        player_stats = await get_player_stats(user_id)
        
        # Calculate stats safely with null checks
        total_matches = career_stats.get('total_matches', 0)
        wins = career_stats.get('wins', 0)
        losses = career_stats.get('losses', 0)
        rating = career_stats.get('rating', 1000)
        rank_tier = career_stats.get('rank_tier', 'Bronze')
        win_rate = safe_division(wins, total_matches, 0) * 100
        
        # Get detailed stats
        total_runs = player_stats.get('total_runs', 0)
        batting_avg = player_stats.get('batting_avg', 0)
        highest_score = player_stats.get('highest_score', 0)
        boundaries = player_stats.get('boundaries', 0)
        sixes = player_stats.get('sixes', 0)
        wickets = player_stats.get('wickets', 0)
        dot_balls = player_stats.get('dot_balls', 0)
        
        # Calculate normal mode stats (total - ranked)
        normal_matches = player_stats.get('matches_played', 0) - total_matches
        normal_runs = total_runs  # Approximate, we'll track this better in future
        profile_text = (
            "👤  *PLAYER CARD*\n"
            "════════════════\n"
            f"✨ *{escape_markdown_v2_custom(user_name)}*\n\n"
            
            "🏆 *RANKED STATS*\n"
            "────────────────\n"
            f"🎖️ *Tier:*   {escape_markdown_v2_custom(rank_tier)}\n"
            f"⚡ *Rating:* {rating}\n"
            f"🎮 *Matches:* {total_matches}\n"
            f"📈 *Win Rate:* {escape_markdown_v2_custom(f'{win_rate:.0f}%')}\n\n"
            
            "🏏 *CAREER TOTALS*\n"
            "────────────────\n"
            f"🏃 *Runs:*    {total_runs}  |  *High:* {highest_score}\n"
            f"💥 *Bound:*   {boundaries}/{sixes}\n"
            f"🎯 *Wickets:* {wickets}"
        )

        # Enhanced interactive buttons
        keyboard = [
            [
                InlineKeyboardButton("� Refresh", callback_data=f"refresh_profile_{user_id}"),
                InlineKeyboardButton("🏆 Leaderboard", callback_data="leaderboard")
            ],
            [InlineKeyboardButton("📜 Match History", callback_data="list_matches")]
        ]

        await update.message.reply_text(
            profile_text,
            parse_mode=ParseMode.MARKDOWN_V2
        )

    except Exception as e:
        logger.error(f"Error showing profile: {e}")
        await update.message.reply_text(
            escape_markdown_v2_custom("❌ Error showing profile. Please try again."),
            parse_mode=ParseMode.MARKDOWN_V2
        )

# ========================================
# CAREER/RANKING SYSTEM FUNCTIONS
# ========================================

def get_rank_tier(rating: int) -> str:
    """Convert rating to rank tier"""
    if rating < 200: return "🥉 Bronze I"
    elif rating < 400: return "🥉 Bronze II"
    elif rating < 600: return "🥉 Bronze III"
    elif rating < 800: return "🥈 Silver I"
    elif rating < 1000: return "🥈 Silver II"
    elif rating < 1200: return "🥈 Silver III"
    elif rating < 1400: return "🥇 Gold I"
    elif rating < 1600: return "🥇 Gold II"
    elif rating < 1800: return "🥇 Gold III"
    elif rating < 2000: return "💎 Platinum I"
    elif rating < 2200: return "💎 Platinum II"
    elif rating < 2400: return "💎 Platinum III"
    elif rating < 2600: return "💠 Diamond I"
    elif rating < 2800: return "💠 Diamond II"
    elif rating < 3000: return "💠 Diamond III"
    elif rating < 3300: return "⚜️ Master I"
    elif rating < 3600: return "⚜️ Master II"
    elif rating < 4000: return "⚜️ Master III"
    elif rating < 4400: return "👑 Grandmaster I"
    elif rating < 4800: return "👑 Grandmaster II"
    elif rating < 5200: return "👑 Grandmaster III"
    else: return "🔥 Immortal"

def get_next_rank_info(rating: int) -> tuple:
    """Get next rank threshold and name"""
    thresholds = [
        (200, "Bronze II"), (400, "Bronze III"), (600, "Silver I"),
        (800, "Silver II"), (1000, "Silver III"), (1200, "Gold I"),
        (1400, "Gold II"), (1600, "Gold III"), (1800, "Platinum I"),
        (2000, "Platinum II"), (2200, "Platinum III"), (2400, "Diamond I"),
        (2600, "Diamond II"), (2800, "Diamond III"), (3000, "Master I"),
        (3300, "Master II"), (3600, "Master III"), (4000, "Grandmaster I"),
        (4400, "Grandmaster II"), (4800, "Grandmaster III"), (5200, "Immortal I"),
        (5600, "Immortal II"), (6000, "Immortal III")
    ]
    
    for threshold, name in thresholds:
        if rating < threshold:
            return threshold, name
    return None, "MAX RANK"

def get_rank_from_rating(rating: int) -> str:
    """Get rank tier name based on rating"""
    if rating < 0: return "Unranked"
    elif rating < 200: return "Bronze I"
    elif rating < 400: return "Bronze II"
    elif rating < 600: return "Bronze III"
    elif rating < 800: return "Silver I"
    elif rating < 1000: return "Silver II"
    elif rating < 1200: return "Silver III"
    elif rating < 1400: return "Gold I"
    elif rating < 1600: return "Gold II"
    elif rating < 1800: return "Gold III"
    elif rating < 2000: return "Platinum I"
    elif rating < 2200: return "Platinum II"
    elif rating < 2400: return "Platinum III"
    elif rating < 2600: return "Diamond I"
    elif rating < 2800: return "Diamond II"
    elif rating < 3000: return "Diamond III"
    elif rating < 3300: return "Master I"
    elif rating < 3600: return "Master II"
    elif rating < 4000: return "Master III"
    elif rating < 4400: return "Grandmaster I"
    elif rating < 4800: return "Grandmaster II"
    elif rating < 5200: return "Grandmaster III"
    elif rating < 5600: return "Immortal I"
    elif rating < 6000: return "Immortal II"
    else: return "Immortal III"

def get_current_rank_bounds(rating: int) -> tuple:
    """Get current rank's min and max rating bounds"""
    bounds = [
        (0, 200, "Bronze I"), (200, 400, "Bronze II"), (400, 600, "Bronze III"),
        (600, 800, "Silver I"), (800, 1000, "Silver II"), (1000, 1200, "Silver III"),
        (1200, 1400, "Gold I"), (1400, 1600, "Gold II"), (1600, 1800, "Gold III"),
        (1800, 2000, "Platinum I"), (2000, 2200, "Platinum II"), (2200, 2400, "Platinum III"),
        (2400, 2600, "Diamond I"), (2600, 2800, "Diamond II"), (2800, 3000, "Diamond III"),
        (3000, 3300, "Master I"), (3300, 3600, "Master II"), (3600, 4000, "Master III"),
        (4000, 4400, "Grandmaster I"), (4400, 4800, "Grandmaster II"), (4800, 5200, "Grandmaster III"),
        (5200, 5600, "Immortal I"), (5600, 6000, "Immortal II"), (6000, 10000, "Immortal III")
    ]
    
    for min_rating, max_rating, tier_name in bounds:
        if min_rating <= rating < max_rating:
            return min_rating, max_rating, tier_name
    return 6000, 10000, "Immortal III"

# ===== PHASE 3: CHALLENGE SYSTEM HELPER FUNCTIONS =====

def get_rank_tier_distance(tier1: str, tier2: str) -> int:
    """Calculate distance between two rank tiers (0 = same, 1 = adjacent, etc.)"""
    tier_order = [
        "Bronze I", "Bronze II", "Bronze III",
        "Silver I", "Silver II", "Silver III",
        "Gold I", "Gold II", "Gold III",
        "Platinum I", "Platinum II", "Platinum III",
        "Diamond I", "Diamond II", "Diamond III",
        "Master I", "Master II", "Master III",
        "Grandmaster I", "Grandmaster II", "Grandmaster III",
        "Immortal I", "Immortal II", "Immortal III"
    ]
    
    # Remove emojis from tier names (e.g., "🥈 Silver III" -> "Silver III")
    def clean_tier(tier: str) -> str:
        # Split by space and take last two parts (e.g., "Silver III")
        parts = tier.split()
        if len(parts) >= 2:
            return ' '.join(parts[-2:])
        return tier
    
    try:
        clean_tier1 = clean_tier(tier1)
        clean_tier2 = clean_tier(tier2)
        idx1 = tier_order.index(clean_tier1)
        idx2 = tier_order.index(clean_tier2)
        return abs(idx1 - idx2)
    except ValueError:
        return 999  # Unknown tier, return large number

async def check_challenge_cooldown(challenger_id: int, target_id: int) -> int:
    """Check if challenge cooldown is active. Returns remaining seconds or 0"""
    try:
        conn = get_db_connection()
        if not conn:
            return 0
            
        with conn.cursor() as cur:
            cur.execute("""
                SELECT expires_at FROM challenge_cooldowns
                WHERE challenger_id = %s AND target_id = %s
                AND expires_at > NOW()
            """, (challenger_id, target_id))
            
            result = cur.fetchone()
            
            if result:
                expires_at = result[0]
                remaining = (expires_at - datetime.now()).total_seconds()
                return max(0, int(remaining))
            return 0
            
    except Exception as e:
        logger.error(f"Error checking challenge cooldown: {e}")
        return 0
    finally:
        if conn:
            return_db_connection(conn)

async def add_challenge_cooldown(challenger_id: int, target_id: int, cooldown_minutes: int = 5):
    """Add challenge cooldown entry"""
    try:
        conn = get_db_connection()
        if not conn:
            return
            
        with conn.cursor() as cur:
            expires_at = datetime.now() + timedelta(minutes=cooldown_minutes)
            
            cur.execute("""
                INSERT INTO challenge_cooldowns (challenger_id, target_id, expires_at)
                VALUES (%s, %s, %s)
                ON CONFLICT (challenger_id, target_id)
                DO UPDATE SET challenged_at = NOW(), expires_at = EXCLUDED.expires_at
            """, (challenger_id, target_id, expires_at))
            
            conn.commit()
            
    except Exception as e:
        logger.error(f"Error adding challenge cooldown: {e}")
    finally:
        if conn:
            return_db_connection(conn)

async def is_player_available(user_id: int) -> bool:
    """Check if player is available for a challenge (not in active game or queue)"""
    # Check if in active game
    for game in games.values():
        if game.get('creator') == user_id or game.get('joiner') == user_id:
            return False
    
    # Check if in ranked queue AND clean up stale entries
    if user_id in ranked_queue:
        queue_entry = ranked_queue[user_id]
        # Check if entry is stale (older than 5 minutes)
        if time.time() - queue_entry.get('joined_at', 0) > 300:
            # Remove stale entry
            logger.warning(f"🧹 Cleaning stale queue entry for user {user_id}")
            del ranked_queue[user_id]
            return True
        return False
    
    # Don't check pending challenges - having a challenge shouldn't block playing
    return True

async def get_career_stats(user_id: str) -> dict:
    """Get career/ranking stats for a player"""
    try:
        with DatabaseConnection() as conn:
            with conn.cursor(cursor_factory=DictCursor) as cur:
                # Check if player exists
                cur.execute("""
                    SELECT * FROM career_stats WHERE user_id = %s
                """, (user_id,))
                
                result = cur.fetchone()
                
                if not result:
                    # Create new career record
                    cur.execute("""
                        INSERT INTO career_stats 
                            (user_id, username, rating, rank_tier, total_matches, wins, losses)
                        VALUES (%s, '', 1000, 'Silver III', 0, 0, 0)
                        RETURNING *
                    """, (user_id,))
                    conn.commit()
                    result = cur.fetchone()
                
                return dict(result) if result else None
                
    except Exception as e:
        logger.error(f"Error getting career stats: {e}")
        return None

def calculate_performance_bonus(game: dict, winner_side: str) -> int:
    """Calculate performance bonus points based on match dominance"""
    bonus = 0
    
    try:
        innings1_score = game['score'].get('innings1', 0)
        innings2_score = game['score'].get('innings2', 0)
        innings1_wickets = game.get('first_innings_wickets', 0)
        innings2_wickets = game['wickets']
        
        # Determine margin
        if winner_side == 'batsman':
            # Chasing team won
            wickets_left = 10 - innings2_wickets
            if wickets_left >= 8:
                bonus += 3  # Dominant chase
            elif wickets_left >= 5:
                bonus += 2
                
            # Quick chase
            balls_used = game['balls']
            total_balls = game['max_overs'] * 6
            if balls_used < total_balls * 0.7:  # Finished with 30%+ balls remaining
                bonus += 2
                
        else:
            # Defending team won
            run_margin = innings1_score - innings2_score
            if run_margin >= 100:
                bonus += 3  # Won by 100+ runs
            elif run_margin >= 50:
                bonus += 2
                
            # All out opponent
            if innings2_wickets == 10:
                bonus += 2
        
    except Exception as e:
        logger.error(f"Error calculating performance bonus: {e}")
    
    return min(bonus, 7)  # Max +7 bonus

def calculate_rating_change(winner_rating: int, loser_rating: int, performance_bonus: int = 0) -> tuple:
    """Calculate rating changes for winner and loser"""
    BASE_POINTS = 20
    
    # Rating difference factor
    rating_diff = winner_rating - loser_rating
    
    if rating_diff > 0:
        # Higher rated player won (expected)
        multiplier = 0.9
    elif rating_diff < 0:
        # Lower rated player won (upset!)
        multiplier = 1.2
    else:
        multiplier = 1.0
    
    # Calculate changes
    winner_gain = int(BASE_POINTS * multiplier) + performance_bonus
    loser_loss = int(BASE_POINTS * multiplier)
    
    # Apply bounds
    winner_gain = max(10, min(winner_gain, 35))  # Between 10-35
    loser_loss = max(5, min(loser_loss, 25))  # Between 5-25
    
    return winner_gain, loser_loss

async def update_career_stats(winner_id: str, loser_id: str, winner_gain: int, loser_loss: int, 
                              winner_name: str = "", loser_name: str = "") -> tuple:
    """Update career stats after a match"""
    try:
        with DatabaseConnection() as conn:
            with conn.cursor(cursor_factory=DictCursor) as cur:
                # Get current stats
                winner_stats = await get_career_stats(winner_id)
                loser_stats = await get_career_stats(loser_id)
                
                if not winner_stats or not loser_stats:
                    return None, None
                
                # Calculate new ratings
                new_winner_rating = max(0, winner_stats['rating'] + winner_gain)
                new_loser_rating = max(0, loser_stats['rating'] - loser_loss)
                
                # Update winner
                cur.execute("""
                    UPDATE career_stats SET
                        username = %s,
                        rating = %s,
                        rank_tier = %s,
                        total_matches = total_matches + 1,
                        wins = wins + 1,
                        current_streak = CASE 
                            WHEN streak_type = 'win' THEN current_streak + 1
                            ELSE 1
                        END,
                        streak_type = 'win',
                        highest_rating = GREATEST(highest_rating, %s),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = %s
                    RETURNING *
                """, (
                    winner_name, 
                    new_winner_rating, 
                    get_rank_tier(new_winner_rating),
                    new_winner_rating,
                    winner_id
                ))
                winner_result = dict(cur.fetchone())
                
                # Update loser
                cur.execute("""
                    UPDATE career_stats SET
                        username = %s,
                        rating = %s,
                        rank_tier = %s,
                        total_matches = total_matches + 1,
                        losses = losses + 1,
                        current_streak = CASE 
                            WHEN streak_type = 'loss' THEN current_streak + 1
                            ELSE 1
                        END,
                        streak_type = 'loss',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = %s
                    RETURNING *
                """, (
                    loser_name,
                    new_loser_rating,
                    get_rank_tier(new_loser_rating),
                    loser_id
                ))
                loser_result = dict(cur.fetchone())
                
                conn.commit()
                return winner_result, loser_result
            
    except Exception as e:
        logger.error(f"Error updating career stats: {e}")
        return None, None

async def save_ranked_match(game: dict, winner_id: str, loser_id: str, 
                            winner_gain: int, loser_loss: int, performance_bonus: int) -> bool:
    """Save ranked match history"""
    try:
        with DatabaseConnection() as conn:
            with conn.cursor() as cur:
                # Get ratings before match
                winner_stats = await get_career_stats(winner_id)
                loser_stats = await get_career_stats(loser_id)
                
                if not winner_stats or not loser_stats:
                    return False
                
                # Determine which player is player1/player2
                is_batsman_winner = (winner_id == game.get('batsman'))
                player1_id = game.get('batsman')
                player2_id = game.get('bowler')
                
                # Insert match record
                cur.execute("""
                    INSERT INTO ranked_matches (
                        player1_id, player2_id, winner_id, match_type,
                        p1_rating_before, p1_rating_after, p1_rating_change,
                        p2_rating_before, p2_rating_after, p2_rating_change,
                        p1_score, p1_wickets, p1_overs,
                        p2_score, p2_wickets, p2_overs,
                        performance_bonus
                    ) VALUES (
                        %s, %s, %s, 'ranked',
                        %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s,
                        %s
                    )
                """, (
                    player1_id, player2_id, winner_id,
                    winner_stats['rating'] if is_batsman_winner else loser_stats['rating'],
                    winner_stats['rating'] + winner_gain if is_batsman_winner else loser_stats['rating'] - loser_loss,
                    winner_gain if is_batsman_winner else -loser_loss,
                    loser_stats['rating'] if is_batsman_winner else winner_stats['rating'],
                    loser_stats['rating'] - loser_loss if is_batsman_winner else winner_stats['rating'] + winner_gain,
                    -loser_loss if is_batsman_winner else winner_gain,
                    game['score'].get('innings1', 0),
                    game.get('first_innings_wickets', 0),
                    game.get('first_innings_balls', 0) / 6.0,
                    game['score'].get('innings2', 0),
                    game['wickets'],
                    game['balls'] / 6.0,
                    performance_bonus
                ))
                
                conn.commit()
                return True
    
    except Exception as e:
        logger.error(f"Error saving ranked match: {e}")
        return False

@require_subscription
async def career(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show player career/ranking profile"""
    user_id = str(update.effective_user.id)
    username = update.effective_user.first_name or "Player"
    user = update.effective_user
    
    await send_admin_log(
        f"CMD: /career by {username} (@{user.username or 'no_username'}, ID: {user_id})",
        log_type="command",
        chat_context=get_chat_context(update)
    )
    
    try:
        # Get career stats
        stats = await get_career_stats(user_id)
        
        if not stats:
            await update.message.reply_text(
                escape_markdown_v2_custom("❌ Error loading career stats. Please try again."),
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return
        
        # Update username if changed
        if stats['username'] != username:
            try:
                conn = get_db_connection()
                if conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "UPDATE career_stats SET username = %s WHERE user_id = %s",
                            (username, user_id)
                        )
                        conn.commit()
            except Exception:
                pass
            finally:
                if conn:
                    return_db_connection(conn)
        
        # Calculate stats
        rating = stats['rating']
        rank_tier = get_rank_from_rating(rating)  # Get actual rank from rating
        total_matches = stats['total_matches']
        wins = stats['wins']
        losses = stats['losses']
        win_rate = safe_division(wins, total_matches, 0) * 100
        loss_rate = safe_division(losses, total_matches, 0) * 100
        current_streak = stats['current_streak']
        streak_type = stats['streak_type']
        highest_rating = stats['highest_rating']
        
        # Get current rank bounds and next rank
        min_rating, max_rating, current_tier = get_current_rank_bounds(rating)
        next_threshold, next_rank = get_next_rank_info(rating)
        
        if next_threshold:
            points_needed = next_threshold - rating
            tier_range = max_rating - min_rating
            progress_in_tier = rating - min_rating
            progress_pct = safe_division(progress_in_tier, tier_range, 0) * 100
            progress_bar = "█" * int(progress_pct / 10) + "░" * (10 - int(progress_pct / 10))
        else:
            points_needed = 0
            progress_bar = "██████████"
        
        # Streak text
        if streak_type == 'win' and current_streak > 0:
            streak_text = f"{current_streak} win streak 🔥"
        elif streak_type == 'loss' and current_streak > 0:
            streak_text = f"{current_streak} loss streak"
        else:
            streak_text = "No active streak"
        
        # Get trust score and status
        trust_score = stats.get('trust_score', 50)
        rating_suspended = stats.get('rating_suspended', False)
        account_flagged = stats.get('account_flagged', False)
        
        # Trust score emoji
        if trust_score >= 70:
            trust_emoji = "🟢"
        elif trust_score >= 40:
            trust_emoji = "🟡"
        elif trust_score >= 20:
            trust_emoji = "🟠"
        else:
            trust_emoji = "🔴"
        
        # Build message
        career_text = (
            f"🏆 *YOUR CAREER*\n"
            f"━━━━━━━━━━━━━━━━\n\n"
            f"*🎖️ RANK & RATING*\n"
            f"• Rank: {escape_markdown_v2_custom(rank_tier)}\n"
            f"• Rating: {escape_markdown_v2_custom(str(rating))}\n"
            f"• Trust: {trust_emoji} {trust_score}/100\n"
        )
        
        # Add warning if flagged
        if rating_suspended:
            career_text += f"• Status: ⛔ *SUSPENDED*\n"
        elif account_flagged:
            career_text += f"• Status: ⚠️ *Flagged*\n"
        
        career_text += (
            f"\n📊 *PERFORMANCE*\n"
            f"• Matches: {total_matches}\n"
            f"• Wins: {wins} \\({escape_markdown_v2_custom(f'{win_rate:.0f}%')}\\)\n"
            f"• Losses: {losses} \\({escape_markdown_v2_custom(f'{loss_rate:.0f}%')}\\)\n\n"
            f"🔥 *CURRENT STREAK*\n"
            f"• {escape_markdown_v2_custom(streak_text)}\n\n"
        )
        
        if next_threshold:
            career_text += (
                f"📈 *Progress*\n"
                f"{escape_markdown_v2_custom(rank_tier)} → {escape_markdown_v2_custom(next_rank)}\n"
                f"{escape_markdown_v2_custom(progress_bar)} {rating} / {next_threshold}\n"
                f"→ {escape_markdown_v2_custom(f'{points_needed} points to rank up')}\n"
            )
        else:
            career_text += (
                f"📈 *Progress*\n"
                f"🔥 MAX RANK ACHIEVED\\!\n"
            )
        
        career_text += (
            f"*🎯 PERSONAL BEST*\n"
            f"└─ Highest Rating: {highest_rating}\n\n"
            f"*💡 AVAILABLE COMMANDS*\n"
            f"• `/ranked` \\- Find a ranked match\n"
            f"• `/challenge @user` \\- Challenge someone\n"
            f"• `/leaderboard` \\- View top players\n"
            f"• `/ranks` \\- View all rank tiers"
        )
        
        await update.message.reply_text(
            career_text,
            parse_mode=ParseMode.MARKDOWN_V2
        )
        
    except Exception as e:
        logger.error(f"Error in career command: {e}")
        await update.message.reply_text(
            escape_markdown_v2_custom("❌ Error showing career profile. Please try again."),
            parse_mode=ParseMode.MARKDOWN_V2
        )

@check_blacklist()
async def rankedinfo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Explain ranked system and anti-cheat to users with pagination"""
    try:
        # Define all pages
        pages = [
            # Page 1: How Ranked Works
            (
                f"🏆 *RANKED SYSTEM \\- GUIDE* \\(1/4\\)\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"*📋 HOW RANKED WORKS \\(A to Z\\)*\n\n"
                f"1️⃣ *Start Playing*\n"
                f"   • Type `/ranked` to join queue\n"
                f"   • Bot finds opponent near your rating\n"
                f"   • Play cricket match\\!\n\n"
                f"2️⃣ *Win or Lose*\n"
                f"   • Win \\= Rating goes UP ⬆️\n"
                f"   • Lose \\= Rating goes DOWN ⬇️\n"
                f"   • More matches \\= Unlock full rewards\n\n"
                f"3️⃣ *Climb Ranks*\n"
                f"   • Everyone starts at Bronze III \\(1000\\)\n"
                f"   • Keep winning to reach Legend \\(3000\\+\\)\n"
                f"   • Check `/ranks` for all tiers\n\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"*🎯 TRUST SCORE EXPLAINED*\n\n"
                f"*What is it?*\n"
                f"A fairness score \\(0\\-100\\) that protects \n"
                f"against cheating and keeps matches fair\\.\n\n"
                f"*Trust Levels:*\n"
                f"🟢 *70\\-100* \\→ Perfect\\! Full rewards\n"
                f"🟡 *40\\-69* \\→ Good, play normally\n"
                f"🟠 *20\\-39* \\→ Low, only 50% rewards\n"
                f"🔴 *0\\-19* \\→ Very low, rating suspended"
            ),
            # Page 2: Trust Score Details
            (
                f"🏆 *RANKED SYSTEM \\- GUIDE* \\(2/4\\)\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"*🎯 KEEPING TRUST SCORE HIGH*\n\n"
                f"*How to KEEP trust high:*\n"
                f"✅ Play with different opponents\n"
                f"✅ Play naturally \\(win/lose naturally\\)\n"
                f"✅ Don't play same person repeatedly\n"
                f"✅ Be consistent and fair\n\n"
                f"*What LOWERS trust:*\n"
                f"❌ Playing same opponent 5\\+ times per day\n"
                f"❌ Suspicious patterns \\(taking turns winning\\)\n"
                f"❌ Trying to boost rating unfairly\n\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"*🆕 NEW PLAYERS*\n\n"
                f"*Why reduced rewards at start?*\n"
                f"To stop people from making fake accounts\n"
                f"and cheating the system\\.\n\n"
                f"*Rating gain unlocks gradually:*\n"
                f"• First 5 matches \\→ 30% rating gain\n"
                f"• Matches 6\\-10 \\→ 50% rating gain\n"
                f"• Matches 11\\-20 \\→ 75% rating gain\n"
                f"• After 20 matches \\→ 100% \\(full rewards\\)\n\n"
                f"_Just play 20 matches and you're fully unlocked\\!_"
            ),
            # Page 3: Getting Flagged & Recovery
            (
                f"🏆 *RANKED SYSTEM \\- GUIDE* \\(3/4\\)\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"*⚠️ WHAT IF I GET FLAGGED?*\n\n"
                f"*Why does flagging happen?*\n"
                f"Bot auto\\-detects suspicious activity to\n"
                f"protect fair players\\.\n\n"
                f"*Common triggers:*\n"
                f"• Playing 5\\+ matches vs same person/day\n"
                f"• Win\\-trading patterns detected\n"
                f"• Account too new \\(under 7 days old\\)\n\n"
                f"*What happens?*\n"
                f"• Your trust score drops\n"
                f"• You get less rating points\n"
                f"• Admins review your matches\n\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"*🔧 HOW TO FIX LOW TRUST*\n\n"
                f"*Step 1:* Stop playing same opponent\n"
                f"*Step 2:* Play with different people\n"
                f"*Step 3:* Keep playing fair matches\n"
                f"*Step 4:* Trust score slowly recovers\n\n"
                f"*Time needed:*\n"
                f"Usually takes 10\\-20 fair matches to\n"
                f"fully recover trust score\\."
            ),
            # Page 4: Challenge Mode & Commands
            (
                f"🏆 *RANKED SYSTEM \\- GUIDE* \\(4/4\\)\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"*🎮 CHALLENGE MODE \\- PLAY FRIENDS*\n\n"
                f"Want to play a specific person instead\n"
                f"of random matchmaking?\n\n"
                f"*How to challenge:*\n"
                f"1\\. Find any message from the player\n"
                f"2\\. Reply to their message\n"
                f"3\\. Type `/challenge`\n"
                f"4\\. Match starts immediately\\!\n\n"
                f"*Challenge rules:*\n"
                f"✅ Counts as ranked match\n"
                f"✅ Affects rating \\& trust score\n"
                f"✅ Same anti\\-cheat protection\n"
                f"✅ Must be within ±2 rank tiers\n"
                f"⚠️ Don't spam same person \\(5\\+ times/day\\)\n\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"*💡 GOLDEN RULES*\n"
                f"1\\. Play with VARIETY of opponents\n"
                f"2\\. Don't spam same person repeatedly\n"
                f"3\\. Play naturally and fairly\n"
                f"4\\. Check `/career` to see your trust score\n"
                f"5\\. Have fun and climb ranks\\!\n\n"
                f"_System is fair\\. Play fair\\. Have fun\\!_ 🎯"
            )
        ]
        
        # Create navigation buttons for first page
        keyboard = [[
            InlineKeyboardButton("Next ▶️", callback_data="rankedinfo_page_1")
        ]]
        
        await update.message.reply_text(
            pages[0],
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    except Exception as e:
        logger.error(f"Error in rankedinfo: {e}")
        await update.message.reply_text(
            "❌ Error showing ranked info\\. Use /help for commands\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )

async def handle_rankedinfo_pagination(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle pagination for rankedinfo command"""
    query = update.callback_query
    await query.answer()
    
    # Extract page number from callback data
    page = int(query.data.split("_")[-1])
    
    # Define all pages (same as in rankedinfo)
    pages = [
        # Page 1: How Ranked Works
        (
            f"🏆 *RANKED SYSTEM \\- GUIDE* \\(1/4\\)\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"*📋 HOW RANKED WORKS \\(A to Z\\)*\n\n"
            f"1️⃣ *Start Playing*\n"
            f"   • Type `/ranked` to join queue\n"
            f"   • Bot finds opponent near your rating\n"
            f"   • Play cricket match\\!\n\n"
            f"2️⃣ *Win or Lose*\n"
            f"   • Win \\= Rating goes UP ⬆️\n"
            f"   • Lose \\= Rating goes DOWN ⬇️\n"
            f"   • More matches \\= Unlock full rewards\n\n"
            f"3️⃣ *Climb Ranks*\n"
            f"   • Everyone starts at Bronze III \\(1000\\)\n"
            f"   • Keep winning to reach Legend \\(3000\\+\\)\n"
            f"   • Check `/ranks` for all tiers\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"*🎯 TRUST SCORE EXPLAINED*\n\n"
            f"*What is it?*\n"
            f"A fairness score \\(0\\-100\\) that protects \n"
            f"against cheating and keeps matches fair\\.\n\n"
            f"*Trust Levels:*\n"
            f"🟢 *70\\-100* \\→ Perfect\\! Full rewards\n"
            f"🟡 *40\\-69* \\→ Good, play normally\n"
            f"🟠 *20\\-39* \\→ Low, only 50% rewards\n"
            f"🔴 *0\\-19* \\→ Very low, rating suspended"
        ),
        # Page 2: Trust Score Details
        (
            f"🏆 *RANKED SYSTEM \\- GUIDE* \\(2/4\\)\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"*🎯 KEEPING TRUST SCORE HIGH*\n\n"
            f"*How to KEEP trust high:*\n"
            f"✅ Play with different opponents\n"
            f"✅ Play naturally \\(win/lose naturally\\)\n"
            f"✅ Don't play same person repeatedly\n"
            f"✅ Be consistent and fair\n\n"
            f"*What LOWERS trust:*\n"
            f"❌ Playing same opponent 5\\+ times per day\n"
            f"❌ Suspicious patterns \\(taking turns winning\\)\n"
            f"❌ Trying to boost rating unfairly\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"*🆕 NEW PLAYERS*\n\n"
            f"*Why reduced rewards at start?*\n"
            f"To stop people from making fake accounts\n"
            f"and cheating the system\\.\n\n"
            f"*Rating gain unlocks gradually:*\n"
            f"• First 5 matches \\→ 30% rating gain\n"
            f"• Matches 6\\-10 \\→ 50% rating gain\n"
            f"• Matches 11\\-20 \\→ 75% rating gain\n"
            f"• After 20 matches \\→ 100% \\(full rewards\\)\n\n"
            f"_Just play 20 matches and you're fully unlocked\\!_"
        ),
        # Page 3: Getting Flagged & Recovery
        (
            f"🏆 *RANKED SYSTEM \\- GUIDE* \\(3/4\\)\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"*⚠️ WHAT IF I GET FLAGGED?*\n\n"
            f"*Why does flagging happen?*\n"
            f"Bot auto\\-detects suspicious activity to\n"
            f"protect fair players\\.\n\n"
            f"*Common triggers:*\n"
            f"• Playing 5\\+ matches vs same person/day\n"
            f"• Win\\-trading patterns detected\n"
            f"• Account too new \\(under 7 days old\\)\n\n"
            f"*What happens?*\n"
            f"• Your trust score drops\n"
            f"• You get less rating points\n"
            f"• Admins review your matches\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"*🔧 HOW TO FIX LOW TRUST*\n\n"
            f"*Step 1:* Stop playing same opponent\n"
            f"*Step 2:* Play with different people\n"
            f"*Step 3:* Keep playing fair matches\n"
            f"*Step 4:* Trust score slowly recovers\n\n"
            f"*Time needed:*\n"
            f"Usually takes 10\\-20 fair matches to\n"
            f"fully recover trust score\\."
        ),
        # Page 4: Challenge Mode & Commands
        (
            f"🏆 *RANKED SYSTEM \\- GUIDE* \\(4/4\\)\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"*🎮 CHALLENGE MODE \\- PLAY FRIENDS*\n\n"
            f"Want to play a specific person instead\n"
            f"of random matchmaking?\n\n"
            f"*How to challenge:*\n"
            f"1\\. Find any message from the player\n"
            f"2\\. Reply to their message\n"
            f"3\\. Type `/challenge`\n"
            f"4\\. Match starts immediately\\!\n\n"
            f"*Challenge rules:*\n"
            f"✅ Counts as ranked match\n"
            f"✅ Affects rating \\& trust score\n"
            f"✅ Same anti\\-cheat protection\n"
            f"✅ Must be within ±2 rank tiers\n"
            f"⚠️ Don't spam same person \\(5\\+ times/day\\)\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"*💡 GOLDEN RULES*\n"
            f"1\\. Play with VARIETY of opponents\n"
            f"2\\. Don't spam same person repeatedly\n"
            f"3\\. Play naturally and fairly\n"
            f"4\\. Check `/career` to see your trust score\n"
            f"5\\. Have fun and climb ranks\\!\n\n"
            f"_System is fair\\. Play fair\\. Have fun\\!_ 🎯"
        )
    ]
    
    # Create navigation buttons based on current page
    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton("◀️ Previous", callback_data=f"rankedinfo_page_{page-1}"))
    if page < len(pages) - 1:
        buttons.append(InlineKeyboardButton("Next ▶️", callback_data=f"rankedinfo_page_{page+1}"))
    
    keyboard = [buttons] if buttons else None
    
    try:
        await query.edit_message_text(
            pages[page],
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None
        )
    except Exception as e:
        logger.error(f"Error in rankedinfo pagination: {e}")

# ===== PHASE 4: SOCIAL FEATURES =====

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show top players ranked by rating"""
    user_id = str(update.effective_user.id)
    user = update.effective_user
    
    await send_admin_log(
        f"CMD: /leaderboard by {user.first_name} (@{user.username or 'no_username'}, ID: {user_id})",
        log_type="command",
        chat_context=get_chat_context(update)
    )
    
    try:
        with DatabaseConnection() as conn:
            if not conn:
                await update.message.reply_text(
                    "❌ *Database Error*\n"
                    "Unable to load leaderboard\\. Try again later\\.",
                    parse_mode=ParseMode.MARKDOWN_V2
                )
                return
            
            with conn.cursor(cursor_factory=DictCursor) as cur:
                # Get top 10 players
                cur.execute("""
                    SELECT user_id, username, rating, rank_tier, total_matches, wins, losses
                    FROM career_stats
                    WHERE total_matches > 0
                    ORDER BY rating DESC
                    LIMIT 10
                """)
                top_players = cur.fetchall()
                
                # Get user's rank if not in top 10
                cur.execute("""
                    SELECT COUNT(*) + 1 as rank
                    FROM career_stats
                    WHERE rating > (SELECT rating FROM career_stats WHERE user_id = %s)
                    AND total_matches > 0
                """, (user_id,))
                user_rank_result = cur.fetchone()
                user_rank = user_rank_result['rank'] if user_rank_result else None
                
                # Get user's stats
                cur.execute("""
                    SELECT username, rating, rank_tier, total_matches, wins, losses
                    FROM career_stats
                    WHERE user_id = %s
                """, (user_id,))
                user_stats = cur.fetchone()
        
        if not top_players:
            await update.message.reply_text(
                "📊 *LEADERBOARD*\n"
                "━━━━━━━━━━━━━━\n\n"
                "No ranked players yet\\!\n"
                "Be the first to play ranked matches\\.",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return
        
        # Build leaderboard message with improved UI
        leaderboard_text = (
            "🏆  *HALL OF FAME*\n"
            "════════════════\n\n"
        )
        
        medal_emojis = ["🥇", "🥈", "🥉"]
        
        for idx, player in enumerate(top_players, 1):
            medal = medal_emojis[idx-1] if idx <= 3 else f"⚡"
            username = player['username']
            rating = player['rating']
            rank_tier = player['rank_tier']
            total = player['total_matches']
            
            # Escape username and rank
            username_escaped = escape_markdown_v2_custom(username)
            rank_tier_escaped = escape_markdown_v2_custom(rank_tier)
            
            leaderboard_text += (
                f"{medal} *\\#{idx}* {username_escaped}\n"
                f"   ⚡ *{rating}* \\({rank_tier_escaped}\\) │ {total} matches\n\n"
            )
        
        leaderboard_text += "━━━━━━━━━━━━━━━━━━━━━━\n"
        
        # Add user's position if not in top 10
        if user_rank and user_rank > 10 and user_stats:
            username_escaped = escape_markdown_v2_custom(user_stats['username'])
            rank_escaped = escape_markdown_v2_custom(user_stats['rank_tier'])
            user_rating = user_stats['rating']
            
            leaderboard_text += (
                f"\n📍 *Your Position*\n"
                f"   Rank: *\\#{user_rank}*\n"
                f"   Rating: *{user_rating}*\n"
                f"   Tier: {rank_escaped}\n"
            )

        
        await update.message.reply_text(
            leaderboard_text,
            parse_mode=ParseMode.MARKDOWN_V2
        )
        
    except Exception as e:
        logger.error(f"Error in leaderboard command: {e}")
        await update.message.reply_text(
            "❌ *Error*\n"
            "Failed to load leaderboard\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )

async def ranks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show all rank tiers and rating thresholds"""
    user_id = str(update.effective_user.id)
    
    try:
        # Get user's current stats
        stats = await get_career_stats(user_id)
        user_rating = stats['rating'] if stats else 0
        user_rank = get_rank_from_rating(user_rating) if stats else "Unranked"
        
        # Define all rank tiers with emojis
        rank_tiers = [
            ("🟫 BRONZE", [
                ("Bronze I", 0, 199),
                ("Bronze II", 200, 399),
                ("Bronze III", 400, 599)
            ]),
            ("⚪ SILVER", [
                ("Silver I", 600, 799),
                ("Silver II", 800, 999),
                ("Silver III", 1000, 1199)
            ]),
            ("🟡 GOLD", [
                ("Gold I", 1200, 1399),
                ("Gold II", 1400, 1599),
                ("Gold III", 1600, 1799)
            ]),
            ("🔵 PLATINUM", [
                ("Platinum I", 1800, 1999),
                ("Platinum II", 2000, 2199),
                ("Platinum III", 2200, 2399)
            ]),
            ("💎 DIAMOND", [
                ("Diamond I", 2400, 2799),
                ("Diamond II", 2800, 3199),
                ("Diamond III", 3200, 3999)
            ]),
            ("🔴 RUBY", [
                ("Ruby I", 4000, 4399),
                ("Ruby II", 4400, 4799),
                ("Ruby III", 4800, 4999)
            ]),
            ("⭐ IMMORTAL", [
                ("Immortal I", 5000, 5499),
                ("Immortal II", 5500, 5999),
                ("Immortal III", 6000, 99999)
            ])
        ]
        
        # Build ranks info message
        ranks_text = (
            "📊 *RANK SYSTEM INFO* 📊\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
        )
        
        for tier_name, tier_ranks in rank_tiers:
            ranks_text += f"*{escape_markdown_v2_custom(tier_name)}*\n"
            
            for rank_name, min_r, max_r in tier_ranks:
                # Check if this is user's current rank
                is_current = (stats and min_r <= user_rating <= max_r)
                marker = " ← *YOU ARE HERE*" if is_current else ""
                
                # Format range
                if max_r >= 99999:
                    range_str = f"{min_r}\\+"
                else:
                    range_str = f"{min_r} \\- {max_r}"
                
                rank_escaped = escape_markdown_v2_custom(rank_name)
                ranks_text += f"  {rank_escaped} • {range_str}{marker}\n"
            
            ranks_text += "\n"
        
        # Add user's status
        if stats:
            next_threshold, next_rank = get_next_rank_info(user_rating)
            if next_threshold:
                points_needed = next_threshold - user_rating
                ranks_text += "━━━━━━━━━━━━━━━━━━━━━\n"
                ranks_text += f"*YOUR STATUS:*\n"
                user_rank_escaped = escape_markdown_v2_custom(user_rank)
                ranks_text += f"Rating: {user_rating} \\({user_rank_escaped}\\)\n"
                next_rank_escaped = escape_markdown_v2_custom(next_rank)
                ranks_text += f"Next: {next_rank_escaped} at {next_threshold}\n"
                ranks_text += f"Need: *{points_needed} more points\\!* 🎯"
            else:
                ranks_text += "━━━━━━━━━━━━━━━━━━━━━\n"
                ranks_text += f"*YOU'VE REACHED MAX RANK\\!* ⭐"
        
        await update.message.reply_text(
            ranks_text,
            parse_mode=ParseMode.MARKDOWN_V2
        )
        
    except Exception as e:
        logger.error(f"Error in ranks command: {e}")
        await update.message.reply_text(
            "❌ *Error*\n"
            "Failed to load rank info\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )

# ===== PHASE 2: RANKED MATCHMAKING COMMANDS =====

async def ranked(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Join ranked matchmaking queue"""
    user_id = update.effective_user.id
    username = update.effective_user.first_name or "Player"
    chat_id = update.effective_chat.id
    user = update.effective_user
    
    await send_admin_log(
        f"CMD: /ranked by {username} (@{user.username or 'no_username'}, ID: {user_id})",
        log_type="command",
        chat_context=get_chat_context(update)
    )
    
    try:
        # Check if user is already in a game
        if str(chat_id) in games:
            await update.message.reply_text(
                "❌ *Error*\n"
                "You're already in an active game\\!\n"
                "Finish your current match before joining ranked queue\\.",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return
        
        # Check if already in queue
        if user_id in ranked_queue:
            queue_data = ranked_queue[user_id]
            elapsed = int(time.time() - queue_data['joined_at'])
            await update.message.reply_text(
                f"🔍 *ALREADY SEARCHING*\n"
                f"━━━━━━━━━━━━━━━━\n\n"
                f"⏱️ Searching\\.\\.\\. {elapsed}s\n"
                f"🎯 Range: {queue_data['rating'] - RANKED_RATING_RANGE}\\-{queue_data['rating'] + RANKED_RATING_RANGE}\n\n"
                f"_Use /cancel\\_queue to stop searching\\._",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return
        
        # Check queue join cooldown
        if user_id in user_queue_cooldown:
            time_since_last = time.time() - user_queue_cooldown[user_id]
            if time_since_last < QUEUE_JOIN_COOLDOWN:
                wait_time = int(QUEUE_JOIN_COOLDOWN - time_since_last)
                await update.message.reply_text(
                    f"⏳ *COOLDOWN ACTIVE*\n"
                    f"━━━━━━━━━━━━━━━━\n\n"
                    f"Wait {wait_time}s before searching again\\.",
                    parse_mode=ParseMode.MARKDOWN_V2
                )
                return
        
        # Get user's career stats
        stats = await get_career_stats(str(user_id))
        if not stats:
            await update.message.reply_text(
                "❌ *Registration Required*\n"
                "Use /start to create your account first\\!",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return
        
        # ========== ANTI-CHEAT CHECKS ==========
        
        # Check 1: Account age verification (DISABLED - checks bot registration, not Telegram account age)
        # Telegram API doesn't provide account creation date, only user ID
        # Lower user IDs = older accounts, but this isn't reliable enough
        # Commenting out to avoid false positives
        """
        is_valid_age, account_age = await check_telegram_account_age(update.effective_user)
        if not is_valid_age:
            await update.message.reply_text(
                f"🔒 *ACCOUNT TOO NEW*\n"
                f"━━━━━━━━━━━━━━━━\n\n"
                f"Your Telegram account must be at least {MIN_TELEGRAM_ACCOUNT_AGE_DAYS} days old\\.\n\n"
                f"Current age: {account_age} days\n"
                f"Required: {MIN_TELEGRAM_ACCOUNT_AGE_DAYS} days\n\n"
                f"_This prevents multi\\-accounting and smurfing\\._",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return
        """
        
        # Check 2: Trust score check
        trust_score = stats.get('trust_score', 50)
        if trust_score < SUSPEND_TRUST_SCORE:
            await update.message.reply_text(
                f"⛔ *RANKED ACCESS SUSPENDED*\n"
                f"━━━━━━━━━━━━━━━━\n\n"
                f"Your trust score is too low \\({trust_score}/100\\)\n\n"
                f"_Contact an admin if you believe this is an error\\._",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return
        
        # Check 3: Rating suspension check
        if stats.get('rating_suspended', False):
            suspension_reason = stats.get('suspension_reason', 'Suspicious activity detected')
            await update.message.reply_text(
                f"⛔ *RATING SUSPENDED*\n"
                f"━━━━━━━━━━━━━━━━\n\n"
                f"Your rating has been suspended\\.\n\n"
                f"*Reason:* {escape_markdown_v2_custom(suspension_reason)}\n\n"
                f"_Contact an admin for more information\\._",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return
        
        # Check 4: Low trust score warning
        if trust_score < MIN_TRUST_SCORE:
            await update.message.reply_text(
                f"⚠️ *LOW TRUST SCORE*\n"
                f"━━━━━━━━━━━━━━━━\n\n"
                f"Your trust score is {trust_score}/100\n"
                f"Rating gains will be reduced by 50%\\.\n\n"
                f"_Play fair to improve your trust score\\._",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            await asyncio.sleep(3)
        
        # ========== END ANTI-CHEAT CHECKS ==========
        
        rating = stats['rating']
        rank_tier = stats['rank_tier']
        
        # Send initial searching message
        search_message = await update.message.reply_text(
            f"🔍  *SEARCHING FOR OPPONENT\\.\\.\\.* \n"
            f"════════════════════════\n\n"
            f"👤 *Player:* {escape_markdown_v2_custom(username)}\n"
            f"🎖️ *Rating:* {rating} \\({escape_markdown_v2_custom(rank_tier)}\\)\n"
            f"⏱️ *Time:* 0s\n"
            f"📡 *Range:* ±{RANKED_RATING_RANGE}",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        
        # Add to queue
        success = await add_to_ranked_queue(user_id, username, rating, rank_tier, search_message)
        if not success:
            await search_message.edit_text(
                "❌ *Server Error*\n"
                "Failed to join ranked queue\\. Try again in a moment\\.",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return
        
        # Update cooldown
        user_queue_cooldown[user_id] = time.time()
        
        # Try to find match immediately
        opponent = await find_ranked_opponent(user_id, rating)
        
        if opponent:
            # Match found immediately!
            await search_message.edit_text(
                f"✅  *MATCH FOUND\\!*\n"
                f"════════════════\n"
                f"⚔️ *Opponent:* {escape_markdown_v2_custom(opponent['username'])}\n"
                f"📊 *Rating:* {opponent['rating']} \\({escape_markdown_v2_custom(opponent['rank_tier'])}\\)\n\n"
                f"🏆 *Your Rating:* {rating} \\({escape_markdown_v2_custom(rank_tier)}\\)\n\n"
                f"_Starting game in 3 seconds\\.\\.\\._",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            
            # Notify opponent
            if opponent.get('message'):
                try:
                    await opponent['message'].edit_text(
                        f"✅  *MATCH FOUND\\!*\n"
                        f"════════════════\n"
                        f"⚔️ *Opponent:* {escape_markdown_v2_custom(username)}\n"
                        f"📊 *Rating:* {rating} \\({escape_markdown_v2_custom(rank_tier)}\\)\n\n"
                        f"🏆 *Your Rating:* {opponent['rating']} \\({escape_markdown_v2_custom(opponent['rank_tier'])}\\)\n\n"
                        f"_Starting game in 3 seconds\\.\\.\\._",
                        parse_mode=ParseMode.MARKDOWN_V2
                    )
                except:
                    pass
            
            # Wait 3 seconds
            await asyncio.sleep(3)
            
            # Create ranked match
            match_id = await create_ranked_match(
                {'user_id': user_id, 'username': username, 'rating': rating, 'rank_tier': rank_tier},
                opponent,
                chat_id
            )
            
            if match_id:
                # Log match start to admin
                await send_admin_log(
                    f"Match #{match_id} Started | Players: {username} ({rating}) vs {opponent['username']} ({opponent['rating']})",
                    log_type="match"
                )
                
                # Start the toss
                game = games[str(chat_id)]
                game_id = str(chat_id)  # Use chat_id as game_id for lookup
                
                # Set toss player (player 1 chooses)
                game['choosing_player'] = user_id
                game['choosing_player_name'] = username
                
                # Create toss buttons with correct format
                keyboard = [
                    [
                        InlineKeyboardButton("ODD", callback_data=f"toss_{game_id}_odd"),
                        InlineKeyboardButton("EVEN", callback_data=f"toss_{game_id}_even")
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                # Tag both users
                user_mention = f"[{escape_markdown_v2_custom(username)}](tg://user?id={user_id})"
                opponent_mention = f"[{escape_markdown_v2_custom(opponent['username'])}](tg://user?id={opponent['user_id']})"
                
                toss_text = (
                    f"🏆 *RANKED MATCH \\- {escape_markdown_v2_custom(match_id)}*\n"
                    f"━━━━━━━━━━━━━━\n\n"
                    f"*🎮 PLAYERS*\n"
                    f"🔹 {user_mention} \\({rating}\\)\n"
                    f"🔸 {opponent_mention} \\({opponent['rating']}\\)\n\n"
                    f"*🏏 FORMAT*\n"
                    f"Mode: Survival \\(1 wicket, unlimited overs\\)\n"
                    f"Type: Ranked \\(Rated Match\\)\n\n"
                    f"*🎲 TOSS TIME*\n"
                    f"_{user_mention}, choose ODD or EVEN\\!_"
                )
                
                await search_message.edit_text(
                    toss_text,
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.MARKDOWN_V2
                )
                
                # Update opponent's message to show waiting state WITH user tags
                if opponent.get('message'):
                    try:
                        # Tag both users
                        user_mention = f"[{escape_markdown_v2_custom(username)}](tg://user?id={user_id})"
                        opponent_mention = f"[{escape_markdown_v2_custom(opponent['username'])}](tg://user?id={opponent['user_id']})"
                        
                        opponent_text = (
                            f"🏆 *RANKED MATCH \\- {escape_markdown_v2_custom(match_id)}*\n"
                            f"━━━━━━━━━━━━━━\n\n"
                            f"*🎮 PLAYERS*\n"
                            f"🔹 {user_mention} \\({rating}\\)\n"
                            f"🔸 {opponent_mention} \\({opponent['rating']}\\)\n\n"
                            f"*🏏 FORMAT*\n"
                            f"Mode: Survival \\(1 wicket, unlimited overs\\)\n"
                            f"Type: Ranked \\(Rated Match\\)\n\n"
                            f"*⏳ WAITING*\n"
                            f"_{user_mention} is choosing the toss\\.\\.\\._"
                        )
                        await opponent['message'].edit_text(
                            opponent_text,
                            parse_mode=ParseMode.MARKDOWN_V2
                        )
                    except:
                        pass
                
                logger.info(f"🎮 Ranked match started: {match_id}")
            else:
                await send_admin_log(
                    f"ERROR: Ranked match creation failed for {username} (ID: {user_id}) vs {opponent['username']} (ID: {opponent['user_id']})",
                    log_type="error"
                )
                await search_message.edit_text(
                    "❌ *Error*\n"
                    "Failed to create ranked match\\. Please try again\\.",
                    parse_mode=ParseMode.MARKDOWN_V2
                )
        else:
            # No match found, start periodic search
            search_task = asyncio.create_task(
                update_search_message(user_id, search_message, username, rating, rank_tier)
            )
            queue_search_tasks[user_id] = search_task
            
            # Also start periodic matchmaking checks
            asyncio.create_task(periodic_matchmaking_check(user_id, chat_id))
        
    except Exception as e:
        logger.error(f"Error in ranked command: {e}")
        await update.message.reply_text(
            "❌ *Error*\n"
            "Failed to join ranked queue\\. Please try again\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )

async def periodic_matchmaking_check(user_id: int, chat_id: int):
    """Periodically check for opponents while in queue"""
    try:
        while user_id in ranked_queue:
            await asyncio.sleep(3)  # Check every 3 seconds
            
            if user_id not in ranked_queue:
                break
            
            user_data = ranked_queue[user_id]
            opponent = await find_ranked_opponent(user_id, user_data['rating'])
            
            if opponent:
                # Match found!
                message = user_data.get('message')
                username = user_data['username']
                rating = user_data['rating']
                rank_tier = user_data['rank_tier']
                
                if message:
                    try:
                        await message.edit_text(
                            f"✅ *Match Found\\!*\n"
                            f"━━━━━━━━━━━━━━\n"
                            f"⚔️ Opponent: {escape_markdown_v2_custom(opponent['username'])}\n"
                            f"📊 Their Rating: {opponent['rating']} \\({escape_markdown_v2_custom(opponent['rank_tier'])}\\)\n"
                            f"🏆 Your Rating: {rating} \\({escape_markdown_v2_custom(rank_tier)}\\)\n\n"
                            f"_Starting game in 3 seconds\\.\\.\\._",
                            parse_mode=ParseMode.MARKDOWN_V2
                        )
                    except BadRequest as e:
                        if "message is not modified" not in str(e).lower():
                            raise
                
                # Notify opponent
                if opponent.get('message'):
                    try:
                        await opponent['message'].edit_text(
                            f"✅ *Match Found\\!*\n"
                            f"━━━━━━━━━━━━━━\n"
                            f"⚔️ Opponent: {escape_markdown_v2_custom(username)}\n"
                            f"📊 Their Rating: {rating} \\({escape_markdown_v2_custom(rank_tier)}\\)\n"
                            f"🏆 Your Rating: {opponent['rating']} \\({escape_markdown_v2_custom(opponent['rank_tier'])}\\)\n\n"
                            f"_Starting game in 3 seconds\\.\\.\\._",
                            parse_mode=ParseMode.MARKDOWN_V2
                        )
                    except:
                        pass
                
                await asyncio.sleep(3)
                
                # Create ranked match
                match_id = await create_ranked_match(
                    {'user_id': user_id, 'username': username, 'rating': rating, 'rank_tier': rank_tier},
                    opponent,
                    chat_id
                )
                
                if match_id and message:
                    game = games[str(chat_id)]
                    game_id = str(chat_id)  # Use chat_id as game_id for lookup
                    
                    # Set toss player (player 1 chooses)
                    game['choosing_player'] = user_id
                    game['choosing_player_name'] = username
                    
                    keyboard = [
                        [
                            InlineKeyboardButton("ODD", callback_data=f"toss_{game_id}_odd"),
                            InlineKeyboardButton("EVEN", callback_data=f"toss_{game_id}_even")
                        ]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    
                    toss_text = (
                        f"🏆 *RANKED MATCH \\- {escape_markdown_v2_custom(match_id)}*\n"
                        f"━━━━━━━━━━━━━━\n\n"
                        f"*🎮 PLAYERS*\n"
                        f"🔹 {escape_markdown_v2_custom(username)} \\({rating}\\)\n"
                        f"🔸 {escape_markdown_v2_custom(opponent['username'])} \\({opponent['rating']}\\)\n\n"
                        f"*🏏 FORMAT*\n"
                        f"Mode: Survival \\(1 wicket, unlimited overs\\)\n"
                        f"Type: Ranked \\(Rated Match\\)\n\n"
                        f"*🪙 TOSS TIME*\n"
                        f"{escape_markdown_v2_custom(username)}, call it\\!"
                    )
                    
                    try:
                        await message.edit_text(
                            toss_text,
                            reply_markup=reply_markup,
                            parse_mode=ParseMode.MARKDOWN_V2
                        )
                    except BadRequest as e:
                        if "message is not modified" not in str(e).lower():
                            raise
                    
                    # Update opponent's message to show waiting state (no buttons)
                    if opponent.get('message'):
                        try:
                            opponent_text = (
                                f"🏆 *RANKED MATCH \\- {escape_markdown_v2_custom(match_id)}*\n"
                                f"━━━━━━━━━━━━━━\n\n"
                                f"*🎮 PLAYERS*\n"
                                f"🔹 {escape_markdown_v2_custom(username)} \\({rating}\\)\n"
                                f"🔸 {escape_markdown_v2_custom(opponent['username'])} \\({opponent['rating']}\\)\n\n"
                                f"*🏏 FORMAT*\n"
                                f"Mode: Survival \\(1 wicket, unlimited overs\\)\n"
                                f"Type: Ranked \\(Rated Match\\)\n\n"
                                f"*⏳ WAITING*\n"
                                f"_{escape_markdown_v2_custom(username)} is choosing the toss\\.\\.\\._"
                            )
                            await opponent['message'].edit_text(
                                opponent_text,
                                parse_mode=ParseMode.MARKDOWN_V2
                            )
                        except:
                            pass
                
                break
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"Error in periodic matchmaking check: {e}")

async def cancel_queue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel ranked matchmaking search"""
    user_id = update.effective_user.id
    
    try:
        if user_id not in ranked_queue:
            await update.message.reply_text(
                "❌ *NOT IN QUEUE*\n"
                "━━━━━━━━━━━━━━━━\n\n"
                "You're not currently searching for a ranked match\\.",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return
        
        # Remove from queue
        await remove_from_ranked_queue(user_id)
        
        await update.message.reply_text(
            "❌ *SEARCH CANCELED*\n"
            "━━━━━━━━━━━━━━━━\n\n"
            "You've left the ranked queue\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        
    except Exception as e:
        logger.error(f"Error in cancel_queue command: {e}")
        await update.message.reply_text(
            "❌ *Error*\n"
            "Failed to cancel queue search\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )

# ========================================
# PHASE 3: CHALLENGE SYSTEM
# ========================================

async def challenge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Challenge another player by replying to their message with /challenge"""
    user_id = update.effective_user.id
    username = update.effective_user.first_name or update.effective_user.username or "Player"
    chat_id = update.effective_chat.id
    chat_type = update.effective_chat.type
    
    # Get chat context for logging
    if chat_type == 'private':
        chat_context = "DM"
    else:
        chat_title = update.effective_chat.title or "Group"
        chat_context = f"GC: {chat_title} ({chat_id})"
    
    logger.info(f"Challenge command received from {username} ({user_id}) in chat {chat_id}")
    
    # Log command usage
    await send_admin_log(
        f"CMD: /challenge by {username} (ID: {user_id})",
        log_type="command",
        chat_context=chat_context
    )
    
    try:
        # Check if this is in a group
        if chat_type == 'private':
            logger.info(f"Challenge rejected - private chat")
            await update.message.reply_text(
                "❌ *Group Only*\n"
                "Challenges can only be used in groups\\!",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return
        
        # Check if this is a reply
        if not update.message.reply_to_message:
            logger.info(f"Challenge rejected - not a reply")
            await update.message.reply_text(
                "❌ *How to Challenge*\n"
                "Reply to someone's message with /challenge to challenge them\\!",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return
        
        # Get target user from replied message
        target = update.message.reply_to_message.from_user
        target_id = target.id
        target_name = target.first_name or target.username or "Player"
        
        # Validation checks
        if target_id == user_id:
            await update.message.reply_text(
                "❌ *INVALID CHALLENGE*\n"
                "━━━━━━━━━━━━━━━━\n\n"
                "You can't challenge yourself\\!",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return
        
        if target.is_bot:
            await update.message.reply_text(
                "❌ *INVALID CHALLENGE*\n"
                "━━━━━━━━━━━━━━━━\n\n"
                "You can't challenge bots\\!",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return
        
        # Check if both users have career stats
        logger.info(f"Fetching career stats for challenger {user_id} and target {target_id}")
        challenger_stats = await get_career_stats(str(user_id))
        target_stats = await get_career_stats(str(target_id))
        
        logger.info(f"Challenger stats: {challenger_stats}")
        logger.info(f"Target stats: {target_stats}")
        
        if not challenger_stats:
            logger.info(f"Challenger not registered")
            await update.message.reply_text(
                "❌ *NOT REGISTERED*\n"
                "━━━━━━━━━━━━━━━━\n\n"
                "You need to play a ranked match first\\!\n\n"
                "Use /ranked to start\\.",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return
        
        if not target_stats:
            await update.message.reply_text(
                f"❌ *INVALID TARGET*\n"
                f"━━━━━━━━━━━━━━━━\n\n"
                f"{escape_markdown_v2_custom(target_name)} hasn't played ranked yet\\!",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return
        
        # ========== ANTI-CHEAT CHECKS FOR CHALLENGES ==========
        
        # Check challenger's trust score
        challenger_trust = challenger_stats.get('trust_score', 50)
        if challenger_trust < SUSPEND_TRUST_SCORE:
            await update.message.reply_text(
                f"⛔ *CHALLENGE BLOCKED*\n"
                f"━━━━━━━━━━━━━━━━\n\n"
                f"Your trust score is too low \\({challenger_trust}/100\\)\n"
                f"You cannot send challenges\\.\n\n"
                f"_Contact an admin if you believe this is an error\\._",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return
        
        # Check if challenger rating is suspended
        if challenger_stats.get('rating_suspended', False):
            suspension_reason = challenger_stats.get('suspension_reason', 'Suspicious activity detected')
            await update.message.reply_text(
                f"⛔ *RATING SUSPENDED*\n"
                f"━━━━━━━━━━━━━━━━\n\n"
                f"Your rating is suspended\n"
                f"You cannot send challenges\\.\n\n"
                f"*Reason:* {escape_markdown_v2_custom(suspension_reason)}",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return
        
        # Check match pattern between these players (skip if it fails to avoid blocking challenges)
        try:
            is_suspicious, reason, pattern = await check_match_patterns(str(user_id), str(target_id))
            if is_suspicious and pattern.get('recent', 0) >= SUSPICIOUS_OPPONENT_FREQUENCY:
                logger.info(f"Challenge blocked - too many matches: {user_id} vs {target_id}")
                await update.message.reply_text(
                    f"⚠️ *TOO MANY MATCHES*\n"
                    f"━━━━━━━━━━━━━━━━\n\n"
                    f"You've played {pattern['recent']} matches with this opponent in 24h\\.\n"
                    f"Take a break and play with others\\!\n\n"
                    f"_This prevents rating manipulation\\._",
                    parse_mode=ParseMode.MARKDOWN_V2
                )
                return
        except Exception as e:
            logger.error(f"Error checking match patterns (continuing anyway): {e}")
        
        # Low trust warning
        if challenger_trust < MIN_TRUST_SCORE:
            await update.message.reply_text(
                f"⚠️ *LOW TRUST WARNING*\n"
                f"━━━━━━━━━━━━━━━━\n\n"
                f"Trust Score: {challenger_trust}/100\n"
                f"Rating gains reduced by 50%\\.\n\n"
                f"_Continuing with challenge\\.\\.\\._",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            await asyncio.sleep(2)
        
        # ========== END ANTI-CHEAT CHECKS ==========
        
        # Check rank tier distance (must be within ±2 tiers)
        challenger_rank = challenger_stats['rank_tier']
        target_rank = target_stats['rank_tier']
        logger.info(f"Checking tier distance between {challenger_rank} and {target_rank}")
        tier_distance = get_rank_tier_distance(challenger_rank, target_rank)
        logger.info(f"Tier distance calculated: {tier_distance}")
        
        if tier_distance > 2:
            await update.message.reply_text(
                f"❌ *RANK DIFFERENCE*\n"
                f"━━━━━━━━━━━━━━━━\n\n"
                f"• *Your Rank:* {escape_markdown_v2_custom(challenger_rank)}\n"
                f"• *Their Rank:* {escape_markdown_v2_custom(target_rank)}\n\n"
                f"_You can only challenge players within ±2 rank tiers\\!_",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return
        
        # Check if both players are available
        logger.info(f"Checking if players are available: challenger={user_id}, target={target_id}")
        if not await is_player_available(user_id):
            logger.info(f"Challenge blocked - challenger {user_id} is busy")
            await update.message.reply_text(
                "❌ *YOU'RE BUSY*\n"
                "━━━━━━━━━━━━━━━━\n\n"
                "Finish your current match or leave the queue first\\!",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return
        
        if not await is_player_available(target_id):
            logger.info(f"Challenge blocked - target {target_id} is busy")
            await update.message.reply_text(
                f"❌ *PLAYER BUSY*\n"
                f"━━━━━━━━━━━━━━━━\n\n"
                f"{escape_markdown_v2_custom(target_name)} is currently in a match or queue\\!",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return
        
        # Create challenge ID
        challenge_id = f"CH{random.randint(1000, 9999)}"
        logger.info(f"Creating challenge {challenge_id}: {user_id} -> {target_id}")
        
        # Store challenge in database
        try:
            logger.info(f"Attempting to store challenge {challenge_id} in database")
            with DatabaseConnection() as conn:
                with conn.cursor() as cur:
                    expires_at = datetime.now() + timedelta(seconds=60)
                    
                    cur.execute("""
                        INSERT INTO pending_challenges 
                        (challenge_id, challenger_id, target_id, challenger_name, target_name,
                         challenger_rating, target_rating, challenger_rank, target_rank, expires_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        challenge_id, user_id, target_id, username, target_name,
                        challenger_stats['rating'], target_stats['rating'],
                        challenger_rank, target_rank, expires_at
                    ))
                    
                    conn.commit()
                    logger.info(f"Challenge {challenge_id} successfully stored in database")
        
        except Exception as e:
            logger.error(f"Error creating challenge {challenge_id}: {e}", exc_info=True)
            await update.message.reply_text(
                "❌ *Error*\n"
                "Failed to create challenge\\.",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return
        
        # Create accept/decline buttons
        keyboard = [
            [
                InlineKeyboardButton("✅ Accept", callback_data=f"challenge_accept_{challenge_id}"),
                InlineKeyboardButton("❌ Decline", callback_data=f"challenge_decline_{challenge_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Send challenge notification in group
        # Send challenge notification in group
        challenge_text = (
            f"⚔️ <b>RANKED CHALLENGE</b>\n"
            f"════════════════════\n\n"
            f"🔴 <a href='tg://user?id={user_id}'>{html_escape(username)}</a> <b>VS</b> 🔵 <a href='tg://user?id={target_id}'>{html_escape(target_name)}</a>\n\n"
            f"⚠️ <b>RANKED MATCH ALERT</b>\n"
            f"Risk: Rating updates enabled\n\n"
            f"👇 <i><a href='tg://user?id={target_id}'>{html_escape(target_name)}</a>, do you accept?</i>"
        )
        
        try:
            logger.info(f"Sending challenge notification for {challenge_id} to group {chat_id}")
            # Send in group chat
            challenge_msg = await update.message.reply_text(
                text=challenge_text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML
            )
            logger.info(f"Challenge {challenge_id} notification sent successfully (msg_id: {challenge_msg.message_id})")
            
            # Store chat_id and message_id in database for later updates
            try:
                conn = get_db_connection()
                if conn:
                    with conn.cursor() as cur:
                        # Use 'pending' as status since the full string is too long for varchar(20)
                        cur.execute("""
                            UPDATE pending_challenges 
                            SET status = %s
                            WHERE challenge_id = %s
                        """, ('pending', challenge_id))
                        conn.commit()
            except Exception as e:
                logger.error(f"Error updating challenge with chat info: {e}")
            finally:
                if conn:
                    return_db_connection(conn)
            
            # Start timeout task
            asyncio.create_task(challenge_timeout_task(challenge_id, user_id, target_id, chat_id, challenge_msg.message_id, context))
            logger.info(f"Challenge {challenge_id} timeout task started")
            
        except Exception as e:
            logger.error(f"Error sending challenge notification for {challenge_id}: {e}", exc_info=True)
            # Remove challenge from database
            try:
                with DatabaseConnection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("DELETE FROM pending_challenges WHERE challenge_id = %s", (challenge_id,))
                        conn.commit()
            except:
                pass
            
            await update.message.reply_text(
                "❌ *Challenge Failed*\n"
                "Couldn't send challenge\\!",
                parse_mode=ParseMode.MARKDOWN_V2
            )
    
    except Exception as e:
        logger.error(f"Critical error in challenge command: {e}", exc_info=True)
        try:
            await update.message.reply_text(
                "❌ *Error*\n"
                "Something went wrong\\!",
                parse_mode=ParseMode.MARKDOWN_V2
            )
        except:
            pass  # If even error message fails, log it
            logger.error(f"Failed to send error message in challenge command")

async def handle_challenge_accept(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle challenge acceptance"""
    query = update.callback_query
    await query.answer()
    
    challenge_id = query.data.replace("challenge_accept_", "")
    target_id = update.effective_user.id
    chat_id = update.effective_chat.id
    chat_id = update.effective_chat.id
    
    try:
        conn = get_db_connection()
        if not conn:
            await query.edit_message_text(
                "❌ <b>Database Error</b>\n"
                "Please try again later.",
                parse_mode=ParseMode.HTML
            )
            return
        
        with conn.cursor() as cur:
            # Get challenge details
            cur.execute("""
                SELECT challenger_id, target_id, challenger_name, target_name,
                       challenger_rating, target_rating, status, expires_at
                FROM pending_challenges
                WHERE challenge_id = %s
            """, (challenge_id,))
            
            result = cur.fetchone()
            
            if not result:
                await query.edit_message_text(
                    "❌ <b>Challenge Not Found</b>\n"
                    "This challenge has expired or been canceled.",
                    parse_mode=ParseMode.HTML
                )
                return
            
            challenger_id, db_target_id, challenger_name, target_name, \
                challenger_rating, target_rating, status, expires_at = result
            
            # Verify it's the right person accepting
            if target_id != db_target_id:
                await query.answer("❌ This challenge is not for you!", show_alert=True)
                return
            
            # Check if already accepted/declined/expired
            if status != 'pending':
                await query.edit_message_text(
                    f"❌ <b>Challenge {status.title()}</b>\n"
                    f"This challenge is no longer available.",
                    parse_mode=ParseMode.HTML
                )
                return
            
            # Check if expired
            if datetime.now() > expires_at:
                cur.execute("""
                    UPDATE pending_challenges SET status = 'expired'
                    WHERE challenge_id = %s
                """, (challenge_id,))
                conn.commit()
                
                await query.edit_message_text(
                    "⏱️ <b>Challenge Expired</b>\n"
                    "This challenge has timed out.",
                    parse_mode=ParseMode.HTML
                )
                return
            
            # Check if both players are still available
            if not await is_player_available(challenger_id):
                cur.execute("""
                    UPDATE pending_challenges SET status = 'canceled'
                    WHERE challenge_id = %s
                """, (challenge_id,))
                conn.commit()
                
                await query.edit_message_text(
                    f"❌ <b>Challenge Canceled</b>\n"
                    f"<a href='tg://user?id={challenger_id}'>{challenger_name}</a> is no longer available.",
                    parse_mode=ParseMode.HTML
                )
                return
            
            if not await is_player_available(target_id):
                await query.edit_message_text(
                    "❌ <b>You're Busy</b>\n"
                    "Finish your current match or leave the queue first!",
                    parse_mode=ParseMode.HTML
                )
                return
            
            # Mark challenge as accepted
            cur.execute("""
                UPDATE pending_challenges SET status = 'accepted'
                WHERE challenge_id = %s
            """, (challenge_id,))
            conn.commit()
    
    except Exception as e:
        logger.error(f"Error accepting challenge: {e}")
        await query.edit_message_text(
            "❌ <b>Error</b>\n"
            "Failed to accept challenge.",
            parse_mode=ParseMode.HTML
        )
        return
    finally:
        if conn:
            return_db_connection(conn)
    
    # Create ranked match using group chat_id
    game_id = f"challenge_{challenge_id}"
    match_id = f"RM{random.randint(10000, 99999)}"
    
    games[game_id] = {
        'chat_id': chat_id,
        'creator': challenger_id,
        'joiner': target_id,
        'creator_name': challenger_name,
        'joiner_name': target_name,
        'match_id': match_id,
        'match_type': 'ranked',
        'is_ranked': True,
        'status': 'playing',
        'mode': 'Blitz',
        'max_overs': 3,
        'max_wickets': 3,
        'overs': 3,
        'wickets': 0,
        'balls': 0,
        'current_innings': 1,
        'innings': 1,
        'score': {'innings1': 0, 'innings2': 0},
        'this_over': [],
        'boundaries': 0,
        'sixes': 0,
        'first_innings_boundaries': 0,
        'first_innings_sixes': 0,
        'second_innings_boundaries': 0,
        'second_innings_sixes': 0,
        'over_scores': {},
        'dot_balls': 0,
        'toss_choice': None,
        'toss_result': None,
        'choosing_player': None,
        'bat_first': None,
        'batsman': None,
        'batsman_name': None,
        'bowler': None,
        'bowler_name': None,
        'batsman_choice': None,
        'bowler_choice': None,
        'batsman_ready': False,
        'player1_score': 0,
        'player2_score': 0,
        'player1_wickets': 0,
        'player2_wickets': 0,
        'player1_balls': 0,
        'player2_balls': 0,
        'target': None,
        'p1_rating': challenger_rating,
        'p2_rating': target_rating,
        'created_at': time.time(),
        'last_activity': time.time()
    }
    
    # Update message with toss in group
    game = games[game_id]
    game['choosing_player'] = challenger_id
    game['choosing_player_name'] = challenger_name
    game['chat_id'] = chat_id  # Store group chat_id
    
    keyboard = [
        [
            InlineKeyboardButton("ODD", callback_data=f"toss_{game_id}_odd"),
            InlineKeyboardButton("EVEN", callback_data=f"toss_{game_id}_even")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    toss_text = (
        f"🏆 <b>RANKED MATCH - {match_id}</b>\n"
        f"━━━━━━━━━━━━━━\n\n"
        f"<b>🎮 PLAYERS</b>\n"
        f"🔹 <a href='tg://user?id={challenger_id}'>{challenger_name}</a> ({challenger_rating})\n"
        f"🔸 <a href='tg://user?id={target_id}'>{target_name}</a> ({target_rating})\n\n"
        f"<b>🏏 FORMAT</b>\n"
        f"Mode: Blitz (3 overs, 3 wickets)\n"
        f"Type: Ranked (Rated Match)\n\n"
        f"<b>🎲 TOSS TIME</b>\n"
        f"<i><a href='tg://user?id={challenger_id}'>{challenger_name}</a>, choose ODD or EVEN!</i>"
    )
    
    # Update the challenge message with toss buttons in group
    try:
        await query.edit_message_text(
            text=toss_text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.error(f"Error updating message with toss: {e}")

async def handle_challenge_decline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle challenge decline"""
    query = update.callback_query
    await query.answer()
    
    challenge_id = query.data.replace("challenge_decline_", "")
    target_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    try:
        conn = get_db_connection()
        if not conn:
            await query.edit_message_text(
                "❌ <b>Database Error</b>\n"
                "Please try again later.",
                parse_mode=ParseMode.HTML
            )
            return
        
        with conn.cursor() as cur:
            # Get challenge details
            cur.execute("""
                SELECT challenger_id, target_id, challenger_name, target_name, status
                FROM pending_challenges
                WHERE challenge_id = %s
            """, (challenge_id,))
            
            result = cur.fetchone()
            
            if not result:
                await query.edit_message_text(
                    "❌ <b>Challenge Not Found</b>\n"
                    "This challenge has expired or been canceled.",
                    parse_mode=ParseMode.HTML
                )
                return
            
            challenger_id, db_target_id, challenger_name, target_name, status = result
            
            # Verify it's the right person declining
            if target_id != db_target_id:
                await query.answer("❌ This challenge is not for you!", show_alert=True)
                return
            
            # Check if already accepted/declined/expired
            if status != 'pending':
                await query.edit_message_text(
                    f"❌ <b>Challenge {status.title()}</b>\n"
                    f"This challenge is no longer available.",
                    parse_mode=ParseMode.HTML
                )
                return
            
            # Mark as declined
            cur.execute("""
                UPDATE pending_challenges SET status = 'declined'
                WHERE challenge_id = %s
            """, (challenge_id,))
            conn.commit()
    
    except Exception as e:
        logger.error(f"Error declining challenge: {e}")
        await query.edit_message_text(
            "❌ <b>Error</b>\n"
            "Failed to decline challenge.",
            parse_mode=ParseMode.HTML
        )
        return
    finally:
        if conn:
            return_db_connection(conn)
    
    # Update decline message in group
    await query.edit_message_text(
        f"❌ <b>Challenge Declined</b>\n"
        f"━━━━━━━━━━━━━━\n\n"
        f"<a href='tg://user?id={target_id}'>{target_name}</a> declined the challenge from <a href='tg://user?id={challenger_id}'>{challenger_name}</a>.",
        parse_mode=ParseMode.HTML
    )

async def challenge_timeout_task(challenge_id: str, challenger_id: int, target_id: int, chat_id: int, message_id: int, context):
    """Auto-decline challenge after 60 seconds"""
    await asyncio.sleep(60)
    
    try:
        conn = get_db_connection()
        if not conn:
            return
        
        with conn.cursor() as cur:
            # Check if challenge is still pending
            cur.execute("""
                SELECT status, challenger_name, target_name
                FROM pending_challenges
                WHERE challenge_id = %s
            """, (challenge_id,))
            
            result = cur.fetchone()
            
            if not result:
                return
            
            status, challenger_name, target_name = result
            
            if status and status.startswith('pending_'):
                # Mark as expired
                cur.execute("""
                    UPDATE pending_challenges SET status = 'expired'
                    WHERE challenge_id = %s
                """, (challenge_id,))
                conn.commit()
                
                # Update message in group
                try:
                    await context.bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=message_id,
                        text=(
                            f"⏱️ <b>Challenge Expired</b>\n"
                            f"━━━━━━━━━━━━━━\n\n"
                            f"<a href='tg://user?id={target_id}'>{target_name}</a> didn't respond to <a href='tg://user?id={challenger_id}'>{challenger_name}</a>'s challenge in time."
                        ),
                        parse_mode=ParseMode.HTML
                    )
                except Exception as e:
                    logger.error(f"Error updating challenge timeout message: {e}")
    
    except Exception as e:
        logger.error(f"Error in challenge timeout task: {e}")
    finally:
        if conn:
            return_db_connection(conn)

# ========================================
# END OF CAREER SYSTEM FUNCTIONS
# ========================================

# Add persistence for admins and groups
def load_persistent_data():
    """Load admins and groups from database on bot startup"""
    conn = None
    try:
        conn = get_db_connection()
        if not conn:
            return

        with conn.cursor() as cur:
            # Load admins
            cur.execute("SELECT admin_id FROM bot_admins WHERE is_active = TRUE")
            for row in cur.fetchall():
                BOT_ADMINS.add(str(row[0]))

            # Load groups
            cur.execute("SELECT group_id FROM authorized_groups WHERE is_active = TRUE")
            for row in cur.fetchall():
                AUTHORIZED_GROUPS.add(row[0])

    except Exception as e:
        logger.error(f"Error loading persistent data: {e}")
    finally:
        if conn:
            return_db_connection(conn)

async def reset_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reset a user's profile statistics"""
    if not check_admin(str(update.effective_user.id)):
        await update.message.reply_text("❌ Unauthorized")
        return
    
    user = update.effective_user
    await send_admin_log(
        f"CMD: /resetstats by {user.first_name} (@{user.username or 'no_username'}, ID: {user.id})",
        log_type="command",
        chat_context=get_chat_context(update)
    )
        
    if not context.args:
        await update.message.reply_text(
            "Usage: /resetstats <user_id>"
        )
        return
        
    user_id = context.args[0]
    
    try:
        conn = get_db_connection()
        if not conn:
            await update.message.reply_text("❌ Database connection error")
            return
            
        with conn.cursor() as cur:
            # Reset player stats
            cur.execute("""
                UPDATE player_stats 
                SET matches_played = 0,
                    matches_won = 0,
                    total_runs_scored = 0,
                    total_wickets_taken = 0,
                    highest_score = 0,
                    total_boundaries = 0,
                    total_sixes = 0,
                    fifties = 0,
                    hundreds = 0,
                    total_balls_faced = 0,
                    total_dot_balls = 0,
                    last_five_scores = '[]',
                    best_bowling = NULL
                WHERE user_id = %s
                RETURNING user_id
            """, (user_id,))
            
            result = cur.fetchone()
            
            # Also reset career stats
            cur.execute("""
                UPDATE career_stats
                SET rating = 1000,
                    rank_tier = 'Bronze',
                    matches_played = 0,
                    matches_won = 0,
                    matches_lost = 0,
                    win_streak = 0,
                    best_streak = 0
                WHERE user_id = %s
            """, (user_id,))
            
            if result:
                conn.commit()
                await update.message.reply_text(
                    f"✅ *STATS RESET*\n"
                    f"━━━━━━━━━━━━━━━━\n\n"
                    f"Profile and career stats reset for user {user_id}",
                    parse_mode=ParseMode.MARKDOWN_V2
                )
            else:
                await update.message.reply_text("❌ User not found in database")
                
    except Exception as e:
        logger.error(f"Error resetting stats: {e}")
        await update.message.reply_text("❌ Error resetting stats")
    finally:
            if conn:
                return_db_connection(conn)

# Add new function to update player stats
async def update_player_stats(user_id: str, **stats) -> bool:
    """Update player statistics"""
    try:
        conn = get_db_connection()
        if not conn:
            return False
            
        with conn.cursor() as cur:
            # Ensure user exists in users table first
            cur.execute("""
                INSERT INTO users (telegram_id, first_name, username)
                VALUES (%s, 'Player', 'player')
                ON CONFLICT (telegram_id) DO NOTHING
            """, (user_id,))
            
            # Get current highest score to compare
            cur.execute("""
                SELECT highest_score FROM player_stats WHERE user_id = %s
            """, (user_id,))
            result = cur.fetchone()
            current_highest = result[0] if result else 0
            
            # Update all stats in a single query
            new_highest = max(current_highest, stats.get('runs_scored', 0))
            
            cur.execute("""
                INSERT INTO player_stats 
                    (user_id, matches_played, matches_won, total_runs_scored, 
                     total_balls_faced, total_wickets_taken, total_boundaries,
                     total_sixes, dot_balls, highest_score) 
                VALUES 
                    (%s, 1, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE SET
                    matches_played = player_stats.matches_played + 1,
                    matches_won = player_stats.matches_won + %s,
                    total_runs_scored = player_stats.total_runs_scored + %s,
                    total_balls_faced = player_stats.total_balls_faced + %s,
                    total_wickets_taken = player_stats.total_wickets_taken + %s,
                    total_boundaries = player_stats.total_boundaries + %s,
                    total_sixes = player_stats.total_sixes + %s,
                    dot_balls = player_stats.dot_balls + %s,
                    highest_score = GREATEST(player_stats.highest_score, %s),
                    last_updated = CURRENT_TIMESTAMP
            """, (
                user_id, 
                int(stats.get('is_winner', 0)),
                stats.get('runs_scored', 0),
                stats.get('balls_faced', 0),
                stats.get('wickets', 0),
                stats.get('boundaries', 0),
                stats.get('sixes', 0),
                stats.get('dot_balls', 0),
                new_highest,
                int(stats.get('is_winner', 0)),
                stats.get('runs_scored', 0),
                stats.get('balls_faced', 0),
                stats.get('wickets', 0),
                stats.get('boundaries', 0),
                stats.get('sixes', 0),
                stats.get('dot_balls', 0),
                stats.get('runs_scored', 0)
            ))
            conn.commit()
            return True
            
    except Exception as e:
        logger.error(f"Error updating player stats: {e}")
        return False
    finally:
        if conn:
            return_db_connection(conn)

def default_stats() -> dict:
    """Return default stats dictionary with all required fields"""
    return {
        'matches_played': 0,
        'matches_won': 0,
        'total_runs': 0,
        'total_balls_faced': 0,
        'batting_avg': 0,
        'highest_score': 0,
        'boundaries': 0,
        'sixes': 0,
        'fifties': 0,
        'hundreds': 0,
        'wickets': 0,
        'bowling_avg': 0,
        'best_bowling': None,
        'strike_rate': 0,
        'dot_balls': 0,
        'last_five_scores': '[]'
    }

# Add new constants for team matches ---
class MatchType(Enum):
    PVP = "pvp"
    TEAM = "team"

class TeamMatchType(Enum):
    RANDOM = "random"
    NORMAL = "normal"

@dataclass
class TeamPlayer:
    user_id: str
    username: str
    batting: bool = False
    bowling: bool = False
    balls_bowled: int = 0
    runs_scored: int = 0
    wickets: int = 0

@dataclass
class Team:
    name: str
    captain_id: str
    players: List[TeamPlayer]
    current_bowler: Optional[TeamPlayer] = None
    current_batsman: Optional[TeamPlayer] = None
    next_bowler_queue: List[TeamPlayer] = None

class TeamMatch:
    def __init__(self):
        self.team1: Optional[Team] = None
        self.team2: Optional[Team] = None
        self.registered_players: List[TeamPlayer] = []
        self.match_type: TeamMatchType = None
        self.status: str = "registering"
        self.max_players: int = 11
        self.min_players: int = 2
        self.host_id: str = None
        self.current_innings: int = 1
        self.score: Dict[str, int] = {"innings1": 0, "innings2": 0}
        self.wickets: int = 0
        self.overs: int = 0
        self.balls: int = 0
        self.max_overs: int = 0
        self.max_wickets: int = 0

# Add to existing game constants
TEAM_MATCH_STATES = {
    'registering': '📝',
    'team_selection': '👥',
    'captain_selection': '👑',
    'team_naming': '✏️',
    'match_setup': '⚙️',
    'playing': '🏏',
    'completed': '🏆'
}

# Add team match messages
TEAM_MESSAGES = {
    'registration': (
        "*🏏 Team Match Registration*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "• Click below to join\n"
        "• Min Players: {min}\n"
        "• Max Players: {max}\n"
        "• Currently Registered: {count}\n\n"
        "*Registered Players:*\n{players}"
    ),
    'captain_selection': (
        "*👑 Captain Selection*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Random captains have been selected:\n\n"
        "*Team 1 Captain:* {cap1}\n"
        "*Team 2 Captain:* {cap2}\n\n"
        "Captains, please set your team names!"
    ),
    'team_naming': (
        "*✏️ Team Setup*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "*Captain:* {captain}\n"
        "Please enter your team name:"
    )
}

# Add to existing games dict to track team matches
team_matches: Dict[str, TeamMatch] = {}

# Add match type handler function
async def handle_match_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle match type selection (PvP or Team)"""
    query = update.callback_query
    await query.answer()
    
    try:
        # Extract match type and creator ID
        parts = query.data.split('_')
        match_type = parts[1]
        creator_id = parts[2] if len(parts) > 2 else None
        
        # Check if the person clicking is the creator
        current_user_id = str(query.from_user.id)
        if creator_id and current_user_id != creator_id:
            await query.answer(
                "❌ Only the game creator can configure the match!",
                show_alert=True
            )
            return
        
        if match_type == "team":
            # Team vs Team feature - Coming Soon
            await query.edit_message_text(
                escape_markdown_v2_custom(
                    "🚧 *TEAM VS TEAM*\n"
                    "━━━━━━━━━━━━━━━━━━━━\n\n"
                    "⚠️ *Coming Soon!*\n\n"
                    "This feature is currently under development.\n"
                    "We're working hard to bring you:\n\n"
                    "• 🎲 Random Team Matches\n"
                    "• 👥 Manual Team Setup\n"
                    "• 📊 Team Statistics\n"
                    "• 🏆 Team Leaderboards\n\n"
                    "Stay tuned for updates!"
                ),
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Back to Menu", callback_data=f"back_to_menu_{creator_id}")
                ]]),
                parse_mode=ParseMode.MARKDOWN_V2
            )
        else:  # pvp
            # Create new game with improved ID generation
            chat_id = query.message.chat_id
            game_id = f"{abs(chat_id)}_{int(time.time() * 1000) % 1000000}"
            while game_id in games:
                game_id = f"{abs(chat_id)}_{int(time.time() * 1000) % 1000000}_{random.randint(0, 99)}"
            
            creator_name = query.from_user.first_name
            
            games[game_id] = {
                'chat_id': query.message.chat_id,
                'creator': str(query.from_user.id),
                'creator_name': creator_name,
                'status': 'config'
            }
            
            # Show game mode selection - pass creator_id along
            keyboard = []
            for mode in GAME_MODES:
                keyboard.append([
                    InlineKeyboardButton(
                        f"{GAME_MODES[mode]['icon']} {GAME_MODES[mode]['title']}", 
                        callback_data=f"mode_{game_id}_{mode}_{creator_id}"
                    )
                ])
            
            # Build mode descriptions with proper escaping
            mode_descriptions = []
            for mode in GAME_MODES:
                mode_info = GAME_MODES[mode]
                # Don't double-escape if already escaped, just use the descriptions as-is
                desc_lines = "\n  ".join(mode_info['description'])
                title = mode_info['title']
                mode_descriptions.append(f"*{mode_info['icon']} {title}*\n  {desc_lines}")
            
            modes_text = "\n\n".join(mode_descriptions)
            
            await query.edit_message_text(
                escape_markdown_v2_custom(
                    f"🎮  *SELECT GAME MODE*\n"
                    f"══════════════════════\n\n"
                    f"{modes_text}\n\n"
                    f"👇 *Tap a mode to configure:*"
                ),
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN_V2
            )
            
    except Exception as e:
        logger.error(f"Error in handle_match_type: {e}")
        await handle_error(query)

async def handle_back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle back to menu button"""
    query = update.callback_query
    await query.answer()
    
    try:
        # Extract creator ID if present
        parts = query.data.split('_')
        creator_id = parts[-1] if len(parts) > 3 else None
        
        # If creator_id exists, pass it along in the buttons
        if creator_id:
            keyboard = [
                [InlineKeyboardButton("🏏 Player vs Player", callback_data=f"matchtype_pvp_{creator_id}")],
                [InlineKeyboardButton("👥 Team vs Team", callback_data=f"matchtype_team_{creator_id}")]
            ]
        else:
            keyboard = [
                [InlineKeyboardButton("🏏 Player vs Player", callback_data="matchtype_pvp")],
                [InlineKeyboardButton("👥 Team vs Team", callback_data="matchtype_team")]
            ]
        
        await query.edit_message_text(
            escape_markdown_v2_custom(
                "🏟️  *CRICKET SAGA ARENA*\n"
                "══════════════════════\n\n"
                "⚔️ *PLAYER VS PLAYER*\n"
                "Challenge a friend to a 1v1 duel.\n\n"
                "👥 *TEAM BATTLE*\n"
                "Squad play. Captains lead the charge.\n\n"
                "👇 *Choose match type:*"
            ),
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN_V2
        )
    except Exception as e:
        logger.error(f"Error in handle_back_to_menu: {e}")

# Update handle_team_type for better match creation
async def handle_team_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle team match type selection (Random or Normal)"""
    query = update.callback_query
    await query.answer()
    
    try:
        team_type = query.data.split('_')[1]  # Get match type
        
        # Create new team match
        match_id = str(random.randint(1000, 9999))
        match = TeamMatch()
        match.match_type = TeamMatchType(team_type)
        match.host_id = str(query.from_user.id)
        match.host_name = query.from_user.first_name
        team_matches[match_id] = match
        
        if team_type == "random":
            # Random team match setup
            keyboard = [
                [InlineKeyboardButton("🤝 Join Team", callback_data=f"teamjoin_{match_id}")],
                [InlineKeyboardButton("📊 Players List", callback_data=f"teamlist_{match_id}")],
                [InlineKeyboardButton("✅ Start Match", callback_data=f"teamstart_{match_id}")]
            ]
            
            await query.edit_message_text(
                escape_markdown_v2_custom(
                    "*🏏 RANDOM TEAM MATCH*\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    f"*Host:* {match.host_name}\n\n"
                    f"• Min Players: {match.min_players}\n"
                    f"• Max Players: {match.max_players}\n"
                    f"• Players: {len(match.registered_players)}/11\n\n"
                    "*Click to join the match!*"
                ),
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN_V2
            )
            
        else:  # normal
            # Manual team setup
            keyboard = [
                [InlineKeyboardButton("🎯 Create Team 1", callback_data=f"createteam_{match_id}_1")],
                [InlineKeyboardButton("🎯 Create Team 2", callback_data=f"createteam_{match_id}_2")],
                [InlineKeyboardButton("📊 View Teams", callback_data=f"viewteams_{match_id}")]
            ]
            
            await query.edit_message_text(
                escape_markdown_v2_custom(
                    "*👥 MANUAL TEAM SETUP*\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    "1. Create both teams\n"
                    "2. Add players (5-11 per team)\n"
                    "3. Start the match\n\n"
                    "*Current Status:*\n"
                    "• Team 1: Not Created\n"
                    "• Team 2: Not Created"
                ),
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN_V2
            )
            
    except Exception as e:
        logger.error(f"Error in handle_team_type: {e}")
        await handle_error(query)


async def handle_team_name_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle team name input from captains"""
    if 'awaiting_team_name' not in context.user_data:
        return

    try:
        data = context.user_data['awaiting_team_name']
        match_id = data['match_id']
        team_num = data['team']
        match = team_matches.get(match_id)
        
        if not match:
            await update.message.reply_text(
                escape_markdown_v2_custom("❌ Match not found!"),
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return
            
        # Set team name
        team_name = update.message.text.strip()[:20]  # Limit name length
        if team_num == 1:
            match.team1.name = team_name
        else:
            match.team2.name = team_name
            
        # Check if both teams have names
        if match.team1.name and match.team2.name:
            await update.message.reply_text(
                escape_markdown_v2_custom(
                    "*👥 TEAM SETUP COMPLETE*\n"
                    "━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"*{match.team1.name}* vs *{match.team2.name}*\n\n"
                    "Next: Select overs and wickets!"
                ),
                parse_mode=ParseMode.MARKDOWN_V2,
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("⚙️ Match Setup", callback_data=f"teamsetup_{match_id}")
                ]])
            )
        else:
            await update.message.reply_text(
                escape_markdown_v2_custom(
                    "✅ Team name set!\n"
                    "Waiting for other captain..."
                ),
                parse_mode=ParseMode.MARKDOWN_V2
            )
            
        del context.user_data['awaiting_team_name']

    except Exception as e:
        logger.error(f"Error in handle_team_name_input: {e}")
        await update.message.reply_text(
            escape_markdown_v2_custom("❌ Error setting team name!"),
            parse_mode=ParseMode.MARKDOWN_V2
        )

async def handle_team_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle player joining team match"""
    query = update.callback_query
    await query.answer()
    
    try:
        _, match_id = query.data.split('_')
        match = team_matches.get(match_id)
        
        if not match:
            await query.edit_message_text(
                escape_markdown_v2_custom("❌ Match not found!"),
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return
            
        # Check if player already registered
        if any(p.user_id == str(query.from_user.id) for p in match.registered_players):
            await query.answer("You're already registered!", show_alert=True)
            return
            
        # Add new player
        new_player = TeamPlayer(
            user_id=str(query.from_user.id),
            username=query.from_user.first_name
        )
        match.registered_players.append(new_player)
        
        # Update registration message
        players_list = "\n".join([f"• {p.username}" for p in match.registered_players])
        message = TEAM_MESSAGES['registration'].format(
            min=match.min_players,
            max=match.max_players,
            count=len(match.registered_players),
            players=players_list
        )
        
        keyboard = [
            [InlineKeyboardButton("🤝 Join Team", callback_data=f"teamjoin_{match_id}")],
            [InlineKeyboardButton("📊 Players List", callback_data=f"teamlist_{match_id}")],
            [InlineKeyboardButton("✅ Start Match", callback_data=f"teamstart_{match_id}")]
        ]
        
        await query.edit_message_text(
            escape_markdown_v2_custom(message),
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN_V2
        )
        
    except Exception as e:
        logger.error(f"Error in handle_team_join: {e}")
        await handle_error(query)

async def handle_team_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start team match and assign teams"""
    query = update.callback_query
    await query.answer()
    
    try:
        _, match_id = query.data.split('_')
        match = team_matches.get(match_id)
        
        if len(match.registered_players) < match.min_players:
            await query.answer(
                f"Need at least {match.min_players} players to start!",
                show_alert=True
            )
            return
            
        # For random match type, select captains and assign teams
        if match.match_type == TeamMatchType.RANDOM:
            # Randomly select captains
            players = match.registered_players.copy()
            random.shuffle(players)
            cap1, cap2 = players[:2]
            
            # Create teams
            match.team1 = Team(name="", captain_id=cap1.user_id, players=[])
            match.team2 = Team(name="", captain_id=cap2.user_id, players=[])
            
            # Random team assignment
            remaining_players = players[2:]
            random.shuffle(remaining_players)
            split_point = len(remaining_players) // 2
            
            match.team1.players = [cap1] + remaining_players[:split_point]
            match.team2.players = [cap2] + remaining_players[split_point:]
            
            # Show captain selection result
            message = TEAM_MESSAGES['captain_selection'].format(
                cap1=cap1.username,
                cap2=cap2.username
            )
            
            keyboard = [
                [InlineKeyboardButton("⚔️ Set Team Names", callback_data=f"teamname_{match_id}")]
            ]
            
            await query.edit_message_text(
                escape_markdown_v2_custom(message),
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN_V2
            )
            
    except Exception as e:
        logger.error(f"Error in handle_team_start: {e}")
        await handle_error(query)

async def handle_team_captain(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle team captain selection"""
    query = update.callback_query
    await query.answer()
    
    try:
        _, match_id, team_num = query.data.split('_')
        match = team_matches.get(match_id)
        team_num = int(team_num)
        
        team = match.team1 if team_num == 1 else match.team2
        
        # Only allow selection if user is in the team
        if str(query.from_user.id) not in [p.user_id for p in team.players]:
            await query.answer("You must be in the team to become captain!", show_alert=True)
            return
            
        # Set new captain
        team.captain_id = str(query.from_user.id)
        
        await query.edit_message_text(
            escape_markdown_v2_custom(
                f"*👑 New Captain Selected*\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"*Team {team_num}*\n"
                f"Captain: {query.from_user.first_name}"
            ),
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("📋 View Teams", callback_data=f"viewteams_{match_id}")
            ]])
        )
        
    except Exception as e:
        logger.error(f"Error in handle_team_captain: {e}")
        await handle_error(query)

async def handle_team_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle team naming process"""
    query = update.callback_query
    await query.answer()
    
    try:
        _, match_id = query.data.split('_')
        match = team_matches.get(match_id)
        
        # Show name input prompt for first unnamed team
        team_num = 1 if not match.team1.name else 2
        captain = match.team1.captain_id if team_num == 1 else match.team2.captain_id
        
        if str(query.from_user.id) != captain:
            await query.answer("Only the captain can set team name!", show_alert=True)
            return
            
        # Store that we're awaiting team name
        context.user_data['awaiting_team_name'] = {
            'match_id': match_id,
            'team': team_num
        }
        
        message = TEAM_MESSAGES['team_naming'].format(
            captain=query.from_user.first_name
        )
        
        await query.edit_message_text(
            escape_markdown_v2_custom(message),
            parse_mode=ParseMode.MARKDOWN_V2
        )
        
    except Exception as e:
        logger.error(f"Error in handle_team_name: {e}")
        await handle_error(query)

async def handle_team_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show list of registered players"""
    query = update.callback_query
    await query.answer()
    
    try:
        _, match_id = query.data.split('_')
        match = team_matches.get(match_id)
        
        players_list = "\n".join([
            f"• {p.username}" for p in match.registered_players
        ])
        
        keyboard = [
            [InlineKeyboardButton("◀️ Back", callback_data=f"teamback_{match_id}")]
        ]
        
        await query.edit_message_text(
            escape_markdown_v2_custom(
                f"*📋 Registered Players ({len(match.registered_players)})*\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"{players_list}"
            ),
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN_V2
        )
        
    except Exception as e:
        logger.error(f"Error in handle_team_list: {e}")
        await handle_error(query)

async def handle_create_team(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle manual team creation"""
    query = update.callback_query
    await query.answer()
    
    try:
        _, match_id, team_num = query.data.split('_')
        match = team_matches.get(match_id)
        team_num = int(team_num)
        
        if (team_num == 1 and match.team1) or (team_num == 2 and match.team2):
            await query.answer("Team already created!", show_alert=True)
            return
            
        # Create empty team with captain
        new_team = Team(
            name="",
            captain_id=str(query.from_user.id),
            players=[]
        )
        
        if team_num == 1:
            match.team1 = new_team
        else:
            match.team2 = new_team
            
        # Show team name input prompt
        message = TEAM_MESSAGES['team_naming'].format(
            captain=query.from_user.first_name
        )
        
        context.user_data['awaiting_team_name'] = {
            'match_id': match_id,
            'team': team_num
        }
        
        await query.edit_message_text(
            escape_markdown_v2_custom(message),
            parse_mode=ParseMode.MARKDOWN_V2
        )
        
    except Exception as e:
        logger.error(f"Error in handle_create_team: {e}")
        await handle_error(query)

async def handle_view_teams(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show current teams"""
    query = update.callback_query
    await query.answer()
    
    try:
        _, match_id = query.data.split('_')
        match = team_matches.get(match_id)
        
        team1_info = "Not created" if not match.team1 else (
            f"*Captain:* {match.team1.name}\n"
            f"*Players:* {len(match.team1.players)}/11"
        )
        
        team2_info = "Not created" if not match.team2 else (
            f"*Captain:* {match.team2.name}\n"
            f"*Players:* {len(match.team2.players)}/11"
        )
        
        keyboard = [
            [InlineKeyboardButton("🎯 Create Team 1", callback_data=f"createteam_{match_id}_1")],
            [InlineKeyboardButton("🎯 Create Team 2", callback_data=f"createteam_{match_id}_2")],
            [InlineKeyboardButton("⚔️ Start Match", callback_data=f"teamstart_{match_id}")]
        ]
        
        await query.edit_message_text(
            escape_markdown_v2_custom(
                "*👥 TEAM STATUS*\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                f"*TEAM 1*\n{team1_info}\n\n"
                f"*TEAM 2*\n{team2_info}"
            ),
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN_V2
        )
        
    except Exception as e:
        logger.error(f"Error in handle_view_teams: {e}")
        await handle_error(query)

async def handle_team_setup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle match setup after team creation"""
    query = update.callback_query
    await query.answer()
    
    try:
        _, match_id = query.data.split('_')
        match = team_matches.get(match_id)
        
        keyboard = [
            [
                InlineKeyboardButton("5 🎯", callback_data=f"teamovers_{match_id}_5"),
                InlineKeyboardButton("10 🎯", callback_data=f"teamovers_{match_id}_10")
            ],
            [
                InlineKeyboardButton("15 🎯", callback_data=f"teamovers_{match_id}_15"),
                InlineKeyboardButton("20 🎯", callback_data=f"teamovers_{match_id}_20")
            ]
        ]
        
        await query.edit_message_text(
            escape_markdown_v2_custom(
                "*⚙️ MATCH SETUP*\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                f"*{match.team1.name}* vs *{match.team2.name}*\n\n"
                "Select number of overs:"
            ),
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN_V2
        )
        
    except Exception as e:
        logger.error(f"Error in handle_team_setup: {e}")
        await handle_error(query)

async def handle_next_bowler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle next bowler selection"""
    query = update.callback_query
    await query.answer()
    
    try:
        _, match_id, player_id = query.data.split('_')
        match = team_matches.get(match_id)
        
        # Get bowling team
        bowling_team = match.team2 if match.current_innings == 1 else match.team1
        
        # Find player
        bowler = next((p for p in bowling_team.players if p.user_id == player_id), None)
        if not bowler:
            await query.answer("Player not found!", show_alert=True)
            return
            
        # Set as current bowler
        bowling_team.current_bowler = bowler
        
        # Show batting view
        keyboard = get_batting_keyboard(match_id)  # Reuse existing keyboard
        
        await query.edit_message_text(
            escape_markdown_v2_custom(
                f"*🎯 New Bowler: {bowler.username}*\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                f"*Score:* {match.score[f'innings{match.current_innings}']}/{match.wickets}\n"
                f"*Overs:* {match.overs}.{match.balls%6}"
            ),
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN_V2
        )
        
    except Exception as e:
        logger.error(f"Error in handle_next_bowler: {e}")
        await handle_error(query)

async def handle_next_batter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle next batter selection"""
    query = update.callback_query
    await query.answer()
    
    try:
        _, match_id, player_id = query.data.split('_')
        match = team_matches.get(match_id)
        
        # Get batting team
        batting_team = match.team1 if match.current_innings == 1 else match.team2
        
        # Find player
        batter = next((p for p in batting_team.players if p.user_id == player_id), None)
        if not batter:
            await query.answer("Player not found!", show_alert=True)
            return
            
        # Set as current batsman
        batting_team.current_batsman = batter
        
        # Show batting view
        keyboard = get_batting_keyboard(match_id)  # Reuse existing keyboard
        
        await query.edit_message_text(
            escape_markdown_v2_custom(
                f"*🏏 New Batter: {batter.username}*\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                f"*Score:* {match.score[f'innings{match.current_innings}']}/{match.wickets}\n"
                f"*Overs:* {match.overs}.{match.balls%6}"
            ),
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN_V2
        )
        
    except Exception as e:
        logger.error(f"Error in handle_next_batter: {e}")
        await handle_error(query)

# Add to main() where $SELECTION_PLACEHOLDER$ is:
def main():
    # Add this at the start of main()
    load_dotenv()  # Load environment variables
    
    if not BOT_TOKEN:
        logger.error("Bot token not found!")
        return

    # Initialize database
    if not init_database_connection():
        logger.warning("Running in file storage mode due to database initialization failure")
        global USE_FILE_STORAGE
        USE_FILE_STORAGE = True
    
    # Initialize application with proxy settings removed
    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .connection_pool_size(8)  # Adjust pool size as needed
        .connect_timeout(30.0)    # Increase timeout if needed
        .read_timeout(30.0)
        .write_timeout(30.0)
        .build()
    )

    # Load persistent data  
    load_persistent_data()
    
    # ===== AUTO-SAVE GROUPS MIDDLEWARE =====
    # This runs before every update to auto-save groups
    async def group_tracker_middleware(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Middleware to auto-save groups before processing commands"""
        await auto_save_group(update, context)
    
    # Add as a pre-processor for all updates
    application.add_handler(MessageHandler(filters.ALL, group_tracker_middleware), group=-1)

    # ===== GAME HANDLERS =====
    application.add_handler(CommandHandler("gameon", gameon))
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("save", save_match))
    application.add_handler(CommandHandler("scorecard", view_scorecards))
    application.add_handler(CommandHandler("profile", profile))
    application.add_handler(CommandHandler("career", career))  # Career/ranking system
    application.add_handler(CommandHandler("leaderboard", leaderboard))  # Phase 4: Leaderboard
    application.add_handler(CommandHandler("recent", recent_matches))  # Recent match history
    application.add_handler(CommandHandler("ranks", ranks))  # Phase 4: Rank info
    application.add_handler(CommandHandler("rankedinfo", rankedinfo))  # Ranked system guide
    application.add_handler(CommandHandler("ranked", ranked))  # Phase 2: Ranked matchmaking
    application.add_handler(CommandHandler("cancel_queue", cancel_queue))  # Phase 2: Cancel queue
    application.add_handler(CommandHandler("challenge", challenge))  # Phase 3: Challenge system
    
    # ===== CALLBACK QUERY HANDLERS =====
    # Game flow callbacks
    application.add_handler(CallbackQueryHandler(handle_mode, pattern="^mode_"))
    application.add_handler(CallbackQueryHandler(handle_wickets, pattern="^wickets_"))
    application.add_handler(CallbackQueryHandler(handle_overs, pattern="^overs_"))
    application.add_handler(CallbackQueryHandler(handle_custom, pattern="^custom_"))
    application.add_handler(CallbackQueryHandler(handle_join, pattern="^join_"))
    application.add_handler(CallbackQueryHandler(handle_toss, pattern="^toss_"))
    application.add_handler(CallbackQueryHandler(handle_choice, pattern="^choice_"))
    application.add_handler(CallbackQueryHandler(handle_bat, pattern="^bat_"))
    application.add_handler(CallbackQueryHandler(handle_bowl, pattern="^bowl_"))
    
    # Phase 3: Challenge callbacks
    application.add_handler(CallbackQueryHandler(handle_challenge_accept, pattern="^challenge_accept_"))
    application.add_handler(CallbackQueryHandler(handle_challenge_decline, pattern="^challenge_decline_"))
    
    # Scorecard callbacks
    application.add_handler(CallbackQueryHandler(view_single_scorecard, pattern="^view_"))
    application.add_handler(CallbackQueryHandler(delete_match, pattern="^delete_"))
    application.add_handler(CallbackQueryHandler(back_to_list, pattern="^list_matches"))
    application.add_handler(CallbackQueryHandler(handle_pagination, pattern="^page\\_"))
    
    # Rankedinfo pagination callback
    application.add_handler(CallbackQueryHandler(handle_rankedinfo_pagination, pattern="^rankedinfo_page_"))
    
    # Subscription verification callback
    application.add_handler(CallbackQueryHandler(verify_subscription, pattern="^verify_subscription$"))
    
    # Team match callbacks
    application.add_handler(CallbackQueryHandler(handle_match_type, pattern="^matchtype_"))
    application.add_handler(CallbackQueryHandler(handle_back_to_menu, pattern="^back_to_menu$"))
    application.add_handler(CallbackQueryHandler(handle_team_type, pattern="^teamtype_"))
    application.add_handler(CallbackQueryHandler(handle_team_join, pattern="^teamjoin_"))
    application.add_handler(CallbackQueryHandler(handle_team_start, pattern="^teamstart_"))
    
    # Error handling callbacks
    application.add_handler(CallbackQueryHandler(handle_error, pattern="^retry_"))
    application.add_handler(CallbackQueryHandler(handle_retry, pattern="^retry_"))
    application.add_handler(CallbackQueryHandler(handle_input, pattern="^manual_"))
    
    # ===== MESSAGE HANDLERS =====
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_input))
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, 
        handle_team_name_input
    ))
    
    # ===== GROUP TRACKING =====
    # Track when bot is added/removed from groups
    from telegram.ext import ChatMemberHandler
    application.add_handler(ChatMemberHandler(track_group_membership, ChatMemberHandler.MY_CHAT_MEMBER))
    
    # ===== ADMIN COMMANDS =====
    application.add_handler(CommandHandler("addadmin", add_admin))
    application.add_handler(CommandHandler("removeadmin", remove_admin))
    application.add_handler(CommandHandler("listadmins", list_admins))
    application.add_handler(CommandHandler("blacklist", blacklist_user))
    application.add_handler(CommandHandler("unban", unban_user))
    application.add_handler(CommandHandler("broadcast", broadcast_message))
    application.add_handler(CommandHandler("stopgames", stop_games))
    application.add_handler(CommandHandler("forceremove", force_remove_player))
    application.add_handler(CommandHandler("resetratings", reset_all_ratings))
    application.add_handler(CommandHandler("setrating", set_player_rating))
    application.add_handler(CommandHandler("maintenance", toggle_maintenance))
    application.add_handler(CommandHandler("botstats", botstats))
    application.add_handler(CommandHandler("resetstats", reset_stats))
    application.add_handler(CommandHandler("testdb", test_db_connection))
    
    # User & group management commands
    application.add_handler(CommandHandler("listusers", listusers))
    application.add_handler(CommandHandler("listgroups", listgroups))
    application.add_handler(CommandHandler("scangroups", scangroups))
    application.add_handler(CommandHandler("userstats", userstats))
    
    # Anti-cheat admin commands
    application.add_handler(CommandHandler("flaggedmatches", flaggedmatches))
    application.add_handler(CommandHandler("reviewmatch", reviewmatch))
    application.add_handler(CommandHandler("clearflag", clearflag))
    application.add_handler(CommandHandler("suspendrating", suspendrating))
    application.add_handler(CommandHandler("unsuspendrating", unsuspendrating))
    
    # Additional team match callback handlers
    application.add_handler(CallbackQueryHandler(handle_team_list, pattern="^teamlist_"))
    application.add_handler(CallbackQueryHandler(handle_create_team, pattern="^createteam_"))
    application.add_handler(CallbackQueryHandler(handle_view_teams, pattern="^viewteams_"))
    application.add_handler(CallbackQueryHandler(handle_team_name, pattern="^teamname_"))
    application.add_handler(CallbackQueryHandler(handle_team_setup, pattern="^teamsetup_"))
    application.add_handler(CallbackQueryHandler(handle_team_captain, pattern="^teamcap_"))
    application.add_handler(CallbackQueryHandler(handle_next_bowler, pattern="^nextbowl_"))
    application.add_handler(CallbackQueryHandler(handle_next_batter, pattern="^nextbat_"))

    # Global error handler
    async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Log all errors and send to admin log"""
        try:
            # Log to console
            logger.error(f"Exception while handling update: {context.error}", exc_info=context.error)
            
            # Get chat context if update is available
            chat_context = None
            if update and hasattr(update, 'effective_chat'):
                chat_context = get_chat_context(update)
            
            # Format error message for admin
            error_msg = f"ERROR: {type(context.error).__name__}: {str(context.error)[:200]}"
            if update and hasattr(update, 'effective_user'):
                user = update.effective_user
                error_msg += f"\nUser: {user.first_name} (@{user.username or 'none'}, ID: {user.id})"
            
            # Send to admin log
            await send_admin_log(error_msg, log_type="error", chat_context=chat_context)
        except Exception as e:
            logger.error(f"Error in error handler: {e}")
    
    # Add error handler
    application.add_error_handler(error_handler)

    # Define post_init callback to start background tasks
    async def post_init(application):
        """Called after the event loop starts"""
        # Delete any existing webhook to avoid conflicts with polling
        await application.bot.delete_webhook(drop_pending_updates=True)
        logger.info("✅ Webhook deleted successfully")
        
        # Start background cleanup task
        asyncio.create_task(cleanup_old_games())
        logger.info("🧹 Background cleanup task started")
        
        # Start connection health monitoring
        asyncio.create_task(check_connection_health())
        logger.info("❤️ Connection health monitoring started")
        
        # Start web server if on Render
        PORT = os.environ.get("PORT")
        if PORT:
            from web import web_server, keep_alive
            from aiohttp import web as aio_web
            
            logger.info("🌐 Starting web server for Render.com deployment...")
            
            # Start keep-alive task
            asyncio.create_task(keep_alive())
            
            # Run web server in background
            app = web_server()
            runner = aio_web.AppRunner(app)
            await runner.setup()
            site = aio_web.TCPSite(runner, '0.0.0.0', int(PORT))
            await site.start()
            logger.info(f"✅ Web server started on port {PORT}")
            logger.info("✅ Keep-alive system activated")
    
    application.post_init = post_init
    
    # Start the bot
    logger.info("=" * 50)
    logger.info("🏏 Cricket Bot Started Successfully!")
    logger.info(f"📊 Registered {len(REGISTERED_USERS)} users from database")
    logger.info(f"🎮 Bot is ready to accept commands")
    logger.info(f"🔧 Total handlers registered: {len(application.handlers[0])}")
    logger.info("=" * 50)
    
    try:
        # Drop pending updates to avoid processing old commands
        application.run_polling(drop_pending_updates=True)
    except KeyboardInterrupt:
        logger.info("\n⚠️ Bot shutdown requested...")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
    finally:
        # Defensive cleanup - close all database connections
        logger.info("🧹 Cleaning up resources...")
        
        # Close DatabaseHandler pool
        if db:
            try:
                db.close()
                logger.info("✅ DatabaseHandler closed")
            except Exception as e:
                logger.error(f"⚠️ Error closing DatabaseHandler: {e}")
        
        # Close global connection pool
        if db_pool:
            try:
                db_pool.closeall()
                logger.info("✅ Global DB pool closed")
            except Exception as e:
                logger.error(f"⚠️ Error closing DB pool: {e}")
        
        logger.info("👋 Bot shutdown complete")

if __name__ == "__main__":
    main()

