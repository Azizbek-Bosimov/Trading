import asyncio
import ccxt
import pandas as pd
import ta
import sys
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from telegram.constants import ParseMode

# ==================== KONFIGURATSIYA ====================
TELEGRAM_TOKEN = "8397450809:AAHMf2JdIlnH4yP3kfaDDtuMRFtXD9Zcrys"
CHANNEL_ID     = "@fhoveuss" 
SYMBOL         = "XAUUSDT" 
WAIT_TIME      = 20 

exchange = ccxt.bybit({'options': {'defaultType': 'linear'}, 'enableRateLimit': True})
trade_log = {"active": False, "dir": None, "entry": 0, "tp": 0, "sl": 0}

# ==================== 🧠 ELITE ANALIZ (SMC/ICT) ====================

def find_fvg(df):
    """Fair Value Gap (FVG) - Narxdagi bo'shliqni aniqlash"""
    # Oxirgi 3 ta shamni tahlil qilamiz
    c1 = df.iloc[-3] # Birinchi sham
    c3 = df.iloc[-1] # Uchinchi sham
    
    # Bullish FVG (Xarid bo'shlig'i)
    if c3['low'] > c1['high']:
        return "BULLISH_FVG", (c1['high'] + c3['low']) / 2
    # Bearish FVG (Sotuv bo'shlig'i)
    if c3['high'] < c1['low']:
        return "BEARISH_FVG", (c1['low'] + c3['high']) / 2
    return None, 0

def get_market_bias(df):
    """Bozor yo'nalishini (Bias) aniqlash"""
    ema200 = ta.trend.EMAIndicator(df['close'], window=200).ema_indicator().iloc[-1]
    price = df.iloc[-1]['close']
    return "BULLISH" if price > ema200 else "BEARISH"

async def elite_analyser():
    global trade_log
    try:
        ohlcv = exchange.fetch_ohlcv(SYMBOL, timeframe='1m', limit=150)
        df = pd.DataFrame(ohlcv, columns=['ts', 'open', 'high', 'low', 'close', 'volume'])
        price = df.iloc[-1]['close']

        # 1. MONITORING (Natijani tekshirish)
        if trade_log["active"]:
            win = (trade_log["dir"] == "BUY" and price >= trade_log["tp"]) or \
                  (trade_log["dir"] == "SELL" and price <= trade_log["tp"])
            loss = (trade_log["dir"] == "BUY" and price <= trade_log["sl"]) or \
                   (trade_log["dir"] == "SELL" and price >= trade_log["sl"])
            
            if win or loss:
                res = "💎 PROFIT (TP) URILDI! 📈" if win else "🛑 STOP LOSS URILDI. 📉"
                trade_log["active"] = False
                return f"📊 *YOPILGAN SAVDO:* {SYMBOL}\n━━━━━━━━━━━━━━\nNatija: {res}\nNarx: `{price}`"

        # 2. STRUKTURAVIY TAHLIL
        bias = get_market_bias(df)
        fvg_type, fvg_price = find_fvg(df)
        rsi = ta.momentum.RSIIndicator(df['close']).rsi().iloc[-1]
        
        # Bozor strukturasi (Break of Structure - BOS)
        recent_high = df['high'].tail(15).max()
        recent_low = df['low'].tail(15).min()
        
        confs = []
        final_dir = None

        # --- PROFESSIONAL BUY LOGIKASI ---
        if bias == "BULLISH":
            if fvg_type == "BULLISH_FVG": confs.append("⚡️ Fair Value Gap (Imbalance) topildi")
            if price > df['high'].iloc[-2]: confs.append("🏛 Market Structure Shift (MSS)")
            if rsi < 50: confs.append("📊 Narx optimal hududda (RSI)")
            if df['volume'].iloc[-1] > df['volume'].rolling(10).mean().iloc[-1] * 1.5: confs.append("🐋 Yirik xajm (Institutional Flow)")
            
            if len(confs) >= 3: final_dir = "BUY"

        # --- PROFESSIONAL SELL LOGIKASI ---
        if not final_dir and bias == "BEARISH":
            if fvg_type == "BEARISH_FVG": confs.append("⚡️ Fair Value Gap (Imbalance) topildi")
            if price < df['low'].iloc[-2]: confs.append("🏛 Market Structure Shift (MSS)")
            if rsi > 50: confs.append("📊 Narx optimal hududda (RSI)")
            if df['volume'].iloc[-1] > df['volume'].rolling(10).mean().iloc[-1] * 1.5: confs.append("🐋 Yirik xajm (Institutional Flow)")
            
            if len(confs) >= 3: final_dir = "SELL"

        if final_dir and not trade_log["active"]:
            atr = ta.volatility.AverageTrueRange(df['high'], df['low'], df['close']).average_true_range().iloc[-1]
            
            # SL ni eng yaqin Liquidity nuqtasiga qo'yamiz (Snaypercha)
            sl = round(recent_low - (atr * 0.5) if final_dir == "BUY" else recent_high + (atr * 0.5), 2)
            tp = round(price + (abs(price - sl) * 3) if final_dir == "BUY" else price - (abs(price - sl) * 3), 2)
            
            trade_log.update({"active": True, "dir": final_dir, "entry": price, "tp": tp, "sl": sl})
            
            msg = (
                f"🎩 *ELITE TREYDER ANALIZI: {SYMBOL}*\n"
                f"━━━━━━━━━━━━━━\n"
                f"🔑 Signal: *{final_dir}*\n"
                f"💎 Kirish: `{price}`\n"
                f"🎯 Target (TP): `{tp}`\n"
                f"🛡 Stop (SL): `{sl}`\n"
                f"━━━━━━━━━━━━━━\n"
                f"📝 *Mantiqiy asoslar ({len(confs)}/4):*\n" + "\n".join([f"✅ {c}" for c in confs]) +
                f"\n━━━━━━━━━━━━━━\n"
                f"⚠️ *Risk/Reward:* 1:3.0"
            )
            return msg

        return None
    except Exception as e:
        return f"Xato: {e}"

# ==================== 📩 BOT BOSHQARUVI ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🧐 10 yillik tajribaga ega treyder analizni boshladi...")
    res = await elite_analyser()
    if res: await update.message.reply_text(res, parse_mode=ParseMode.MARKDOWN)
    else: await update.message.reply_text("⏳ Bozor hozircha 'shovqin' (noise). Sifatli kirish nuqtasi kutilmoqda.")

async def loop(app):
    while True:
        res = await elite_analyser()
        if res: await app.bot.send_message(chat_id=CHANNEL_ID, text=res, parse_mode=ParseMode.MARKDOWN)
        for i in range(WAIT_TIME, 0, -1):
            sys.stdout.write(f"\r🔍 Snayper Monitoring: {i}s  "); sys.stdout.flush()
            await asyncio.sleep(1)

async def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    await app.initialize(); await app.start()
    await asyncio.gather(app.updater.start_polling(), loop(app))

if __name__ == "__main__":
    try: asyncio.run(main())
    except: pass
