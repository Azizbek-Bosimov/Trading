import asyncio
import os
from flask import Flask
from threading import Thread
import ccxt
import pandas as pd
import ta
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from telegram.constants import ParseMode

# ==================== RENDER UCHUN VEB-SERVER (SHART!) ====================
server = Flask('')

@server.route('/')
def home():
    return "Bot is active!"

def run_server():
    # Render avtomatik beradigan portni oladi
    port = int(os.environ.get("PORT", 8080))
    server.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_server)
    t.start()

# ==================== KONFIGURATSIYA ====================
TELEGRAM_TOKEN = "8397450809:AAHMf2JdIlnH4yP3kfaDDtuMRFtXD9Zcrys"
CHANNEL_ID     = "@fhoveuss" 
SYMBOL         = "XAU/USDT"
WAIT_TIME      = 20 

# ... (Bu yerga o'zingizning elite_analyser, find_fvg va boshqa funksiyalaringizni qo'ying) ...

async def main():
    # Botni yaratish
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    # Buyruqlarni qo'shish
    app.add_handler(CommandHandler("start", start))
    
    # Botni ishga tushirish
    await app.initialize()
    await app.start()
    
    # Loop va Pollingni parallel yurgizish
    await asyncio.gather(
        app.updater.start_polling(),
        loop(app)
    )

if __name__ == "__main__":
    # 1. Veb-serverni ishga tushiramiz
    keep_alive()
    print("Web-server ishga tushdi!")
    
    # 2. Botni ishga tushiramiz
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
