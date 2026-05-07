import asyncio
import os
import logging
from flask import Flask
from threading import Thread
import ccxt
import pandas as pd
import ta
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler

# ==================== LOGGING ====================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==================== SERVER (Render o'chmasligi uchun) ====================
server = Flask('')
@server.route('/')
def home(): return "🤖 Bot is running..."
def run(): server.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
def keep_alive(): Thread(target=run, daemon=True).start()

# ==================== CONFIG ====================
# Siz bergan yangi token:
TOKEN = "8397450809:AAFtv0n6D1StMLmqeNb1EeKqHOnznVvcXpk"
CHANNEL = "@fhoveuss"

# MEXC'da oltin formatlari har xil bo'lishi mumkin, hammasini tekshiramiz
POSSIBLE_SYMBOLS = ["PAXG/USDT", "PAXGUSDT", "XAU_USDT"]

exchange = ccxt.mexc({'enableRateLimit': True})

def get_data():
    """Birjadan to'g'ri simvolni topib ma'lumot oladi"""
    for sym in POSSIBLE_SYMBOLS:
        try:
            ohlcv = exchange.fetch_ohlcv(sym, "15m", limit=100)
            if ohlcv:
                df = pd.DataFrame(ohlcv, columns=['t', 'o', 'h', 'l', 'c', 'v'])
                return df, sym
        except Exception:
            continue
    return None, None

async def loop(app):
    logger.info("Tahlil boshlandi...")
    while True:
        try:
            df, active_symbol = get_data()
            if df is not None:
                close = df['c']
                # Indikatorlar
                rsi = ta.momentum.RSIIndicator(close, window=14).rsi().iloc[-1]
                ema20 = ta.trend.EMAIndicator(close, window=20).ema_indicator().iloc[-1]
                ema50 = ta.trend.EMAIndicator(close, window=50).ema_indicator().iloc[-1]
                price = close.iloc[-1]
                
                # Signal shartlari (RSI + Trend)
                signal_type = "WAIT"
                if rsi < 38 and price > ema20: 
                    signal_type = "BUY 🟢"
                elif rsi > 62 and price < ema20: 
                    signal_type = "SELL 🔴"
                
                if signal_type != "WAIT":
                    msg = (
                        f"🚀 *{active_symbol} SIGNAL*\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"💰 Narx: `{price}`\n"
                        f"📊 RSI: `{rsi:.1f}`\n"
                        f"⚡️ Signal: *{signal_type}*\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"⏱ Timeframe: 15m"
                    )
                    await app.bot.send_message(chat_id=CHANNEL, text=msg, parse_mode="Markdown")
                    logger.info(f"✅ Signal yuborildi: {signal_type}")
                else:
                    logger.info(f"🔍 {active_symbol} tahlil qilindi: Signal yo'q (RSI: {rsi:.1f})")
            else:
                logger.error("❌ Birja bilan aloqa yo'q!")
        except Exception as e:
            logger.error(f"Loop xatosi: {e}")
        
        await asyncio.sleep(60) # Har 1 daqiqada tekshiradi

async def main():
    # drop_pending_updates=True eski tiqilib qolgan xabarlarni tozalaydi
    app = ApplicationBuilder().token(TOKEN).build()
    
    await app.initialize()
    await app.start()
    
    logger.info("Bot Telegramga muvaffaqiyatli ulandi!")
    
    # Bir vaqtda ham xabarlarni kutadi, ham tahlil qiladi
    await asyncio.gather(
        app.updater.start_polling(drop_pending_updates=True),
        loop(app)
    )

if __name__ == "__main__":
    keep_alive()
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
