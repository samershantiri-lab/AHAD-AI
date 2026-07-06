import os
import telebot
import requests
import pandas as pd
import numpy as np
from flask import Flask
from threading import Thread
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator, MACD
from ta.volatility import AverageTrueRange


# =========================
# AHAD AI v5.7
# SMART MONEY EDITION
# =========================


TOKEN = os.environ.get("BOT_TOKEN")

bot = telebot.TeleBot(TOKEN)

app = Flask(__name__)


# =========================
# KEEP RENDER ONLINE
# =========================

@app.route("/")
def home():
    return "🚀 AHAD AI v5.7 SMART MONEY ONLINE"


def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(
        host="0.0.0.0",
        port=port
    )


def keep_alive():
    t = Thread(target=run_web)
    t.start()


# =========================
# MARKET DATA
# =========================

def get_data(symbol):

    url = "https://api.binance.com/api/v3/klines"

    params = {
        "symbol": symbol,
        "interval": "15m",
        "limit": 120
    }

    try:
        r = requests.get(
            url,
            params=params,
            timeout=10
        )

        data = r.json()

        df = pd.DataFrame(
            data,
            columns=[
                "time",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "x1",
                "x2",
                "x3",
                "x4",
                "x5",
                "x6"
            ]
        )

        df = df[
            [
                "open",
                "high",
                "low",
                "close",
                "volume"
            ]
        ]

        df = df.astype(float)

        return df

    except:
        return None


# =========================
# INDICATORS ENGINE
# =========================

def analyze(symbol):

    df = get_data(symbol)

    if df is None:
        return None

    close = df["close"]

    rsi = RSIIndicator(close).rsi().iloc[-1]

    ema50 = EMAIndicator(
        close,
        window=50
    ).ema_indicator().iloc[-1]

    macd = MACD(close)

    macd_value = (
        macd.macd().iloc[-1]
        -
        macd.macd_signal().iloc[-1]
    )

    atr = AverageTrueRange(
        df["high"],
        df["low"],
        df["close"]
    ).average_true_range().iloc[-1]
