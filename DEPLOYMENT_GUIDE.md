# CricSaga Bot Deployment Guide

## 🚀 Deploying to Render

### Prerequisites
1. GitHub account
2. Render account (free at [render.com](https://render.com))
3. Telegram Bot Token from [@BotFather](https://t.me/BotFather)
4. Your Telegram User ID from [@userinfobot](https://t.me/userinfobot)

---

## 📋 Step-by-Step Deployment

### Step 1: Push to GitHub

```bash
# Initialize git repository (if not already done)
cd "CricSaga Bot"
git init

# Add all files
git add .

# Commit
git commit -m "Initial commit - CricSaga Bot"

# Create repository on GitHub (via web interface)
# Then link and push:
git remote add origin https://github.com/yourusername/cricsaga-bot.git
git branch -M main
git push -u origin main
```

### Step 2: Create PostgreSQL Database on Render

1. Go to [Render Dashboard](https://dashboard.render.com/)
2. Click **"New +"** → **"PostgreSQL"**
3. Configure:
   - **Name**: `cricsaga-db`
   - **Database**: `cricsaga`
   - **User**: `cricsaga_user`
   - **Region**: Choose closest to you
   - **Plan**: **Free**
4. Click **"Create Database"**
5. Wait for provisioning (~2 minutes)
6. **IMPORTANT**: Copy the following:
   - Internal Database URL
   - External Database URL
   - Username
   - Password
   - Host
   - Port

### Step 3: Set Up Database Schema

#### Option A: Via Render Dashboard (Recommended)
1. In your database dashboard, click **"Connect"** → **"External Connection"**
2. Use provided credentials with a PostgreSQL client:
   ```bash
   psql -h <host> -U <user> -d cricsaga
   ```
3. Run the consolidated SQL script:
   ```sql
   \i DATABASE_SETUP.sql
   ```

#### Option B: Via Render Shell
1. Click **"Shell"** in database dashboard
2. Paste contents of DATABASE_SETUP.sql
3. Execute in order (listed above)

### Step 4: Create Web Service

1. Click **"New +"** → **"Web Service"**
2. Select **"Connect a repository"**
3. Choose your GitHub repository
4. Configure:
   - **Name**: `cricsaga-bot`
   - **Environment**: `Python 3`
   - **Region**: Same as database
   - **Branch**: `main`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python bb.py`
   - **Plan**: **Free**

### Step 5: Set Environment Variables

In the web service dashboard, go to **"Environment"** and add:

```
TELEGRAM_BOT_TOKEN=<your_bot_token_from_botfather>
BOT_ADMIN=<your_telegram_user_id>
DB_NAME=cricsaga
DB_USER=<from_render_db_dashboard>
DB_PASSWORD=<from_render_db_dashboard>
DB_HOST=<internal_host_from_render_db>
DB_PORT=5432
```

⚠️ **IMPORTANT**: Use the **Internal Database URL** host for `DB_HOST` (not external)

### Step 6: Deploy!

1. Click **"Create Web Service"**
2. Wait for build to complete (~5 minutes)
3. Check logs for successful startup:
   ```
   🏏 Cricket Bot Started Successfully!
   📊 Registered X users from database
   🎮 Bot is ready to accept commands
   ```

### Step 7: Test Your Bot

1. Open Telegram
2. Search for your bot: `@yourbotname`
3. Send `/start`
4. If you see welcome message → ✅ Success!

---

## 🔍 Common Issues & Solutions

### Issue: Bot not responding

**Solution**: 
- Check logs in Render dashboard
- Verify `TELEGRAM_BOT_TOKEN` is correct
- Ensure no spaces in environment variables

### Issue: Database connection failed

**Solution**:
- Use **Internal Database URL** for `DB_HOST`
- Verify database is in same region as web service
- Check all DB credentials are correct

### Issue: "relation does not exist" error

**Solution**:
- Database schema not set up properly
- Re-run all SQL scripts in correct order
- Check SQL execution logs for errors

### Issue: Bot starts but crashes

**Solution**:
- Check logs for specific error
- Verify Python version (should be 3.12)
- Ensure all dependencies installed

---

## 📊 Monitoring Your Bot

### View Logs
1. Go to your web service in Render
2. Click **"Logs"** tab
3. Monitor for errors or issues

### Database Metrics
1. Go to your database in Render
2. Click **"Metrics"** tab
3. Monitor connections, storage usage

### Keep Bot Alive (Free Plan)
Render free tier spins down after 15 min of inactivity:
- Your bot will restart on first message (30s delay)
- Consider upgrade for 24/7 uptime
- Or use cron-job.org to ping every 14 minutes

---

## 🔄 Updating Your Bot

```bash
# Make changes to code
git add .
git commit -m "Update: description of changes"
git push origin main

# Render auto-deploys on push
# Check deployment progress in dashboard
```

---

## 💰 Cost Breakdown

### Free Tier (Render)
- ✅ PostgreSQL: 1GB storage
- ✅ Web Service: 750 hours/month
- ✅ Auto-deploys from GitHub
- ⚠️ Spins down after 15 min inactivity
- ⚠️ Slower cold starts (~30s)

### Paid Tier ($7/month per service)
- ✅ Always-on (no spin down)
- ✅ Faster performance
- ✅ More storage/memory
- ✅ Priority support

---

## 🆘 Getting Help

1. Check bot logs in Render dashboard
2. Review database connection settings
3. Verify all SQL scripts executed successfully
4. Test database connection manually
5. Check GitHub repository issues

---

## ✅ Deployment Checklist

- [ ] GitHub repository created and pushed
- [ ] Render account created
- [ ] PostgreSQL database created on Render
- [ ] All 6 SQL scripts executed successfully
- [ ] Web service created and linked to GitHub
- [ ] All environment variables set correctly
- [ ] Bot deployed and logs show success
- [ ] Tested `/start` command in Telegram
- [ ] Admin commands work with `BOT_ADMIN` user
- [ ] Database connections stable

---

**🎉 Congratulations! Your bot is now live on Render!**

Share your bot link: `https://t.me/yourbotname`
