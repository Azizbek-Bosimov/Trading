import asyncio
import ccxt
import pandas as pd
import ta
import sys
import os
from flask import Flask
from threading import Thread
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from telegram.constants import ParseMode

# ==================== RENDER UCHUN VEB-SERVER ====================
app_flask = Flask('')

@app_flask.route('/')
def home():
    return "Bot is running 24/7"

def run_flask():
    # Render avtomatik beradigan PORT-ni olamiz, bo'lmasa 8080 ishlatamiz
    port = int(os.environ.get("PORT", 8080))
    app_flask.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()

# ==================== KONFIGURATSIYA ====================
# Tokenni Render Environment Variables-ga qo'shish tavsiya etiladi
TELEGRAM_TOKEN = "8397450809:AAHMf2JdIlnH4yP3kfaDDtuMRFtXD9Zcrys"
CHANNEL_ID     = "@fhoveuss" 
SYMBOL         = "XAU/USDT" # Bybit uchun XAU/USDT formatida yozish aniqroq ishlashi mumkin

exchange = ccxt.bybit({'options': {'defaultType': 'linear'}, 'enableRateLimit': True})
trade_log = {"active": False, "dir": None, "entry": 0, "tp": 0, "sl": 0}

# ... (Sizning trading logikangiz: find_fvg, get_market_bias, elite_analyser o'zgarishsiz qoladi) ...

# --- BU YERDA SIZNING ELITE_ANALYSER FUNKSIYANGIZ TURADI ---

async def loop(app):
    while True:
        res = await elite_analyser()
        if res:
            try:
                await app.bot.send_message(chat_id=CHANNEL_ID, text=res, parse_mode=ParseMode.MARKDOWN)
            except Exception as e:
                print(f"Xabar yuborishda xato: {e}")
        
        await asyncio.sleep(WAIT_TIME)

async def main_async():
    # Botni ishga tushirish
    app_bot = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app_bot.add_handler(CommandHandler("start", start))
    
    await app_bot.initialize()
    await app_bot.start()
    
    # Ham botni, ham analiz loop-ni birga yurgizish
    await asyncio.gather(
        app_bot.updater.start_polling(),
        loop(app_bot)
    )

if __name__ == "__main__":
    # 1. Flask serverni alohida oqimda (thread) boshlash
    keep_alive()
    
    # 2. Asosiy async botni boshlash
    try:
        asyncio.run(main_async())
    except (KeyboardInterrupt, SystemExit):
        pass
