# ==============================
# 🤖 TELEGRAM COMMANDS
# ==============================

@bot.message_handler(commands=["start"])
def start(message):

    bot.reply_to(
        message,
"""
🚀 AHAD AI v6.1 ONLINE

🐋 Whale Engine ACTIVE
📊 Auto Futures Scanner ACTIVE
🟢 LONG Priority ACTIVE
⏱ 15m Smart Entry ACTIVE
🎯 TP / SL Engine ACTIVE
👀 Smart Watchlist ACTIVE

Send /scan
"""
    )


@bot.message_handler(commands=["scan"])
def scan(message):

    bot.reply_to(
        message,
        "🐋 AHAD AI scanning futures market...\n⏱ Timeframe: 15m"
    )


    results = []


    symbols = get_futures_symbols()


    for symbol in symbols[:200]:

        try:

            result = analyze(symbol)

            if result:

                results.append(result)


            time.sleep(0.03)


        except Exception as e:

            print(
                "Scan error:",
                symbol,
                e
            )


    results = sorted(
        results,
        key=lambda x: x["score"],
        reverse=True
    )


    strong = [
        x for x in results
        if x["score"] >= 75
    ][:3]


    almost = [
        x for x in results
        if 60 <= x["score"] < 75
    ][:5]


    # ==================
    # 🟢 STRONG SIGNALS
    # ==================

    if strong:

        for s in strong:

            msg = f"""
🐋 AHAD AI v6.1 SIGNAL 🚀

🟢 LONG SETUP CONFIRMED

🪙 Coin:
{s['coin']}

🎯 ENTRY:
{round(s['entry'],5)}

🛑 STOP LOSS:
{round(s['sl'],5)}

🎯 TP1:
{round(s['tp1'],5)}

🎯 TP2:
{round(s['tp2'],5)}

📊 RSI:
{round(s['rsi'],2)}

🐋 Whale Power:
{round(s['whale'],2)}X

🔥 AHAD SCORE:
{s['score']}/100


✅ Confirmation:
{chr(10).join(s['reasons'])}
"""


            bot.send_message(
                message.chat.id,
                msg
            )


    # ==================
    # 🟡 ALMOST READY
    # ==================

    elif almost:


        text = """
🟡 AHAD AI WATCHLIST

Almost ready setups 👀

Waiting confirmation:
"""


        for a in almost:


            text += f"""

🪙 {a['coin']}

🔥 Score:
{a['score']}/100

📊 RSI:
{round(a['rsi'],2)}

🐋 Whale:
{round(a['whale'],2)}X

⏱ 15m Setup forming

━━━━━━━━━━
"""


        bot.send_message(
            message.chat.id,
            text
        )



    # ==================
    # QUIET MARKET
    # ==================

    else:


        watch = results[:5]


        text = """
👀 AHAD WATCHLIST

😴 No sniper LONG yet 🛡

Closest coins:
"""


        if len(results) == 0:


            text += """

⚠️ Scanner ACTIVE
⚠️ Market quiet now

🐋 Waiting for whale movement...
"""


        else:


            for w in watch:


                text += f"""

🪙 {w['coin']}

🔥 Score:
{w['score']}/100

📊 RSI:
{round(w['rsi'],2)}

🐋 Whale:
{round(w['whale'],2)}X

👀 Monitoring...

━━━━━━━━━━
"""


        bot.send_message(
            message.chat.id,
            text
        )



# ==============================
# 🛡 TELEGRAM AUTO RECOVERY
# ==============================

def telegram_engine():

    while True:

        try:

            print(
                "🤖 Telegram Engine Running"
            )


            bot.infinity_polling(
                skip_pending=True,
                timeout=60
            )


        except Exception:


            print(
                traceback.format_exc()
            )


            print(
                "🔄 Restarting Telegram..."
            )


            time.sleep(5)



# ==============================
# 🚀 START SYSTEM
# ==============================

threading.Thread(
    target=run_web,
    daemon=True
).start()


threading.Thread(
    target=telegram_engine,
    daemon=True
).start()


print(
    "🔥 AHAD AI v6.1 FULL ONLINE"
)


while True:

    time.sleep(60)
