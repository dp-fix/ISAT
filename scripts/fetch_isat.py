#!/usr/bin/env python3
"""
fetch_isat.py — Versi resilient
Mengambil data ISAT.JK via Yahoo Finance Chart API (direct HTTP)
dengan retry logic, user-agent rotation, dan fallback data.
"""

import json
import os
import sys
import time
import random
from datetime import datetime, timedelta
from pathlib import Path

import pytz

# ──────────────────────────────────────────────
# Konfigurasi Strategi
# ──────────────────────────────────────────────
STRATEGY = {
    "symbol": "ISAT.JK",
    "company": "PT Indosat Tbk",
    "total_portfolio": 122_030_313,
    "max_allocation": 100_000_000,
    "ultra_reserve": 22_030_313,
    "reserve_instrument": "RDPU Bahana Likuid Syariah Kelas G",
    "horizon": "Position Trading (3-12 bulan)",
    "target_win_rate": "55-65%",
    "method": "Averaging Down Terukur (Tanpa Stop Loss)",
    "target_conservative": 1650,
    "target_consensus_min": 2580,
    "target_consensus_max": 3200,
    "dividend_per_share_conservative": 111,
    "dividend_per_share_optimistic": 152,
    "dividend_window": "Mei-Juni 2027 (tahun buku 2026)",
    "termins": [
        {
            "id": 1,
            "label": "Termin 1 - Gap Down Basing",
            "target_price": 1250,
            "allocation": 20_000_000,
            "rationale": "Antisipasi pembukaan gap down. Eksekusi setelah panik mereda (>=09.30) dan terbentuk lantai harga.",
            "distance_pct": None
        },
        {
            "id": 2,
            "label": "Termin 2 - Psikologis 1200",
            "target_price": 1180,
            "allocation": 25_000_000,
            "rationale": "Jarak -5,6% di bawah Rp1.200 untuk memangkas avg secara signifikan.",
            "distance_pct": -5.6
        },
        {
            "id": 3,
            "label": "Termin 3 - Diskon Ekstrem",
            "target_price": 1115,
            "allocation": 25_000_000,
            "rationale": "Menyerap diskon valuasi PER < 5,5x. Jarak -5,5% dari T2.",
            "distance_pct": -5.5
        },
        {
            "id": 4,
            "label": "Termin 4 - Benteng Akhir",
            "target_price": 1050,
            "allocation": 30_000_000,
            "rationale": "Akumulasi terbesar (30%). Mengunci avg di ~Rp1.132 (880 lot total).",
            "distance_pct": -5.8
        }
    ]
}

# User-Agent pool untuk rotasi
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0",
]


# ──────────────────────────────────────────────
# Fetch Data via Yahoo Finance Chart API (Direct)
# ──────────────────────────────────────────────
def fetch_yahoo_chart(symbol: str, period: str = "6mo", interval: str = "1d",
                      max_retries: int = 3) -> dict | None:
    """
    Hit Yahoo Finance v8 chart API directly with proper headers.
    Returns the raw JSON response or None on failure.
    """
    try:
        import requests
    except ImportError:
        print("Installing requests...", flush=True)
        os.system("pip install requests")
        import requests

    period_map = {"1mo": "1mo", "3mo": "3mo", "6mo": "6mo", "1y": "1y", "2y": "2y"}
    range_val = period_map.get(period, "6mo")

    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    params = {
        "range": range_val,
        "interval": interval,
        "includePrePost": "false",
        "events": "",
    }

    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": "https://finance.yahoo.com",
        "Referer": "https://finance.yahoo.com/",
    }

    for attempt in range(1, max_retries + 1):
        try:
            print(f"  Attempt {attempt}/{max_retries}...", flush=True)
            resp = requests.get(url, params=params, headers=headers, timeout=15)

            if resp.status_code == 200:
                data = resp.json()
                if "chart" in data and "result" in data["chart"]:
                    results = data["chart"]["result"]
                    if results and len(results) > 0:
                        return results[0]
                print(f"  Response OK but no chart data. Keys: {list(data.get('chart', {}).keys())}", flush=True)
            elif resp.status_code == 429:
                print(f"  Rate limited (429). Waiting...", flush=True)
            else:
                print(f"  HTTP {resp.status_code}: {resp.text[:200]}", flush=True)

        except Exception as e:
            print(f"  Request error: {e}", flush=True)

        if attempt < max_retries:
            wait = 2 * attempt + random.uniform(0.5, 1.5)
            print(f"  Waiting {wait:.1f}s before retry...", flush=True)
            time.sleep(wait)

    return None


