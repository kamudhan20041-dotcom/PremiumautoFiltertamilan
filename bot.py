import logging
import logging.config
import os
import sys
from aiohttp import web
from datetime import date, datetime 
import pytz

# --- KOYEB OPTIMIZATION: High-Speed Async Loop ---
try:
    import uvloop
    uvloop.install()
except ImportError:
    pass
# -------------------------------------------------

# Basic Logging Setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logging.getLogger("pyrogram").setLevel(logging.ERROR)
logging.getLogger("aiohttp").setLevel(logging.ERROR) 

from pyrogram import Client, __version__
from pyrogram.raw.all import layer
from database.ia_filterdb import Media
from database.users_chats_db import db
from info import SESSION, API_ID, API_HASH, BOT_TOKEN, LOG_STR, LOG_CHANNEL, PORT, SUPPORT_CHAT_ID
from utils import temp
from Script import script 

# --- KOYEB HEALTH CHECK SERVER ---
routes = web.RouteTableDef()

@routes.get("/", allow_head=True)
async def root_route_handler(request):
    return web.json_response({"status": "running", "platform": "koyeb"})

async def web_server():
    web_app = web.Application(client_max_size=30000000)
    web_app.add_routes(routes)
    return web_app
# ---------------------------------

class Bot(Client):
    def __init__(self):
        super().__init__(
            name=SESSION,
            api_id=API_ID,
            api_hash=API_HASH,
            bot_token=BOT_TOKEN,
            workers=100, # Optimized for high-traffic
            plugins={"root": "plugins"},
            sleep_threshold=10,
        )

    async def start(self):
        # 1. Load Ban List
        b_users, b_chats = await db.get_banned()
        temp.BANNED_USERS = b_users
        temp.BANNED_CHATS = b_chats
        
        # 2. Start Pyrogram Client
        await super().start()
        
        # 3. Ensure Database Indexes (Critical for Speed)
        try:
            await Media.ensure_indexes()
        except Exception as e:
            logging.error(f"Failed to ensure indexes: {e}")

        # 4. Get Bot Info
        me = await self.get_me()
        temp.ME = me.id
        temp.U_NAME = me.username
        temp.B_NAME = me.first_name
        self.username = '@' + me.username
        logging.info(f"Bot Started as {me.username}")
        
        # 5. Send Startup Log
        tz = pytz.timezone('Asia/Kolkata')
        today = date.today()
        now = datetime.now(tz)
        time_str = now.strftime("%H:%M:%S %p")
        if LOG_CHANNEL:
            try:
                await self.send_message(chat_id=int(LOG_CHANNEL), text=script.RESTART_TXT.format(today, time_str))
            except Exception as e:
                logging.error(f"Log Channel Error: {e}")
            
        # 6. Start Koyeb Web Server
        app = web.AppRunner(await web_server())
        await app.setup()
        
        # Koyeb will dynamically assign a port or we default to 8080
        bind_address = "0.0.0.0"
        PORT_VAR = int(os.environ.get("PORT", 8080))
        
        await web.TCPSite(app, bind_address, PORT_VAR).start()
        logging.info(f"Web Server running on Port {PORT_VAR}")

    async def stop(self, *args):
        await super().stop()
        logging.info("Bot stopped.")

if __name__ == "__main__":
    app = Bot()
    app.run()
