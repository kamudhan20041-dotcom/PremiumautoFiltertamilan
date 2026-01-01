import logging
import logging.config
import os
from aiohttp import web
from datetime import date, datetime 
import pytz

# Basic Logging Setup
logging.basicConfig(level=logging.INFO)
logging.getLogger("pyrogram").setLevel(logging.ERROR)
logging.getLogger("imdbpy").setLevel(logging.ERROR)

from pyrogram import Client, __version__
from pyrogram.raw.all import layer
from database.ia_filterdb import Media
from database.users_chats_db import db
from info import SESSION, API_ID, API_HASH, BOT_TOKEN, LOG_STR, LOG_CHANNEL, PORT, SUPPORT_CHAT_ID
from utils import temp
from Script import script 

# --- FAILSAFE WEB SERVER (Keeps Koyeb Alive) ---
routes = web.RouteTableDef()

@routes.get("/", allow_head=True)
async def root_route_handler(request):
    return web.json_response({"status": "running"})

async def web_server():
    web_app = web.Application(client_max_size=30000000)
    web_app.add_routes(routes)
    return web_app
# -----------------------------------------------

class Bot(Client):
    def __init__(self):
        super().__init__(
            name=SESSION,
            api_id=API_ID,
            api_hash=API_HASH,
            bot_token=BOT_TOKEN,
            workers=50,
            plugins={"root": "plugins"},
            sleep_threshold=5,
        )

    async def start(self):
        b_users, b_chats = await db.get_banned()
        temp.BANNED_USERS = b_users
        temp.BANNED_CHATS = b_chats
        await super().start()
        await Media.ensure_indexes()
        
        me = await self.get_me()
        temp.ME = me.id
        temp.U_NAME = me.username
        temp.B_NAME = me.first_name
        self.username = '@' + me.username
        
        logging.info(f"Bot Started as {me.username}")
        
        # --- Notification Logic (Safe version) ---
        tz = pytz.timezone('Asia/Kolkata')
        today = date.today()
        now = datetime.now(tz)
        time_str = now.strftime("%H:%M:%S %p")
        
        try:
            # Send to Log Channel
            if LOG_CHANNEL:
                await self.send_message(chat_id=int(LOG_CHANNEL), text=script.RESTART_TXT.format(today, time_str))
        except Exception as e:
            logging.error(f"Failed to send startup message: {e}")
            
        # --- Start Web Server ---
        app = web.AppRunner(await web_server())
        await app.setup()
        bind_address = "0.0.0.0"
        PORT_VAR = int(os.environ.get("PORT", 8080))
        await web.TCPSite(app, bind_address, PORT_VAR).start()
        logging.info(f"Web Server running on Port {PORT_VAR}")

    async def stop(self, *args):
        await super().stop()
        logging.info("Bot stopped. Bye.")

if __name__ == "__main__":
    app = Bot()
    app.run()