# ──────────────────────────────────────────────
# Parse Chart Response to DataFrame-like structure
# ──────────────────────────────────────────────
def parse_chart_result(result: dict) -> list[dict]:
    """Convert Yahoo chart API result to list of OHLCV dicts."""
    timestamps = result.get("timestamp", [])
    indicators = result.get("indicators", {})
    quote = indicators.get("quote", [{}])[0]

    opens = quote.get("open", [])
    highs = quote.get("high", [])
    lows = quote.get("low", [])
    closes = quote.get("close", [])
    volumes = quote.get("volume", [])

    rows = []
    for i in range(len(timestamps)):
        c = closes[i] if i < len(closes) else None
        if c is None:
            continue  # skip incomplete rows
        rows.append({
            "Date": datetime.utcfromtimestamp(timestamps[i]),
            "Open": opens[i] if i < len(opens) else c,
            "High": highs[i] if i < len(highs) else c,
            "Low": lows[i] if i < len(lows) else c,
            "Close": c,
            "Volume": int(volumes[i]) if i < len(volumes) and volumes[i] is not None else 0,
        })

    return rows


# ──────────────────────────────────────────────
# Indikator Teknikal
# ──────────────────────────────────────────────
def calculate_rsi(closes: list[float], period: int = 14) -> float | None:
    """RSI dengan Wilder's smoothing. Return latest RSI value."""
    if len(closes) < period + 1:
        return None

    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(d, 0) for d in deltas]
    losses = [max(-d, 0) for d in deltas]

    # Initial average
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    # Wilder smoothing for remaining
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def compute_indicators(rows: list[dict]) -> dict:
    """Hitung MA20, MA50, RSI14, Volume MA20 dari list OHLCV."""
    closes = [r["Close"] for r in rows]
    volumes = [r["Volume"] for r in rows]

    n = len(rows)
    latest = rows[-1]
    prev = rows[-2] if n > 1 else latest

    # MA20
    ma20 = None
    if n >= 20:
        ma20 = sum(closes[-20:]) / 20

    # MA50
    ma50 = None
    if n >= 50:
        ma50 = sum(closes[-50:]) / 50

    # RSI14
    rsi14 = calculate_rsi(closes, 14)

    # Volume MA20
    vol_ma20 = None
    if n >= 20:
        vol_ma20 = sum(volumes[-20:]) / 20

    latest_vol = latest["Volume"]
    vol_ratio = (latest_vol / vol_ma20) if vol_ma20 and vol_ma20 > 0 else 0

    return {
        "ma20": round(ma20, 2) if ma20 is not None else None,
        "ma50": round(ma50, 2) if ma50 is not None else None,
        "rsi14": round(rsi14, 2) if rsi14 is not None else None,
        "vol_ma20": int(vol_ma20) if vol_ma20 is not None else None,
        "latest_volume": int(latest_vol),
        "vol_ratio": round(vol_ratio, 3),
        "prev_close": round(prev["Close"], 2),
        "day_high": round(latest["High"], 2),
        "day_low": round(latest["Low"], 2),
        "day_open": round(latest["Open"], 2),
    }


