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
# Render botni "Web Service" sifatida tanishi va o'chirib qo'ymasligi uchun kerak
app_flask = Flask('')

@app_flask.route('/')
def home():
    return "✅ Bot tirik va ishlamoqda!"

def run_flask():
    # Render portni avtomat beradi, agar bo'lmasa 8080 ishlatadi
    port = int(os.environ.get("PORT", 8080))
    app_flask.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_flask)
    t.start()

# ==================== KONFIGURATSIYA ====================
# Yangi tokenni ishlatamiz
TELEGRAM_TOKEN = "8397450809:AAFtv0n6D1StMLmqeNb1EeKqHOnznVvcXpk"
CHANNEL_ID     = "@fhoveuss" 
SYMBOL         = "XAU/USDT" # MEXC va Bybit uchun universal format
WAIT_TIME      = 60 # Juda tez so'rov yuborish bloklanishga olib keladi

# Renderda Bybit bloklangan bo'lsa MEXC ga o'zgartiring
exchange = ccxt.mexc({'options': {'defaultType': 'spot'}, 'enableRateLimit': True})
trade_log = {"active": False, "dir": None, "entry": 0, "tp": 0, "sl": 0}

# ==================== 🧠 ELITE ANALIZ (SMC/ICT) ====================

def find_fvg(df):
    c1 = df.iloc[-3]
    c3 = df.iloc[-1]
    if c3['low'] > c1['high']:
        return "BULLISH_FVG", (c1['high'] + c3['low']) / 2
    if c3['high'] < c1['low']:
        return "BEARISH_FVG", (c1['low'] + c3['high']) / 2
    return None, 0

def get_market_bias(df):
    ema200 = ta.trend.EMAIndicator(df['close'], window=200).ema_indicator().iloc[-1]
    price = df.iloc[-1]['close']
    return "BULLISH" if price > ema200 else "BEARISH"

async def elite_analyser():
    global trade_log
    try:
        ohlcv = exchange.fetch_ohlcv(SYMBOL, timeframe='1m', limit=150)
        df = pd.DataFrame(ohlcv, columns=['ts', 'open', 'high', 'low', 'close', 'volume'])
        price = df.iloc[-1]['close']

        if trade_log["active"]:
            win = (trade_log["dir"] == "BUY" and price >= trade_log["tp"]) or \
                  (trade_log["dir"] == "SELL" and price <= trade_log["tp"])
            loss = (trade_log["dir"] == "BUY" and price <= trade_log["sl"]) or \
                   (trade_log["dir"] == "SELL" and price >= trade_log["sl"])
            
            if win or loss:
                res = "💎 PROFIT (TP) URILDI! 📈" if win else "🛑 STOP LOSS URILDI. 📉"
                trade_log["active"] = False
                return f"📊 *YOPILGAN SAVDO:* {SYMBOL}\n━━━━━━━━━━━━━━\nNatija: {res}\nNarx: `{price}`"

        bias = get_market_bias(df)
        fvg_type, fvg_price = find_fvg(df)
        rsi = ta.momentum.RSIIndicator(df['close']).rsi().iloc[-1]
        recent_high = df['high'].tail(15).max()
        recent_low = df['low'].tail(15).min()
        
        confs = []
        final_dir = None

        if bias == "BULLISH":
            if fvg_type == "BULLISH_FVG": confs.append("⚡️ Fair Value Gap")
            if price > df['high'].iloc[-2]: confs.append("🏛 Structure Shift")
            if rsi < 50: confs.append("📊 RSI Optimal")
            if df['volume'].iloc[-1] > df['volume'].rolling(10).mean().iloc[-1] * 1.3: confs.append("🐋 Volume Spike")
            if len(confs) >= 3: final_dir = "BUY"

        if not final_dir and bias == "BEARISH":
            if fvg_type == "BEARISH_FVG": confs.append("⚡️ Fair Value Gap")
            if price < df['low'].iloc[-2]: confs.append("🏛 Structure Shift")
            if rsi > 50: confs.append("📊 RSI Optimal")
            if df['volume'].iloc[-1] > df['volume'].rolling(10).mean().iloc[-1] * 1.3: confs.append("🐋 Volume Spike")
            if len(confs) >= 3: final_dir = "SELL"

        if final_dir and not trade_log["active"]:
            atr = ta.volatility.AverageTrueRange(df['high'], df['low'], df['close']).average_true_range().iloc[-1]
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
                f"📝 *Asoslar:* {len(confs)}/4\n"
                f"⚠️ *Risk/Reward:* 1:3.0"
            )
            return msg
        return None
    except Exception as e:
        print(f"Xato: {e}")
        return None

# ==================== 📩 BOT BOSHQARUVI ====================
async def loop(app):
    print("Snayper Monitoring boshlandi...")
    while True:
        try:
            res = await elite_analyser()
            if res:
                await app.bot.send_message(chat_id=CHANNEL_ID, text=res, parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            print(f"Loop xatosi: {e}")
        await asyncio.sleep(WAIT_TIME)

async def main():
    # drop_pending_updates=True Conflict xatosini oldini oladi
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    await app.initialize()
    await app.start()
    
    # Ham pollingni, ham tahlil loopini birga ishga tushiramiz
    await asyncio.gather(
        app.updater.start_polling(drop_pending_updates=True),
        loop(app)
    )

if __name__ == "__main__":
    keep_alive() # Veb-serverni alohida thread'da yoqish
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
    
