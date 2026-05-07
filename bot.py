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
    # Render avtomatik port beradi, bo'lmasa 8080
    port = int(os.environ.get("PORT", 8080))
    server.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_server, daemon=True)
    t.start()

# ==================== KONFIGURATSIYA ====================
# Tokenni Render panelida 'Environment Variables'ga qo'shgan bo'lsangiz os.environ orqali oladi
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8397450809:AAHMf2JdIlnH4yP3kfaDDtuMRFtXD9Zcrys")
CHANNEL_ID     = "@fhoveuss"
SYMBOL         = "XAUUSDT" # Bybit uchun format
TIMEFRAME      = "15m"     
WAIT_TIME      = 60        # Birja bloklamasligi uchun 60 soniya tavsiya etiladi
CANDLE_LIMIT   = 100       

# ==================== CCXT BYBIT (Binance o'rniga) ====================
# Bybit Render serverlari joylashgan hududlarda (AQSH/Yevropa) yaxshi ishlaydi
exchange = ccxt.bybit({
    'options': {'defaultType': 'linear'},
    'enableRateLimit': True,
})

# ==================== MA'LUMOT OLISH ====================
def get_ohlcv(symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        if not ohlcv:
            return pd.DataFrame()
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        return df
    except Exception as e:
        logger.error(f"Birjadan ma'lumot olishda xato: {e}")
        return pd.DataFrame()

# ==================== TEXNIK TAHLIL ====================
def elite_analyser(df: pd.DataFrame) -> dict:
    # Ma'lumot yetarli emasligini tekshirish ('rsi' xatosini oldini oladi)
    if df is None or df.empty or len(df) < 50:
        return {'signal': 'WAIT', 'reason': 'Yetarli ma\'lumot yo\'q', 'price': 0, 'rsi': 50, 'ema20': 0, 'ema50': 0, 'bb_upper': 0, 'bb_lower': 0}

    close = df['close']

    # --- Indikatorlar ---
    rsi    = ta.momentum.RSIIndicator(close, window=14).rsi()
    ema20  = ta.trend.EMAIndicator(close, window=20).ema_indicator()
    ema50  = ta.trend.EMAIndicator(close, window=50).ema_indicator()
    macd   = ta.trend.MACD(close)
    bb     = ta.volatility.BollingerBands(close, window=20, window_dev=2)

    # Oxirgi qiymatlar
    last_rsi    = rsi.iloc[-1]
    last_close  = close.iloc[-1]
    last_ema20  = ema20.iloc[-1]
    last_ema50  = ema50.iloc[-1]
    macd_line   = macd.macd().iloc[-1]
    signal_line = macd.macd_signal().iloc[-1]
    bb_upper    = bb.bollinger_hband().iloc[-1]
    bb_lower    = bb.bollinger_lband().iloc[-1]

    reasons = []
    buy_score  = 0
    sell_score = 0

    if last_rsi < 35:
        buy_score += 2
        reasons.append(f"RSI oversold ({last_rsi:.1f})")
    elif last_rsi > 65:
        sell_score += 2
        reasons.append(f"RSI overbought ({last_rsi:.1f})")

    if last_ema20 > last_ema50:
        buy_score += 1
        reasons.append("EMA20 > EMA50 (uptrend)")
    else:
        sell_score += 1
        reasons.append("EMA20 < EMA50 (downtrend)")

    if macd_line > signal_line:
        buy_score += 1
        reasons.append("MACD bullish")
    else:
        sell_score += 1
        reasons.append("MACD bearish")

    if last_close <= bb_lower:
        buy_score += 2
        reasons.append("Narx BB pastki chegarasida")
    elif last_close >= bb_upper:
        sell_score += 2
        reasons.append("Narx BB yuqori chegarasida")

    if buy_score >= 4:
        signal = 'BUY'
    elif sell_score >= 4:
        signal = 'SELL'
    else:
        signal = 'WAIT'

    return {
        'signal':    signal,
        'reason':    ' | '.join(reasons),
        'price':     last_close,
        'rsi':       last_rsi,
        'ema20':     last_ema20,
        'ema50':     last_ema50,
        'bb_upper':  bb_upper,
        'bb_lower':  bb_lower,
    }

# ==================== FVG TOPISH ====================
def find_fvg(df: pd.DataFrame) -> list:
    fvgs = []
    if df is None or df.empty or len(df) < 3:
        return fvgs

    for i in range(1, len(df) - 1):
        prev_high  = df['high'].iloc[i - 1]
        prev_low   = df['low'].iloc[i - 1]
        next_high  = df['high'].iloc[i + 1]
        next_low   = df['low'].iloc[i + 1]

        if prev_high < next_low:
            fvgs.append({'type': 'bullish', 'top': next_low, 'bottom': prev_high})
        elif prev_low > next_high:
            fvgs.append({'type': 'bearish', 'top': prev_low, 'bottom': next_high})

    return fvgs[-3:] if fvgs else []

# ==================== XABAR FORMATLASH ====================
def format_signal_message(analysis: dict, fvgs: list) -> str:
    signal = analysis['signal']
    if signal == 'WAIT': return ""

    emoji  = "🟢" if signal == 'BUY' else "🔴"
    action = "LONG / BUY" if signal == 'BUY' else "SHORT / SELL"
    price  = analysis['price']
    
    tp1 = price * 1.005 if signal == 'BUY' else price * 0.995
    tp2 = price * 1.010 if signal == 'BUY' else price * 0.990
    sl  = price * 0.992 if signal == 'BUY' else price * 1.008

    msg = (
        f"{emoji} *{SYMBOL} — {action} SIGNAL*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💰 *Kirish:* `{price:.2f}`\n"
        f"🎯 *TP1:* `{tp1:.2f}`\n"
        f"🎯 *TP2:* `{tp2:.2f}`\n"
        f"🛑 *SL:* `{sl:.2f}`\n\n"
        f"📊 *RSI:* `{analysis['rsi']:.1f}`\n"
        f"📝 *Sabab:* _{analysis['reason']}_\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⏱ Timeframe: `{TIMEFRAME}`"
    )
    return msg

# ==================== ASOSIY LOOP ====================
async def loop(app):
    logger.info("Tahlil loop boshlandi...")
    while True:
        try:
            df = get_ohlcv(SYMBOL, TIMEFRAME, CANDLE_LIMIT)
            if not df.empty:
                analysis = elite_analyser(df)
                fvgs     = find_fvg(df)
                msg      = format_signal_message(analysis, fvgs)

                if msg:
                    await app.bot.send_message(chat_id=CHANNEL_ID, text=msg, parse_mode=ParseMode.MARKDOWN)
                    logger.info(f"Signal yuborildi: {analysis['signal']}")
                else:
                    logger.info(f"Tahlil qilindi: Signal yo'q (WAIT). RSI={analysis['rsi']:.1f}")
        except Exception as e:
            logger.error(f"Loop ichida xato: {e}")

        await asyncio.sleep(WAIT_TIME)

# ==================== MAIN ====================
async def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    # Start buyrug'i
    async def start(update, context):
        await update.message.reply_text(f"🚀 Bot ishga tushdi! {SYMBOL} tahlil qilinmoqda...")
    
    app.add_handler(CommandHandler("start", start))

    await app.initialize()
    await app.start()
    
    await asyncio.gather(
        app.updater.start_polling(drop_pending_updates=True),
        loop(app)
    )

if __name__ == "__main__":
    keep_alive() # Render o'chirib yubormasligi uchun
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot to'xtatildi.")