# ──────────────────────────────────────────────
# Penentu Fase Pasar
# ──────────────────────────────────────────────
def determine_phase(price: float, rsi: float | None, ma20: float | None,
                    ma50: float | None, vol_ratio: float, prev_close: float) -> dict:
    change_pct = ((price - prev_close) / prev_close * 100) if prev_close else 0

    if change_pct <= -7 or (rsi is not None and rsi < 25 and ma20 and price < ma20 * 0.95):
        return {
            "phase": "FALLING_KNIFE",
            "phase_label": "⚠️ FALLING KNIFE / ARB RISK",
            "phase_color": "#ff4757",
            "description": "Penurunan tajam terdeteksi. JANGAN menangkap pisau jatuh. Tunggu konfirmasi basing dan volume mengering sebelum entry."
        }

    if price <= 1050:
        return {
            "phase": "DEEP_VALUE",
            "phase_label": "💎 DEEP VALUE ZONE",
            "phase_color": "#a855f7",
            "description": "Harga masuk zona Termin 4 (Rp1.050). Valuasi PER < 5,5x sangat diskontif. Eksekusi Termin 4 jika checklist 3 poin terpenuhi."
        }

    if price <= 1115:
        return {
            "phase": "EXTREME_DISCOUNT",
            "phase_label": "🔥 EXTREME DISCOUNT",
            "phase_color": "#f97316",
            "description": "Harga di zona Termin 3 (Rp1.115). Diskon ekstrem dari harga wajar. Siapkan dana Termin 3 & 4."
        }

    if price <= 1250:
        return {
            "phase": "ACCUMULATION_ZONE",
            "phase_label": "🎯 ACCUMULATION ZONE",
            "phase_color": "#00d4aa",
            "description": "Harga masuk zona akumulasi Termin 1-2. Pantau konfirmasi pembalikan dan checklist 3 poin sebelum Instant Redeem."
        }

    if price > 1400:
        return {
            "phase": "RECLAIM_BULLISH",
            "phase_label": "🚀 RECLAIM BULLISH",
            "phase_color": "#22c55e",
            "description": "Harga telah reclaim di atas Rp1.400. Tren bullish terkonfirmasi. Hold posisi, target konservatif Rp1.650."
        }

    if ma20 and price < ma20 and rsi is not None and rsi < 40:
        return {
            "phase": "WEAKNESS",
            "phase_label": "📉 WEAKNESS",
            "phase_color": "#eab308",
            "description": "Harga di bawah MA20 dengan momentum melemah (RSI < 40). Wait and see, belum masuk zona akumulasi."
        }

    return {
        "phase": "CONSOLIDATION",
        "phase_label": "⏳ CONSOLIDATION",
        "phase_color": "#64748b",
        "description": "Fase konsolidasi. Harga bergerak sideways. Sabar menunggu harga masuk zona akumulasi (<=Rp1.250)."
    }


# ──────────────────────────────────────────────
# Deteksi Akumulasi Bandar
# ──────────────────────────────────────────────
def detect_accumulation(rows: list[dict]) -> dict:
    if len(rows) < 5:
        return {"signal": "UNKNOWN", "score": 0, "note": "Data tidak cukup."}

    last5 = rows[-5:]
    price_change = (last5[-1]["Close"] - last5[0]["Close"]) / last5[0]["Close"] * 100
    avg_vol_5 = sum(r["Volume"] for r in last5) / 5

    # Vol MA20
    if len(rows) >= 20:
        prev_vol_ma = sum(r["Volume"] for r in rows[-21:-1]) / 20
    else:
        prev_vol_ma = avg_vol_5

    vol_spike = (avg_vol_5 / prev_vol_ma) if prev_vol_ma and prev_vol_ma > 0 else 1

    if vol_spike > 1.3 and abs(price_change) < 3:
        return {
            "signal": "ACCUMULATION_DETECTED",
            "score": min(int(vol_spike * 25), 100),
            "note": f"Volume 5-hari {vol_spike:.1f}x rata-rata tapi harga hanya berubah {price_change:+.1f}%. Indikasi bandar sedang menyerap supply."
        }

    if vol_spike > 1.3 and price_change < -5:
        return {
            "signal": "DISTRIBUTION",
            "score": 0,
            "note": f"Volume tinggi ({vol_spike:.1f}x) disertai penurunan {price_change:.1f}%. Indikasi distribusi. Hindari entry."
        }

    if vol_spike < 0.7 and price_change > -3:
        return {
            "signal": "SELLING_DRYING_UP",
            "score": 60,
            "note": f"Volume menyusut ({vol_spike:.1f}x MA20) dengan harga stabil. Supply mulai kering — potensi reversal."
        }

    return {
        "signal": "NEUTRAL",
        "score": 30,
        "note": "Pola volume-netral. Belum ada sinyal akumulasi/distribusi jelas."
    }


