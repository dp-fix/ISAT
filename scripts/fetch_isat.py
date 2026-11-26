import json
from datetime import datetime, timezone, timedelta
import yfinance as yf
import pandas as pd

def calculate_rsi(series: pd.Series, period: int = 14) -> float:
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return round(float(rsi.iloc[-1]), 2)

def fetch_market_data():
    ticker = yf.Ticker("ISAT.JK")
    hist = ticker.history(period="3mo", interval="1d")
    
    if hist.empty:
        raise ValueError("Data ISAT.JK tidak ditemukan")

    latest = hist.iloc[-1]
    prev = hist.iloc[-2]
    
    close_price = float(latest["Close"])
    prev_close = float(prev["Close"])
    change_pct = round(((close_price - prev_close) / prev_close) * 100, 2)
    volume_lot = int(latest["Volume"] / 100)
    ma20 = round(float(hist["Close"].rolling(window=20).mean().iloc[-1]), 0)
    rsi14 = calculate_rsi(hist["Close"])

    wib = timezone(timedelta(hours=7))
    now_wib = datetime.now(wib).strftime("%d %b %Y, %H:%M WIB")

    payload = {
        "symbol": "IDX:ISAT",
        "last_updated": now_wib,
        "price": int(close_price),
        "prev_close": int(prev_close),
        "change_pct": change_pct,
        "volume_lot": volume_lot,
        "ma20": int(ma20),
        "rsi14": rsi14,
        "is_arb_zone": change_pct <= -6.5
    }

    with open("data/isat.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

if __name__ == "__main__":
    fetch_market_data()
