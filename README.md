# 🏏 CricSaga Bot - Telegram Cricket Game

[![Python](https://img.shields.io/badge/Python-3.12-blue.svg)](https://www.python.org/)
[![Telegram Bot API](https://img.shields.io/badge/Telegram%20Bot%20API-20.7-blue.svg)](https://python-telegram-bot.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15+-blue.svg)](https://www.postgresql.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

A feature-rich, production-ready Telegram bot for playing cricket matches with friends! Built with Python, featuring ranked matchmaking, anti-cheat systems, career statistics, and comprehensive admin tools.

## ✨ Features

### 🎮 Core Gameplay
- **Single & Multiplayer Matches** - Play solo or with friends
- **Ranked System** - Competitive matchmaking with ELO rating (1000-3000+)
- **Challenge Mode** - Direct challenge specific players
- **11 Rank Tiers** - From Bronze III to Legend
- **Match Customization** - Choose overs (1, 2, 3, 5, 10)
- **Real-time Ball-by-ball Commentary** - Immersive match experience

### 🛡️ Anti-Cheat System
- **Pattern Detection** - Identifies win-trading and suspicious behavior
- **Trust Score System** - 0-100 score tracking player reputation
- **New Player Penalties** - Progressive rating unlock (30% → 100%)
- **Automatic Flagging** - AI-powered suspicious activity detection
- **Admin Review Tools** - Comprehensive moderation commands

### 📊 Career & Stats
- **Comprehensive Career Profiles** - Track your cricket journey
- **Detailed Statistics** - Matches, wins, runs, wickets, boundaries
- **Match History** - Full record of all matches played
- **Global Leaderboard** - Top 10 players by rating
- **Rank Progression** - Climb from Bronze to Legend

### 👑 Admin Features
- **User Management** - Blacklist/whitelist users
- **Anti-cheat Review** - Review and clear suspicious flags
- **Rating Control** - Suspend/unsuspend player ratings
- **Broadcast System** - Send announcements to all users
- **Database Backups** - Built-in backup/restore functionality

## 🚀 Quick Start

### Prerequisites
- Python 3.12+
- PostgreSQL 15+
- Telegram Bot Token (from [@BotFather](https://t.me/BotFather))

### Installation

1. **Clone the repository**
```bash
git clone https://github.com/yourusername/cricsaga-bot.git
cd cricsaga-bot
```

2. **Install dependencies**
```bash
pip install -r requirements.txt
```

3. **Set up PostgreSQL database**
```bash
# Create database
createdb cricsaga

# Run consolidated setup script
psql -d cricsaga -f DATABASE_SETUP.sql
```

4. **Configure environment variables**
```bash
cp .env.example .env
# Edit .env with your credentials
```

5. **Run the bot**
```bash
python bb.py
```

## 🌐 Deploy to Render

### Option 1: One-Click Deploy
[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy)

### Option 2: Manual Deployment

1. **Create Render account** at [render.com](https://render.com)

2. **Create PostgreSQL Database**
   - Click "New +" → "PostgreSQL"
   - Name: `cricsaga-db`
   - Choose free plan
   - Copy internal database URL

3. **Run Database Setup**
   - Connect to database using psql or Render dashboard
   - Execute all SQL files in order (see Installation step 3)

4. **Create Web Service**
   - Click "New +" → "Web Service"
   - Connect your GitHub repository
   - Settings:
     - **Name**: `cricsaga-bot`
     - **Environment**: `Python 3`
     - **Build Command**: `pip install -r requirements.txt`
     - **Start Command**: `python bb.py`

5. **Set Environment Variables**
   ```
   TELEGRAM_BOT_TOKEN=your_bot_token
   BOT_ADMIN=your_telegram_user_id
   DB_NAME=cricsaga
   DB_USER=cricsaga_user
   DB_PASSWORD=your_db_password
   DB_HOST=your_render_db_host
   DB_PORT=5432
   ```

6. **Deploy!** Click "Create Web Service"

## 📖 Bot Commands

### Player Commands
- `/start` - Start the bot and register
- `/play` - Create a new cricket match
- `/ranked` - Join ranked matchmaking queue
- `/challenge` - Challenge a specific player (reply to their message)
- `/career` - View your career statistics and trust score
- `/leaderboard` - View top 10 players
- `/ranks` - View all rank tiers
- `/rankedinfo` - Complete guide to ranked system
- `/help` - View all available commands

### Admin Commands
- `/broadcast <message>` - Send message to all users
- `/blacklist <user_id>` - Ban user from bot
- `/whitelist <user_id>` - Unban user
- `/flaggedmatches` - View suspicious activities
- `/reviewmatch <flag_id>` - Review specific flag
- `/clearflag <flag_id>` - Clear false positive flag
- `/suspendrating <user_id>` - Suspend rating changes
- `/unsuspendrating <user_id>` - Remove rating suspension

## 🎯 Rank System

| Rank | Rating Range | Emoji |
|------|--------------|-------|
| Bronze III | 1000-1099 | 🥉 |
| Bronze II | 1100-1199 | 🥉 |
| Bronze I | 1200-1299 | 🥉 |
| Silver III | 1300-1399 | 🥈 |
| Silver II | 1400-1499 | 🥈 |
| Silver I | 1500-1599 | 🥈 |
| Gold III | 1600-1699 | 🥇 |
| Gold II | 1700-1799 | 🥇 |
| Gold I | 1800-1899 | 🥇 |
| Platinum | 1900-2499 | 💎 |
| Legend | 2500+ | 🏆 |

## 🛡️ Anti-Cheat System

### Trust Score Levels
- 🟢 **70-100**: Excellent - Full rating gains
- 🟡 **40-69**: Good - Normal play
- 🟠 **20-39**: Low - 50% rating gains
- 🔴 **0-19**: Very Low - Rating suspended

### How to Maintain High Trust
✅ Play with different opponents  
✅ Natural win/loss patterns  
✅ Consistent fair play  
❌ Avoid playing same person 5+ times/day  
❌ No win-trading (alternating wins)  

### Recovery
- Trust score recovers over 10-20 fair matches
- Admins can clear false positive flags
- System is designed to protect fair players

## 📁 Project Structure

```
CricSaga Bot/
├── bb.py                      # Main bot file
├── db_handlerr.py            # Database handler (if separate)
├── requirements.txt          # Python dependencies
├── runtime.txt               # Python version for deployment
├── Procfile                  # Render/Heroku deployment config
├── .env.example              # Environment variables template
├── .gitignore               # Git ignore rules
├── README.md                # This file
├── DATABASE_SETUP.sql       # Complete database schema (consolidated)
├── data/                    # Match history storage
└── logs/                    # Application logs
```

## 🔧 Configuration

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `TELEGRAM_BOT_TOKEN` | Bot token from @BotFather | ✅ Yes |
| `BOT_ADMIN` | Admin Telegram user ID | ✅ Yes |
| `DB_NAME` | PostgreSQL database name | ✅ Yes |
| `DB_USER` | Database username | ✅ Yes |
| `DB_PASSWORD` | Database password | ✅ Yes |
| `DB_HOST` | Database host | ✅ Yes |
| `DB_PORT` | Database port (default: 5432) | ❌ No |

### Getting Your Telegram User ID
1. Message [@userinfobot](https://t.me/userinfobot)
2. Copy your user ID
3. Use it as `BOT_ADMIN` value

## 🐛 Troubleshooting

### Bot Not Responding
- Check bot token is correct
- Verify bot is running: `ps aux | grep bb.py`
- Check logs: `tail -f logs/bot_output.log`

### Database Connection Issues
- Verify PostgreSQL is running
- Check DB credentials in `.env`
- Test connection: `psql -h HOST -U USER -d DATABASE`

### Deployment Issues on Render
- Ensure all SQL scripts ran successfully
- Check environment variables are set
- View logs in Render dashboard
- Verify Python version matches runtime.txt

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📝 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🙏 Acknowledgments

- Built with [python-telegram-bot](https://python-telegram-bot.org/)
- PostgreSQL for robust data storage
- Cricket fans worldwide 🏏

## 📞 Support

- Create an issue on GitHub
- Join our Telegram group: [Link]
- Email: support@cricsaga.com

## 🎯 Roadmap

- [ ] Team tournaments
- [ ] Player achievements/badges
- [ ] Multi-language support
- [ ] Web dashboard
- [ ] Mobile app integration
- [ ] Advanced analytics

---

**Made with ❤️ for cricket fans by cricket fans**

⭐ Star this repo if you found it helpful!