# ──────────────────────────────────────────────
# Fallback Data (jika Yahoo Finance gagal total)
# ──────────────────────────────────────────────
def generate_fallback_data() -> dict:
    """Generate fallback JSON agar dashboard tetap tampil saat API gagal."""
    print("⚠️  Menggunakan FALLBACK DATA (API gagal). Dashboard tetap berfungsi.", flush=True)
    wib = pytz.timezone("Asia/Jakarta")
    now_wib = datetime.now(wib)

    # Data terakhir yang diketahui (update manual jika perlu)
    fallback_price = 1310
    fallback_prev = 1430

    termins_with_lots = []
    for t in STRATEGY["termins"]:
        lots = int(t["allocation"] / (t["target_price"] * 100))
        actual_cost = lots * 100 * t["target_price"]
        termins_with_lots.append({
            **t,
            "lots": lots,
            "shares": lots * 100,
            "actual_cost": actual_cost,
            "remaining_cash": t["allocation"] - actual_cost
        })

    return {
        "timestamp": now_wib.isoformat(),
        "timestamp_unix": int(now_wib.timestamp()),
        "market_status": "CLOSED" if now_wib.weekday() >= 5 else "UNKNOWN",
        "symbol": STRATEGY["symbol"],
        "company": STRATEGY["company"],
        "current_price": fallback_price,
        "prev_close": fallback_prev,
        "change": fallback_price - fallback_prev,
        "change_pct": round((fallback_price - fallback_prev) / fallback_prev * 100, 2),
        "indicators": {
            "ma20": 1385,
            "ma50": 1420,
            "rsi14": 28,
            "vol_ma20": 2850000,
            "latest_volume": 900000,
            "vol_ratio": 0.32,
            "prev_close": fallback_prev,
            "day_high": 1340,
            "day_low": 1310,
            "day_open": 1340
        },
        "phase": {
            "phase": "ACCUMULATION_ZONE",
            "phase_label": "🎯 ACCUMULATION ZONE",
            "phase_color": "#00d4aa",
            "description": "Harga masuk zona akumulasi Termin 1-2. Pantau konfirmasi pembalikan dan checklist 3 poin sebelum Instant Redeem."
        },
        "accumulation": {
            "signal": "SELLING_DRYING_UP",
            "score": 60,
            "note": "Volume menyusut (0.32x MA20) dengan harga stabil di support. Supply mulai kering — potensi reversal."
        },
        "strategy": {**STRATEGY, "termins": termins_with_lots},
        "checklist_reminder": {
            "point_1": "Harga tidak terkunci ARB & bergerak di atas Open setelah 09.30",
            "point_2": "Bid tebal (>30.000 lot) dan bertahan >15 menit",
            "point_3": "Dominasi Haka (beli di Offer > jual di Bid)"
        },
        "is_fallback": True,
        "fallback_note": "Data ini adalah fallback karena Yahoo Finance API tidak merespons. Harga mungkin tidak akurat."
    }


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────
def main():
    wib = pytz.timezone("Asia/Jakarta")
    now_wib = datetime.now(wib)
    print(f"[{now_wib.strftime('%Y-%m-%d %H:%M:%S WIB')}] Fetching ISAT.JK data...", flush=True)

    rows = None

    # ── Metode 1: Direct Yahoo Chart API ──
    print("→ Metode 1: Yahoo Finance Chart API (direct HTTP)...", flush=True)
    result = fetch_yahoo_chart("ISAT.JK", period="6mo", interval="1d", max_retries=3)

    if result:
        rows = parse_chart_result(result)
        print(f"  ✅ Berhasil: {len(rows)} baris data", flush=True)
    else:
        print("  ❌ Yahoo Chart API gagal.", flush=True)

    # ── Metode 2: yfinance sebagai fallback ──
    if rows is None or len(rows) < 20:
        print("→ Metode 2: yfinance library...", flush=True)
        try:
            import yfinance as yf
            ticker = yf.Ticker("ISAT.JK")
            hist = ticker.history(period="6mo", interval="1d")
            if not hist.empty and len(hist) >= 20:
                rows = []
                for idx, row in hist.iterrows():
                    rows.append({
                        "Date": idx.to_pydatetime() if hasattr(idx, 'to_pydatetime') else idx,
                        "Open": float(row["Open"]),
                        "High": float(row["High"]),
                        "Low": float(row["Low"]),
                        "Close": float(row["Close"]),
                        "Volume": int(row["Volume"]),
                    })
                print(f"  ✅ yfinance berhasil: {len(rows)} baris", flush=True)
            else:
                print("  ❌ yfinance: data tidak cukup.", flush=True)
        except Exception as e:
            print(f"  ❌ yfinance error: {e}", flush=True)

    # ── Build Output ──
    if rows and len(rows) >= 20:
        indicators = compute_indicators(rows)
        current_price = round(rows[-1]["Close"], 2)
        prev_close = indicators["prev_close"]
        change = round(current_price - prev_close, 2)
        change_pct = round((change / prev_close * 100), 2) if prev_close else 0

        phase_info = determine_phase(
            price=current_price,
            rsi=indicators["rsi14"],
            ma20=indicators["ma20"],
            ma50=indicators["ma50"],
            vol_ratio=indicators["vol_ratio"],
            prev_close=prev_close
        )
        accumulation = detect_accumulation(rows)
        is_fallback = False
    else:
        # Gunakan fallback
        output = generate_fallback_data()
        save_output(output)
        return

    # Hitung lot per termin
    termins_with_lots = []
    for t in STRATEGY["termins"]:
        lots = int(t["allocation"] / (t["target_price"] * 100))
        actual_cost = lots * 100 * t["target_price"]
        termins_with_lots.append({
            **t,
            "lots": lots,
            "shares": lots * 100,
            "actual_cost": actual_cost,
            "remaining_cash": t["allocation"] - actual_cost
        })

    output = {
        "timestamp": now_wib.isoformat(),
        "timestamp_unix": int(now_wib.timestamp()),
        "market_status": "CLOSED" if now_wib.weekday() >= 5 else "OPEN",
        "symbol": STRATEGY["symbol"],
        "company": STRATEGY["company"],
        "current_price": current_price,
        "prev_close": prev_close,
        "change": change,
        "change_pct": change_pct,
        "indicators": indicators,
        "phase": phase_info,
        "accumulation": accumulation,
        "strategy": {**STRATEGY, "termins": termins_with_lots},
        "checklist_reminder": {
            "point_1": "Harga tidak terkunci ARB & bergerak di atas Open setelah 09.30",
            "point_2": "Bid tebal (>30.000 lot) dan bertahan >15 menit",
            "point_3": "Dominasi Haka (beli di Offer > jual di Bid)"
        },
        "is_fallback": False
    }

    save_output(output)


def save_output(output: dict):
    data_dir = Path(__file__).resolve().parent.parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    output_path = data_dir / "isat.json"

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n[OK] Data saved to {output_path}", flush=True)
    print(f"     Price: {output['current_price']} ({output['change_pct']:+.2f}%)", flush=True)
    print(f"     Phase: {output['phase']['phase_label']}", flush=True)
    print(f"     Accumulation: {output['accumulation']['signal']}", flush=True)
    if output.get("is_fallback"):
        print(f"     ⚠️  FALLBACK MODE — data mungkin tidak akurat", flush=True)


if __name__ == "__main__":
    main()
