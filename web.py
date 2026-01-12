"""
Web server for keeping the bot alive on Render.com
Pings itself every 3 minutes to prevent inactivity shutdown
"""

# TODO: After deploying to Render, update this URL with your actual Render URL
# Example: WEB_URL = "https://your-bot-name.onrender.com/"
WEB_URL = "https://your-bot-name.onrender.com/"  # Update this after deployment

WEB_SLEEP = 3 * 60  # Ping every 3 minutes

from aiohttp import web
import asyncio
import aiohttp
import logging
import traceback

log = logging.getLogger(__name__)

routes = web.RouteTableDef()

@routes.get('/', allow_head=True)
async def hello(request):
    """Health check endpoint"""
    return web.Response(text="🏏 Cricket Saga Bot is alive and running!")

@routes.get('/health', allow_head=True)
async def health(request):
    """Health check endpoint for monitoring"""
    return web.json_response({
        "status": "ok",
        "bot": "Cricket Saga Bot",
        "message": "Bot is running successfully"
    })

def web_server():
    """Create and configure the web server"""
    app = web.Application()
    app.add_routes(routes)
    return app

async def keep_alive():
    """Keep the bot alive by pinging itself every 3 minutes"""
    if WEB_URL and WEB_URL != "https://your-bot-name.onrender.com/":
        log.info(f"🔄 Keep-alive system started. Pinging {WEB_URL} every {WEB_SLEEP // 60} minutes")
        while True:
            await asyncio.sleep(WEB_SLEEP)
            try:
                async with aiohttp.ClientSession(
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as session:
                    async with session.get(WEB_URL) as resp:
                        log.info(
                            f"✅ Pinged {WEB_URL} with response: {resp.status}"
                        )
            except asyncio.TimeoutError:
                log.warning(f"⚠️ Timeout while pinging {WEB_URL}")
            except Exception as e:
                log.error(f"❌ Error pinging {WEB_URL}: {e}")
                traceback.print_exc()
    else:
        log.warning("⚠️ WEB_URL not configured. Keep-alive system disabled.")
        log.warning("👉 Update WEB_URL in web.py after deploying to Render.com")
