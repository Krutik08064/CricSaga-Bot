# 📋 COMPLETE LOGGING SYSTEM IMPLEMENTATION GUIDE
## For Any Telegram Bot (Arena Of Champions / Others)

---

## 🎯 OVERVIEW

This logging system will send all admin command usage, errors, and important events to a centralized admin log chat using a **separate logging bot**. Both CricSaga Bot and Arena Of Champions bot can log to the **same admin chat**.

---

## ✅ STEP 1: CREATE LOGGING BOT

1. Go to [@BotFather](https://t.me/BotFather)
2. Send `/newbot`
3. Name it: **"Your Bot Logs"** (e.g., "Arena Logs Bot")
4. Username: **"your_bot_logs_bot"**
5. **Save the token** you receive

---

## ✅ STEP 2: GET YOUR ADMIN CHAT ID

**Method 1: Using @userinfobot**
1. Start a chat with [@userinfobot](https://t.me/userinfobot)
2. Your chat ID will be displayed
3. Note it down (e.g., `123456789`)

**Method 2: Using API**
1. Start a chat with your logging bot
2. Send any message to it
3. Visit: `https://api.telegram.org/bot<YOUR_LOG_BOT_TOKEN>/getUpdates`
4. Find `"chat":{"id":123456789}` in the response

---

## ✅ STEP 3: ADD ENVIRONMENT VARIABLES

### For Render.com:
1. Go to your service → Environment
2. Add these variables:

```
ADMIN_LOG_BOT_TOKEN = <your_logging_bot_token>
ADMIN_LOG_CHAT_ID = <your_admin_chat_id>
```

### For Heroku:
```bash
heroku config:set ADMIN_LOG_BOT_TOKEN=your_token_here
heroku config:set ADMIN_LOG_CHAT_ID=your_chat_id_here
```

### For Local (.env file):
```env
ADMIN_LOG_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
ADMIN_LOG_CHAT_ID=123456789
```

---

## ✅ STEP 4: ADD CODE TO YOUR BOT

### 4.1 Import Required Modules (At the very top of your bot file)

```python
import os
from datetime import datetime
from telegram import Update, Bot
from telegram.ext import ContextTypes
from telegram.constants import ChatType
```

---

### 4.2 Add Global Configuration (After imports, before any functions)

```python
# ================================
# ADMIN LOGGING CONFIGURATION
# ================================
ADMIN_LOG_BOT_TOKEN = os.getenv('ADMIN_LOG_BOT_TOKEN', '')
ADMIN_LOG_CHAT_ID = os.getenv('ADMIN_LOG_CHAT_ID', '')
```

---

### 4.3 Add Helper Functions (Add these two functions anywhere before your command handlers)

```python
# ================================
# ADMIN LOGGING FUNCTIONS
# ================================

async def send_admin_log(message: str, log_type: str = "info", chat_context: str = "Unknown"):
    """
    Send log message to admin log chat using separate logging bot.
    
    Args:
        message: The log message to send
        log_type: Type of log (info, command, error, match, db_error, success, warning)
        chat_context: Where the action occurred (DM or Group name with ID)
    
    Usage:
        await send_admin_log("User banned", log_type="success", chat_context="DM")
        await send_admin_log("CMD: /ban by Admin", log_type="command", chat_context="GC: Main Chat")
    """
    # Skip if logging is not configured
    if not ADMIN_LOG_BOT_TOKEN or not ADMIN_LOG_CHAT_ID:
        return
    
    try:
        # Emoji mapping for different log types
        emoji_map = {
            "info": "ℹ️",
            "command": "⚡",
            "error": "❌",
            "match": "🏏",
            "game": "🎮",
            "db_error": "🔴",
            "success": "✅",
            "warning": "⚠️",
            "user": "👤",
            "admin": "👑"
        }
        
        emoji = emoji_map.get(log_type, "📝")
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Format the log message
        log_message = (
            f"{emoji} <b>{log_type.upper()}</b>\n"
            f"⏰ {timestamp}\n"
            f"📍 Context: {chat_context}\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"{message}"
        )
        
        # Create separate bot instance for logging
        log_bot = Bot(token=ADMIN_LOG_BOT_TOKEN)
        
        # Send to admin log chat
        await log_bot.send_message(
            chat_id=ADMIN_LOG_CHAT_ID,
            text=log_message,
            parse_mode='HTML'
        )
        
    except Exception as e:
        # Silent fail - don't break main bot if logging fails
        print(f"Admin log error: {e}")


def get_chat_context(update: Update) -> str:
    """
    Get formatted chat context showing where a command was used.
    
    Args:
        update: The Telegram update object
    
    Returns:
        Formatted string like "DM" or "GC: GroupName (ID: -1001234567890)"
    
    Usage:
        chat_ctx = get_chat_context(update)
        await send_admin_log("Command used", chat_context=chat_ctx)
    """
    try:
        if update.effective_chat.type == ChatType.PRIVATE:
            return "DM"
        else:
            chat_title = update.effective_chat.title or "Unknown Group"
            chat_id = update.effective_chat.id
            return f"GC: {chat_title} (ID: {chat_id})"
    except Exception:
        return "Unknown"
```

---

## ✅ STEP 5: ADD LOGGING TO YOUR COMMANDS

### 5.1 Template for ADMIN Commands

```python
async def your_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Your admin command description"""
    
    # 1. Check admin authorization (your existing check)
    if not is_admin(update.effective_user.id):  # Replace with your admin check function
        await update.message.reply_text("❌ Unauthorized")
        return
    
    # 2. ADD LOGGING HERE ⬇️
    user = update.effective_user
    await send_admin_log(
        f"CMD: /yourcommand by {user.first_name} (@{user.username or 'no_username'}, ID: {user.id})",
        log_type="command",
        chat_context=get_chat_context(update)
    )
    # END LOGGING ⬆️
    
    # 3. Your existing command logic
    try:
        # Your command code here
        result = do_something()
        
        # Optional: Log success
        await send_admin_log(
            f"✅ Command completed successfully by {user.first_name}",
            log_type="success",
            chat_context=get_chat_context(update)
        )
        
        await update.message.reply_text("✅ Done!")
        
    except Exception as e:
        # Log errors
        await send_admin_log(
            f"❌ Error in /yourcommand: {str(e)}\n"
            f"User: {user.first_name} (ID: {user.id})",
            log_type="error",
            chat_context=get_chat_context(update)
        )
        await update.message.reply_text("❌ Error occurred")
```

---

### 5.2 Template for USER Commands (Optional but Recommended)

```python
async def your_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Regular user command"""
    user = update.effective_user
    
    # ADD LOGGING HERE ⬇️
    await send_admin_log(
        f"CMD: /yourcommand by {user.first_name} (@{user.username or 'no_username'}, ID: {user.id})",
        log_type="command",
        chat_context=get_chat_context(update)
    )
    # END LOGGING ⬆️
    
    # Your command logic here
    try:
        # Your code
        await update.message.reply_text("Done!")
    except Exception as e:
        await send_admin_log(
            f"Error in /yourcommand: {str(e)}",
            log_type="error",
            chat_context=get_chat_context(update)
        )
```

---

### 5.3 List of Commands to Add Logging To

**MUST ADD (Admin Commands):**
- All commands that only admins can use
- Commands that modify bot settings
- Commands that affect other users (ban, unban, etc.)
- Commands that access sensitive data

**RECOMMENDED (User Commands):**
- `/start` - Track new users
- `/help` - Track help requests
- Main feature commands (game start, profile, etc.)
- Payment/transaction commands

**Examples by Bot Type:**

**Cricket/Gaming Bot:**
- `/broadcast`, `/addadmin`, `/removeadmin`
- `/ban`, `/unban`, `/blacklist`
- `/stopgames`, `/maintenance`, `/resetstats`
- `/start`, `/play`, `/profile`, `/leaderboard`

**Quiz/Trivia Bot:**
- `/broadcast`, `/addadmin`, `/removeadmin`
- `/addquestion`, `/deletequestion`
- `/start`, `/quiz`, `/leaderboard`, `/stats`

**General Purpose Bot:**
- `/broadcast`, `/addadmin`, `/settings`
- `/ban`, `/unban`, `/warn`
- `/start`, `/help`, Your main features

---

## ✅ STEP 6: EXAMPLES BY SCENARIO

### Example 1: Ban Command

```python
async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ban a user from using the bot"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Unauthorized")
        return
    
    user = update.effective_user
    await send_admin_log(
        f"CMD: /ban by {user.first_name} (@{user.username or 'no_username'}, ID: {user.id})",
        log_type="command",
        chat_context=get_chat_context(update)
    )
    
    if not context.args:
        await update.message.reply_text("Usage: /ban <user_id>")
        return
    
    target_user_id = context.args[0]
    
    try:
        # Ban the user (your logic)
        ban_user_from_db(target_user_id)
        
        # Log the action
        await send_admin_log(
            f"✅ User banned\n"
            f"Target: {target_user_id}\n"
            f"By: {user.first_name} (ID: {user.id})",
            log_type="success",
            chat_context=get_chat_context(update)
        )
        
        await update.message.reply_text(f"✅ User {target_user_id} banned")
        
    except Exception as e:
        await send_admin_log(
            f"❌ Failed to ban user {target_user_id}\n"
            f"Error: {str(e)}\n"
            f"By: {user.first_name} (ID: {user.id})",
            log_type="error",
            chat_context=get_chat_context(update)
        )
        await update.message.reply_text("❌ Failed to ban user")
```

---

### Example 2: Broadcast Command

```python
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Broadcast message to all users"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Unauthorized")
        return
    
    user = update.effective_user
    await send_admin_log(
        f"CMD: /broadcast by {user.first_name} (@{user.username or 'no_username'}, ID: {user.id})",
        log_type="command",
        chat_context=get_chat_context(update)
    )
    
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Reply to a message to broadcast it")
        return
    
    message_to_broadcast = update.message.reply_to_message.text
    users = get_all_users()  # Your function to get users
    
    success_count = 0
    fail_count = 0
    
    for user_id in users:
        try:
            await context.bot.send_message(user_id, message_to_broadcast)
            success_count += 1
        except:
            fail_count += 1
    
    # Log the broadcast result
    await send_admin_log(
        f"📢 Broadcast completed\n"
        f"✅ Success: {success_count}\n"
        f"❌ Failed: {fail_count}\n"
        f"By: {user.first_name} (ID: {user.id})",
        log_type="success",
        chat_context=get_chat_context(update)
    )
    
    await update.message.reply_text(
        f"✅ Broadcast sent to {success_count} users\n"
        f"❌ Failed: {fail_count}"
    )
```

---

### Example 3: Game/Match Completion

```python
async def game_complete(game_id, winner_id, loser_id, score, update: Update):
    """Log when a game completes"""
    
    winner_name = get_user_name(winner_id)  # Your function
    loser_name = get_user_name(loser_id)    # Your function
    
    await send_admin_log(
        f"🎮 Game #{game_id} Complete\n"
        f"🏆 Winner: {winner_name} (ID: {winner_id})\n"
        f"📊 Score: {score}\n"
        f"👤 Loser: {loser_name} (ID: {loser_id})",
        log_type="game",
        chat_context=get_chat_context(update)
    )
```

---

### Example 4: Database Error

```python
async def update_user_stats(user_id, stats):
    """Update user statistics"""
    try:
        conn = get_db_connection()
        # Your database logic
        conn.execute("UPDATE users SET stats = %s WHERE id = %s", (stats, user_id))
        conn.commit()
        
    except Exception as e:
        await send_admin_log(
            f"🔴 Database Error\n"
            f"Function: update_user_stats\n"
            f"User: {user_id}\n"
            f"Error: {str(e)}",
            log_type="db_error",
            chat_context="System"
        )
        raise
```

---

## ✅ STEP 7: GLOBAL ERROR HANDLER (Optional but Recommended)

Add this to catch all unhandled errors:

```python
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Global error handler that logs all errors"""
    try:
        error_msg = str(context.error)
        
        # Get user info if available
        user_info = "Unknown"
        if update and update.effective_user:
            user = update.effective_user
            user_info = f"{user.first_name} (@{user.username or 'no_username'}, ID: {user.id})"
        
        # Get chat context
        chat_ctx = get_chat_context(update) if update else "Unknown"
        
        # Log the error
        await send_admin_log(
            f"❌ Unhandled Error\n"
            f"Error: {error_msg}\n"
            f"User: {user_info}\n"
            f"Chat: {chat_ctx}",
            log_type="error",
            chat_context=chat_ctx
        )
        
    except Exception as e:
        print(f"Error in error handler: {e}")

# Register the error handler in your main() function:
# application.add_error_handler(error_handler)
```

---

## ✅ STEP 8: LOG TYPES REFERENCE

Use appropriate `log_type` for different scenarios:

| Log Type | Emoji | When to Use | Example |
|----------|-------|-------------|---------|
| `command` | ⚡ | Any command execution | User ran /start, /ban, etc. |
| `success` | ✅ | Successful operations | User banned, broadcast sent |
| `error` | ❌ | Failed operations | Command failed, validation error |
| `db_error` | 🔴 | Database issues | Connection timeout, query failed |
| `match` | 🏏 | Match/game events (cricket) | Match started, match ended |
| `game` | 🎮 | Game events (general) | Game started, game ended |
| `info` | ℹ️ | General information | Bot started, settings changed |
| `warning` | ⚠️ | Warning messages | Suspicious activity, rate limit |
| `user` | 👤 | User actions | User registered, profile updated |
| `admin` | 👑 | Admin actions | Admin added, settings changed |

---

## ✅ STEP 9: TESTING YOUR IMPLEMENTATION

### Test Checklist:

1. **Test in DM:**
   - Run an admin command in direct message
   - Check admin log chat receives message with "Context: DM"

2. **Test in Group:**
   - Run a command in a group
   - Check admin log chat receives message with "Context: GC: GroupName (ID: -123)"

3. **Test Error Logging:**
   - Trigger an error (invalid input)
   - Check error is logged to admin chat

4. **Test Different Log Types:**
   - Test command log (⚡)
   - Test success log (✅)
   - Test error log (❌)

5. **Verify Log Format:**
   ```
   ⚡ COMMAND
   ⏰ 2026-01-16 15:30:45
   📍 Context: GC: Arena Of Champions (ID: -1001234567890)
   ━━━━━━━━━━━━━━━━
   CMD: /broadcast by Krutik (@krutik, ID: 123456789)
   ```

---

## ✅ STEP 10: DEPLOYMENT CHECKLIST

- [ ] Added `ADMIN_LOG_BOT_TOKEN` environment variable
- [ ] Added `ADMIN_LOG_CHAT_ID` environment variable
- [ ] Added `send_admin_log()` function to bot code
- [ ] Added `get_chat_context()` function to bot code
- [ ] Added logging to all admin commands
- [ ] Added logging to important user commands (optional)
- [ ] Added global error handler (optional)
- [ ] Tested logging in DM
- [ ] Tested logging in group chat
- [ ] Verified admin log chat receives all messages
- [ ] Pushed code to repository
- [ ] Restarted bot service
- [ ] Confirmed bot is running and logging works

---

## 🎯 QUICK START SUMMARY

1. **Create logging bot** with @BotFather
2. **Get admin chat ID** using @userinfobot
3. **Add environment variables** to hosting platform
4. **Copy helper functions** to your bot code
5. **Add logging to commands** using the templates
6. **Deploy and test**

---

## 💡 TIPS AND BEST PRACTICES

1. **Don't log sensitive data** (passwords, tokens, API keys)
2. **Use appropriate log types** for better organization
3. **Keep log messages concise** but informative
4. **Test thoroughly** before deploying to production
5. **Monitor your admin log chat** regularly
6. **Use the same logging bot** for multiple bots (they all log to same chat)
7. **Add timestamps** to track when actions occur
8. **Include user information** to know who did what
9. **Log both successes and failures** for complete audit trail
10. **Silent fail on logging errors** to not break your main bot

---

## 🆘 TROUBLESHOOTING

### Logs not appearing?
- Check `ADMIN_LOG_BOT_TOKEN` is correct
- Check `ADMIN_LOG_CHAT_ID` is correct
- Make sure you started a chat with the logging bot
- Check environment variables are loaded (`os.getenv()` returns value)

### Wrong chat context?
- Verify `get_chat_context()` function is called correctly
- Check update object is being passed properly

### Logging bot not sending?
- Verify bot token is valid (test with @BotFather)
- Check chat ID is correct (use @userinfobot)
- Make sure you started the logging bot before sending messages

### Multiple bots logging to same chat?
- This is normal and expected! Both bots will log to same admin chat
- Use bot name in logs if you need to distinguish: `f"[CricSaga] CMD: /start"`

---

## 📞 SUPPORT

If you need help:
1. Verify all environment variables are set correctly
2. Check bot tokens are valid
3. Test with a simple command first
4. Review error messages in your bot logs
5. Make sure Python packages are up to date (`python-telegram-bot`)

---

## ✅ DONE!

You now have a complete logging system for your bot! All admin commands, errors, and important events will be logged to your admin chat for easy monitoring and debugging.

**Both CricSaga Bot and Arena Of Champions bot can use the SAME logging bot and log to the SAME admin chat!**

---

*Last Updated: January 16, 2026*
*Version: 1.0*
