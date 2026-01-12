# 🚀 Deploy Cricket Saga Bot on Render.com (Free 24/7 Hosting)

This guide will help you deploy your Cricket Saga Bot on Render.com's free tier with automatic keep-alive system.

## ⚠️ Important Note

Render's free tier shuts down after 15 minutes of inactivity. This bot includes an automatic ping system that sends a request every 3 minutes to keep it running 24/7.

---

## 📦 Quick Reference

### Essential Settings
```
Build Command: pip install -r requirements.txt
Start Command: python bb.py
Instance Type: Free
```

### Required Environment Variables
```
PORT=8080
TELEGRAM_BOT_TOKEN=<from @BotFather>
DATABASE_URL=postgresql://user:password@host:port/database
BOT_ADMIN=<your telegram user id>
```

### After Deployment
1. Copy your Render URL: `https://your-app.onrender.com/`
2. Update `web.py` line 5 with your actual URL
3. Commit and push to redeploy

---

## 📋 Prerequisites

1. A GitHub account
2. Your bot code pushed to a GitHub repository
3. A Render.com account (sign up at https://render.com)
4. Your Telegram bot token from @BotFather
5. Your PostgreSQL database credentials (Supabase, ElephantSQL, or Render's PostgreSQL)

---

## 🎯 Step-by-Step Deployment

### Step 1: Prepare Your Repository

Make sure your repository has these files:
- ✅ `bb.py` (main bot file - already updated with web server support)
- ✅ `web.py` (keep-alive web server - already created)
- ✅ `requirements.txt` (dependencies - already updated with aiohttp)
- ✅ `runtime.txt` (Python version)
- ✅ `.env` (NOT pushed to GitHub - for local testing only)

### Step 2: Push to GitHub

```bash
git add .
git commit -m "Add Render.com deployment support with keep-alive"
git push origin main
```

### Step 3: Create Web Service on Render

1. Go to https://dashboard.render.com/
2. Click **"New +"** → **"Web Service"**
3. Connect your GitHub account and select your repository
4. Configure the service:

   **Basic Settings:**
   - **Name:** `cricsaga-bot` (or any name you prefer)
   - **Region:** Choose closest to you
   - **Branch:** `main`
   - **Root Directory:** `./`
   - **Runtime:** `Python 3`
   
   **Build & Deploy:**
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python bb.py`
   
   **Instance Type:**
   - Select **Free** tier

### Step 4: Add Environment Variables

In the **Environment Variables** section, add these:

```
PORT=8080
TELEGRAM_BOT_TOKEN=your_bot_token_here
DATABASE_URL=your_postgresql_connection_string
BOT_ADMIN=your_telegram_user_id
```

**How to get each variable:**
- `PORT`: Always use `8080` for Render
- `TELEGRAM_BOT_TOKEN`: Get from @BotFather on Telegram
- `DATABASE_URL`: Your PostgreSQL connection string (format: `postgresql://user:password@host:port/database`)
- `BOT_ADMIN`: Your Telegram user ID (get from @userinfobot)

### Step 5: Deploy

1. Click **"Create Web Service"**
2. Wait for the deployment to complete (3-5 minutes)
3. Once deployed, you'll see a URL like: `https://cricsaga-bot.onrender.com`

### Step 6: Update Keep-Alive URL

1. Copy your Render URL (e.g., `https://cricsaga-bot.onrender.com/`)
2. Open `web.py` in your repository
3. Update line 5:
   ```python
   WEB_URL = "https://cricsaga-bot.onrender.com/"  # Replace with YOUR URL
   ```
4. Commit and push:
   ```bash
   git add web.py
   git commit -m "Update keep-alive URL"
   git push
   ```
5. Render will automatically redeploy

---

## ✅ Verify Deployment

### Check if bot is running:

1. **Web Interface:**
   - Visit `https://your-bot.onrender.com/`
   - You should see: "🏏 Cricket Saga Bot is alive and running!"

2. **Health Check:**
   - Visit `https://your-bot.onrender.com/health`
   - Should return JSON: `{"status": "ok", "bot": "Cricket Saga Bot", ...}`

3. **Telegram:**
   - Open Telegram and send `/start` to your bot
   - Bot should respond immediately

### Monitor Logs:

- Go to Render Dashboard → Your Service → **Logs**
- Look for these messages:
  ```
  🌐 Starting web server for Render.com deployment...
  ✅ Web server started on port 8080
  ✅ Keep-alive system activated
  🏏 Cricket Bot Started Successfully!
  ✅ Pinged https://your-bot.onrender.com/ with response: 200
  ```

---

## 🔧 Troubleshooting

### Bot goes to sleep after 15 minutes

**Problem:** Free tier sleeps after 15 minutes of inactivity

**Solution:** 
1. Verify `WEB_URL` in `web.py` is correctly set to your Render URL
2. Check logs - you should see ping messages every 3 minutes
3. Make sure `PORT` environment variable is set to `8080`

### Environment Variables not loading

**Problem:** Bot can't connect to database or Telegram

**Solution:**
1. Go to Render Dashboard → Your Service → **Environment**
2. Verify all variables are set correctly
3. Click **"Manual Deploy"** → **"Deploy latest commit"**

### Database connection errors

**Problem:** `Database connection failed!`

**Solution:**
1. Verify `DATABASE_URL` format: `postgresql://user:password@host:port/database`
2. Make sure your database allows connections from Render's IP addresses
3. For Supabase: Check if connection pooling is enabled

### Build fails

**Problem:** `requirements.txt` dependencies can't install

**Solution:**
1. Check if `requirements.txt` has all dependencies
2. Make sure `aiohttp==3.9.1` is included
3. Try deploying with:
   ```
   Build Command: pip install --upgrade pip && pip install -r requirements.txt
   ```

---

## 📊 Expected Behavior

✅ **Normal Operation:**
- Web server runs on port 8080
- Bot pings itself every 3 minutes
- Logs show: `✅ Pinged https://... with response: 200`
- Bot responds to Telegram commands instantly
- No sleep/downtime

❌ **If something is wrong:**
- No ping logs appearing
- Bot doesn't respond after 15 minutes
- Web endpoint returns errors

---

## 💡 Pro Tips

1. **Free Tier Limits:**
   - 750 hours/month free runtime
   - Service sleeps after 15 min inactivity (but our keep-alive prevents this)
   - Wakes up when pinged (handled automatically)

2. **Database:**
   - Use Supabase free tier (500MB, perfect for this bot)
   - Or use Render's PostgreSQL (90 days free, then paid)

3. **Monitoring:**
   - Check Render logs regularly
   - Set up UptimeRobot for external monitoring (optional)

4. **Updates:**
   - Push to GitHub → Render auto-deploys
   - Or use "Manual Deploy" in Render dashboard

---

## 🎉 Success!

Your bot is now running 24/7 on Render.com for free! 

**Test it:**
```
1. Open Telegram
2. Find your bot
3. Send /start
4. Send /gameon (in a group)
5. Enjoy! 🏏
```

---

## 📞 Support

If you encounter issues:
1. Check Render logs first
2. Verify all environment variables
3. Make sure database is accessible
4. Check if `web.py` has the correct URL

---

**Happy Cricket Gaming! 🏏🎮**
