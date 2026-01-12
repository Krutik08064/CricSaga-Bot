# 🚀 Quick Start Guide - CricSaga Bot

Get your cricket bot running in 5 minutes!

## ⚡ Fastest Way (Local Development)

### 1. Prerequisites Check
- ✅ Python 3.12+ installed
- ✅ PostgreSQL 15+ running
- ✅ Git installed

### 2. Clone & Install
```bash
git clone https://github.com/yourusername/cricsaga-bot.git
cd cricsaga-bot
pip install -r requirements.txt
```

### 3. Get Bot Token
1. Message [@BotFather](https://t.me/BotFather) on Telegram
2. Send `/newbot`
3. Follow prompts to create your bot
4. Copy the bot token (looks like: `1234567890:ABCdefGHIjklMNOpqrsTUVwxyz`)

### 4. Get Your User ID
1. Message [@userinfobot](https://t.me/userinfobot)
2. Copy your ID (looks like: `123456789`)

### 5. Setup Database
```bash
# Create database
createdb cricsaga

# Run setup (Windows)
.\setup_database.ps1

# OR run setup (Linux/Mac)
./setup_database.sh
```

### 6. Configure Environment
```bash
# Copy example file
cp .env.example .env

# Edit .env with your values:
# - TELEGRAM_BOT_TOKEN=<paste your bot token>
# - BOT_ADMIN=<paste your user ID>
# - DB_NAME=cricsaga
# - DB_USER=postgres
# - DB_PASSWORD=<your postgres password>
# - DB_HOST=localhost
# - DB_PORT=5432
```

### 7. Run!
```bash
python bb.py
```

### 8. Test
Open Telegram → Search for your bot → Send `/start`

✅ **Done! Your bot is running!**

---

## 🌐 Deploy to Cloud (Render - Free)

### 1. Push to GitHub
```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/yourusername/cricsaga-bot.git
git push -u origin main
```

### 2. Create Render Account
- Go to [render.com](https://render.com)
- Sign up with GitHub

### 3. Create Database
- Click "New +" → "PostgreSQL"
- Name: `cricsaga-db`
- Plan: Free
- Create Database

### 4. Run SQL Script
- Open database shell in Render
- Copy/paste contents of DATABASE_SETUP.sql

### 5. Create Web Service
- Click "New +" → "Web Service"
- Connect your GitHub repo
- Name: `cricsaga-bot`
- Environment: Python 3
- Build: `pip install -r requirements.txt`
- Start: `python bb.py`

### 6. Add Environment Variables
```
TELEGRAM_BOT_TOKEN=<your_bot_token>
BOT_ADMIN=<your_user_id>
DB_NAME=cricsaga
DB_USER=<from_render_db>
DB_PASSWORD=<from_render_db>
DB_HOST=<internal_host_from_render>
DB_PORT=5432
```

### 7. Deploy
- Click "Create Web Service"
- Wait ~5 minutes
- Check logs for success message

✅ **Your bot is now live 24/7!**

---

## 🆘 Troubleshooting

### Bot not responding?
```bash
# Check if running
ps aux | grep bb.py

# Check logs
tail -f logs/bot_output.log

# Restart
python bb.py
```

### Database issues?
```bash
# Test connection
psql -h localhost -U postgres -d cricsaga

# Check if tables exist
\dt

# Re-run setup if needed
./setup_database.sh
```

### Import errors?
```bash
# Reinstall dependencies
pip install -r requirements.txt --force-reinstall
```

---

## 📚 Next Steps

- Read [README.md](README.md) for full documentation
- Check [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) for detailed deploy steps
- Join Telegram community for support
- Star the repo if you found it helpful! ⭐

---

## 🎮 Bot Commands Preview

**Player Commands:**
- `/start` - Register and get started
- `/play` - Create a new match
- `/ranked` - Join competitive queue
- `/career` - View your stats
- `/leaderboard` - Top players

**Admin Commands:**
- `/broadcast` - Message all users
- `/blacklist` - Ban users
- `/flaggedmatches` - Review anti-cheat
- `/clearflag` - Clear false flags

---

**Need help?** Open an issue or join our Telegram group!

**Happy gaming! 🏏**
