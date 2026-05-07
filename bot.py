import asyncio
import os
import logging
from flask import Flask
from threading import Thread
import ccxt
import pandas as pd
import ta
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from telegram.constants import ParseMode

# ==================== LOGGING ====================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==================== RENDER UCHUN VEB-SERVER ====================
server = Flask('')

@server.route('/')
def home():
    return "✅ Bot is active and running!"

def run_server():
    port = int(os.environ.get("PORT", 8080))
    server.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_server, daemon=True)
    t.start()

# ==================== KONFIGURATSIYA ====================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8397450809:AAHMf2JdIlnH4yP3kfaDDtuMRFtXD9Zcrys")
CHANNEL_ID     = "@fhoveuss"
SYMBOL         = "XAUUSDT" 
TIMEFRAME      = "15m"     
WAIT_TIME      = 60        # MEXC bloklamasligi uchun 1 daqiqa ideal
CANDLE_LIMIT   = 100       

# ==================== CCXT MEXC (Eng kam cheklovli) ====================
exchange = ccxt.mexc({
    'enableRateLimit': True,
    'options': {'defaultType': 'spot'} 
})

# ==================== MA'LUMOT OLISH ====================
def get_ohlcv(symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
    try:
        # MEXC ba'zan spotda 'XAU/USDT' yoki 'PAXG/USDT' ishlatadi
        # Agar XAUUSDT ishlamasa, PAXGUSDT (oltin peg) ko'rib chiqiladi
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        if not ohlcv:
            return pd.DataFrame()
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        return df
    except Exception as e:
        logger.error(f"MEXC dan ma'lumot olishda xato: {e}")
        return pd.DataFrame()

# ==================== TEXNIK TAHLIL ====================
def elite_analyser(df: pd.DataFrame) -> dict:
    if df is None or df.empty or len(df) < 30:
        return {'signal': 'WAIT', 'reason': 'Yetarli ma\'lumot yo\'q', 'price': 0, 'rsi': 50}

    close = df['close']
    rsi    = ta.momentum.RSIIndicator(close, window=14).rsi()
    ema20  = ta.trend.EMAIndicator(close, window=20).ema_indicator()
    ema50  = ta.trend.EMAIndicator(close, window=50).ema_indicator()
    bb     = ta.volatility.BollingerBands(close, window=20, window_dev=2)

    last_rsi    = rsi.iloc[-1]
    last_close  = close.iloc[-1]
    last_ema20  = ema20.iloc[-1]
    last_ema50  = ema50.iloc[-1]
    bb_upper    = bb.bollinger_hband().iloc[-1]
    bb_lower    = bb.bollinger_lband().iloc[-1]

    reasons = []
    buy_score  = 0
    sell_score = 0

    # RSI Shartlari (Biroz yumshatildi: 40/60)
    if last_rsi < 40:
        buy_score += 2
        reasons.append(f"RSI past ({last_rsi:.1f})")
    elif last_rsi > 60:
        sell_score += 2
        reasons.append(f"RSI baland ({last_rsi:.1f})")

    # Trend
    if last_ema20 > last_ema50:
        buy_score += 1
    else:
        sell_score += 1

    # Bollinger
    if last_close <= bb_lower:
        buy_score += 2
        reasons.append("Narx BB pastida")
    elif last_close >= bb_upper:
        sell_score += 2
        reasons.append("Narx BB tepasida")

    # Signal qarori
    if buy_score >= 3:
        signal = 'BUY'
    elif sell_score >= 3:
        signal = 'SELL'
    else:
        signal = 'WAIT'

    return {
        'signal': signal,
        'reason': ' | '.join(reasons),
        'price': last_close,
        'rsi': last_rsi,
        'ema20': last_ema20,
        'ema50': last_ema50
    }

# ==================== ASOSIY LOOP ====================
async def loop(app):
    logger.info("Tahlil loop boshlandi...")
    while True:
        try:
            df = get_ohlcv(SYMBOL, TIMEFRAME, CANDLE_LIMIT)
            if not df.empty:
                analysis = elite_analyser(df)
                
                if analysis['signal'] != 'WAIT':
                    price = analysis['price']
                    emoji = "🟢" if analysis['signal'] == 'BUY' else "🔴"
                    msg = (
                        f"{emoji} *{SYMBOL} SIGNAL*\n"
                        f"💰 Narx: `{price:.2f}`\n"
                        f"📊 RSI: `{analysis['rsi']:.1f}`\n"
                        f"📝 Sabab: {analysis['reason']}\n"
                        f"⏱ Timeframe: {TIMEFRAME}"
                    )
                    await app.bot.send_message(chat_id=CHANNEL_ID, text=msg, parse_mode=ParseMode.MARKDOWN)
                    logger.info(f"Signal yuborildi: {analysis['signal']}")
                else:
                    logger.info(f"Signal yo'q. RSI: {analysis['rsi']:.1f}")
        except Exception as e:
            logger.error(f"Loop xatosi: {e}")
        
        await asyncio.sleep(WAIT_TIME)

# ==================== MAIN ====================
async def main():
    # Conflict xatosini kamaytirish uchun application yaratish
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    await app.initialize()
    await app.start()
    
    # Faqat bir marta loop va pollingni ishga tushirish
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
