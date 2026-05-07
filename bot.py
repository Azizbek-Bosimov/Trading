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
CHANNEL_ID     = os.environ.get("CHANNEL_ID", "@fhoveuss")
SYMBOL         = "XAU/USDT"
TIMEFRAME      = "15m"       # Tahlil qilinadigan vaqt oralig'i
WAIT_TIME      = 20          # Signallar orasidagi kutish vaqti (soniya)
CANDLE_LIMIT   = 100         # Yuklanadigan shamlar soni

# ==================== CCXT BIRJA ====================
exchange = ccxt.binance({
    'options': {'defaultType': 'future'},
    'enableRateLimit': True,
})

# ==================== MA'LUMOT OLISH ====================
def get_ohlcv(symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
    """Birjadan OHLCV ma'lumotlarini oladi."""
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        return df
    except Exception as e:
        logger.error(f"Ma'lumot olishda xato: {e}")
        return pd.DataFrame()

# ==================== TEXNIK TAHLIL ====================
def elite_analyser(df: pd.DataFrame) -> dict:
    """
    RSI, EMA, MACD va Bollinger Bands asosida signal chiqaradi.
    Qaytaradi: {'signal': 'BUY'|'SELL'|'WAIT', 'reason': str, 'price': float}
    """
    if df.empty or len(df) < 50:
        return {'signal': 'WAIT', 'reason': 'Yetarli ma\'lumot yo\'q', 'price': 0}

    close = df['close']
    high  = df['high']
    low   = df['low']

    # --- Indikatorlar ---
    rsi   = ta.momentum.RSIIndicator(close, window=14).rsi()
    ema20 = ta.trend.EMAIndicator(close, window=20).ema_indicator()
    ema50 = ta.trend.EMAIndicator(close, window=50).ema_indicator()
    macd  = ta.trend.MACD(close)
    bb    = ta.volatility.BollingerBands(close, window=20, window_dev=2)

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

    # RSI tekshiruvi
    if last_rsi < 35:
        buy_score += 2
        reasons.append(f"RSI oversold ({last_rsi:.1f})")
    elif last_rsi > 65:
        sell_score += 2
        reasons.append(f"RSI overbought ({last_rsi:.1f})")

    # EMA kesishuvi
    if last_ema20 > last_ema50:
        buy_score += 1
        reasons.append("EMA20 > EMA50 (uptrend)")
    else:
        sell_score += 1
        reasons.append("EMA20 < EMA50 (downtrend)")

    # MACD
    if macd_line > signal_line:
        buy_score += 1
        reasons.append("MACD bullish")
    else:
        sell_score += 1
        reasons.append("MACD bearish")

    # Bollinger Bands
    if last_close <= bb_lower:
        buy_score += 2
        reasons.append("Narx BB pastki chegarasida")
    elif last_close >= bb_upper:
        sell_score += 2
        reasons.append("Narx BB yuqori chegarasida")

    # Signal qaror
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
    """
    Fair Value Gap (FVG) larni topadi.
    Qaytaradi: [{'type': 'bullish'|'bearish', 'top': float, 'bottom': float, 'time': str}]
    """
    fvgs = []
    if len(df) < 3:
        return fvgs

    for i in range(1, len(df) - 1):
        prev_high  = df['high'].iloc[i - 1]
        prev_low   = df['low'].iloc[i - 1]
        curr_high  = df['high'].iloc[i]
        curr_low   = df['low'].iloc[i]
        next_high  = df['high'].iloc[i + 1]
        next_low   = df['low'].iloc[i + 1]
        time_label = str(df.index[i])

        # Bullish FVG: avvalgi sham yuqori < keyingi sham past
        if prev_high < next_low:
            fvgs.append({
                'type':   'bullish',
                'top':    next_low,
                'bottom': prev_high,
                'time':   time_label,
            })

        # Bearish FVG: avvalgi sham past > keyingi sham yuqori
        elif prev_low > next_high:
            fvgs.append({
                'type':   'bearish',
                'top':    prev_low,
                'bottom': next_high,
                'time':   time_label,
            })

    # Faqat oxirgi 3 ta FVG qaytariladi
    return fvgs[-3:] if fvgs else []

# ==================== XABAR FORMATLASH ====================
def format_signal_message(analysis: dict, fvgs: list) -> str:
    signal = analysis['signal']

    if signal == 'BUY':
        emoji  = "🟢"
        action = "LONG / BUY"
    elif signal == 'SELL':
        emoji  = "🔴"
        action = "SHORT / SELL"
    else:
        return ""   # WAIT signali kanalga yubormaydi

    price     = analysis['price']
    tp1       = price * 1.005 if signal == 'BUY' else price * 0.995
    tp2       = price * 1.010 if signal == 'BUY' else price * 0.990
    sl        = price * 0.995 if signal == 'BUY' else price * 1.005

    fvg_text = ""
    if fvgs:
        fvg_lines = []
        for f in fvgs:
            fvg_lines.append(
                f"  • {f['type'].upper()} FVG: {f['bottom']:.2f} – {f['top']:.2f}"
            )
        fvg_text = "\n\n📦 *Fair Value Gaps:*\n" + "\n".join(fvg_lines)

    msg = (
        f"{emoji} *{SYMBOL} — {action} SIGNAL*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💰 *Narx:* `{price:.2f}`\n"
        f"🎯 *TP1:* `{tp1:.2f}`\n"
        f"🎯 *TP2:* `{tp2:.2f}`\n"
        f"🛑 *SL:*  `{sl:.2f}`\n\n"
        f"📊 *RSI:* `{analysis['rsi']:.1f}` | "
        f"*EMA20:* `{analysis['ema20']:.2f}` | "
        f"*EMA50:* `{analysis['ema50']:.2f}`\n\n"
        f"📝 *Sabab:* _{analysis['reason']}_"
        f"{fvg_text}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⏱ Timeframe: `{TIMEFRAME}`"
    )
    return msg

# ==================== ASOSIY LOOP ====================
async def loop(app):
    """Har WAIT_TIME soniyada bozorni tahlil qilib signal yuboradi."""
    logger.info("Tahlil loop boshlandi...")
    while True:
        try:
            df       = get_ohlcv(SYMBOL, TIMEFRAME, CANDLE_LIMIT)
            analysis = elite_analyser(df)
            fvgs     = find_fvg(df)
            msg      = format_signal_message(analysis, fvgs)

            if msg:
                await app.bot.send_message(
                    chat_id    = CHANNEL_ID,
                    text       = msg,
                    parse_mode = ParseMode.MARKDOWN,
                )
                logger.info(f"Signal yuborildi: {analysis['signal']} @ {analysis['price']:.2f}")
            else:
                logger.info(f"Signal yo'q (WAIT). RSI={analysis['rsi']:.1f}")

        except Exception as e:
            logger.error(f"Loop xatosi: {e}")

        await asyncio.sleep(WAIT_TIME)

# ==================== TELEGRAM BUYRUQLARI ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *XAU/USDT Tahlil Boti*\n\n"
        "Bot faol! U har 20 soniyada bozorni tahlil qilib,\n"
        f"kanalga signal yuboradi: {CHANNEL_ID}\n\n"
        "📊 Indikatorlar: RSI, EMA, MACD, Bollinger Bands, FVG",
        parse_mode=ParseMode.MARKDOWN,
    )

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Joriy bozor holati."""
    df       = get_ohlcv(SYMBOL, TIMEFRAME, 10)
    analysis = elite_analyser(df)
    await update.message.reply_text(
        f"📊 *Joriy holat — {SYMBOL}*\n"
        f"Narx: `{analysis['price']:.2f}`\n"
        f"Signal: `{analysis['signal']}`\n"
        f"RSI: `{analysis['rsi']:.1f}`",
        parse_mode=ParseMode.MARKDOWN,
    )

# ==================== MAIN ====================
async def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start",  start))
    app.add_handler(CommandHandler("status", status))

    await app.initialize()
    await app.start()
    logger.info("Bot ishga tushdi!")

    await asyncio.gather(
        app.updater.start_polling(drop_pending_updates=True),
        loop(app),
    )

if __name__ == "__main__":
    keep_alive()
    logger.info("Web-server ishga tushdi!")
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot to'xtatildi.")
