#!/usr/bin/env python3
"""
fetch_isat.py
Menarik data ISAT.JK via yfinance, menghitung indikator teknikal,
menentukan fase pasar, dan menyimpan ke data/isat.json.
"""

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import pytz
import yfinance as yf

# ──────────────────────────────────────────────
# Konfigurasi Strategi (Piramida Terbalik 4 Termin)
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
            "distance_pct": None  # dihitung dinamis
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


# ──────────────────────────────────────────────
# Indikator Teknikal
# ──────────────────────────────────────────────
def calculate_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    """RSI dengan Wilder's exponential smoothing."""
    delta = prices.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def compute_indicators(df: pd.DataFrame) -> dict:
    """Hitung MA20, MA50, RSI14, Volume MA20 dari dataframe historis."""
    df = df.copy()
    df["MA20"] = df["Close"].rolling(window=20).mean()
    df["MA50"] = df["Close"].rolling(window=50).mean()
    df["RSI14"] = calculate_rsi(df["Close"], 14)
    df["VolMA20"] = df["Volume"].rolling(window=20).mean()

    latest = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else latest

    vol_ma20 = latest["VolMA20"]
    vol_ratio = (latest["Volume"] / vol_ma20) if vol_ma20 and vol_ma20 > 0 else 0

    return {
        "ma20": round(float(latest["MA20"]), 2) if pd.notna(latest["MA20"]) else None,
        "ma50": round(float(latest["MA50"]), 2) if pd.notna(latest["MA50"]) else None,
        "rsi14": round(float(latest["RSI14"]), 2) if pd.notna(latest["RSI14"]) else None,
        "vol_ma20": int(vol_ma20) if pd.notna(vol_ma20) else None,
        "latest_volume": int(latest["Volume"]),
        "vol_ratio": round(float(vol_ratio), 3),
        "prev_close": round(float(prev["Close"]), 2),
        "day_high": round(float(latest["High"]), 2),
        "day_low": round(float(latest["Low"]), 2),
        "day_open": round(float(latest["Open"]), 2),
    }


# ──────────────────────────────────────────────
# Penentu Fase Pasar
# ──────────────────────────────────────────────
def determine_phase(price: float, rsi: float, ma20: float, ma50: float,
                    vol_ratio: float, prev_close: float) -> dict:
    """
    Fase pasar berdasarkan kombinasi harga, RSI, MA, dan volume.
    Return: {phase, phase_label, phase_color, description}
    """
    change_pct = ((price - prev_close) / prev_close * 100) if prev_close else 0

    # Falling Knife / ARB Risk
    if change_pct <= -7 or (rsi is not None and rsi < 25 and price < (ma20 or 9999) * 0.95):
        return {
            "phase": "FALLING_KNIFE",
            "phase_label": "⚠️ FALLING KNIFE / ARB RISK",
            "phase_color": "#ff4757",
            "description": (
                "Penurunan tajam terdeteksi. JANGAN menangkap pisau jatuh. "
                "Tunggu konfirmasi basing (lantai harga) dan volume mengering sebelum entry."
            )
        }

    # Deep Value (<=1050)
    if price <= 1050:
        return {
            "phase": "DEEP_VALUE",
            "phase_label": "💎 DEEP VALUE ZONE",
            "phase_color": "#a855f7",
            "description": (
                "Harga masuk zona Termin 4 (Rp1.050). Valuasi PER < 5,5x sangat diskontif. "
                "Eksekusi Termin 4 jika checklist 3 poin terpenuhi."
            )
        }

    # Extreme Discount (<=1115)
    if price <= 1115:
        return {
            "phase": "EXTREME_DISCOUNT",
            "phase_label": "🔥 EXTREME DISCOUNT",
            "phase_color": "#f97316",
            "description": (
                "Harga di zona Termin 3 (Rp1.115). Diskon ekstrem dari harga wajar. "
                "Siapkan dana Termin 3 & 4."
            )
        }

    # Accumulation Zone (<=1250)
    if price <= 1250:
        return {
            "phase": "ACCUMULATION_ZONE",
            "phase_label": "🎯 ACCUMULATION ZONE",
            "phase_color": "#00d4aa",
            "description": (
                "Harga masuk zona akumulasi Termin 1-2. Pantau konfirmasi pembalikan "
                "dan checklist 3 poin sebelum Instant Redeem."
            )
        }

    # Reclaim Bullish (>1400)
    if price > 1400:
        return {
            "phase": "RECLAIM_BULLISH",
            "phase_label": "🚀 RECLAIM BULLISH",
            "phase_color": "#22c55e",
            "description": (
                "Harga telah reclaim di atas Rp1.400. Tren bullish terkonfirmasi. "
                "Hold posisi, target konservatif Rp1.650."
            )
        }

    # Weakness
    if ma20 and price < ma20 and (rsi is not None and rsi < 40):
        return {
            "phase": "WEAKNESS",
            "phase_label": "📉 WEAKNESS",
            "phase_color": "#eab308",
            "description": (
                "Harga di bawah MA20 dengan momentum melemah (RSI < 40). "
                "Wait and see, belum masuk zona akumulasi."
            )
        }

    # Consolidation
    return {
        "phase": "CONSOLIDATION",
        "phase_label": "⏳ CONSOLIDATION",
        "phase_color": "#64748b",
        "description": (
            "Fase konsolidasi. Harga bergerak sideways. "
            "Sabar menunggu harga masuk zona akumulasi (<=Rp1.250)."
        )
    }


# ──────────────────────────────────────────────
# Deteksi Akumulasi Bandar (Bandar Accumulation Proxy)
# ──────────────────────────────────────────────
def detect_accumulation(df: pd.DataFrame) -> dict:
    """
    Proxy deteksi akumulasi: volume naik tapi harga stagnan/naik sedikit,
    atau volume selling drying up di area support.
    """
    if len(df) < 5:
        return {"signal": "UNKNOWN", "score": 0, "note": "Data tidak cukup."}

    last5 = df.tail(5)
    price_change = (last5["Close"].iloc[-1] - last5["Close"].iloc[0]) / last5["Close"].iloc[0] * 100
    avg_vol_5 = last5["Volume"].mean()
    prev_vol_ma = df["Volume"].rolling(20).mean().iloc[-6] if len(df) > 5 else avg_vol_5

    vol_spike = (avg_vol_5 / prev_vol_ma) if prev_vol_ma and prev_vol_ma > 0 else 1

    # Akumulasi: volume tinggi tapi harga tidak turun banyak (bandar menyerap)
    if vol_spike > 1.3 and abs(price_change) < 3:
        return {
            "signal": "ACCUMULATION_DETECTED",
            "score": min(int(vol_spike * 25), 100),
            "note": (
                f"Volume 5-hari {vol_spike:.1f}x rata-rata tapi harga hanya berubah "
                f"{price_change:+.1f}%. Indikasi bandar sedang menyerap supply."
            )
        }

    # Distribusi: volume tinggi dan harga turun tajam
    if vol_spike > 1.3 and price_change < -5:
        return {
            "signal": "DISTRIBUTION",
            "score": 0,
            "note": (
                f"Volume tinggi ({vol_spike:.1f}x) disertai penurunan {price_change:.1f}%. "
                f"Indikasi distribusi. Hindari entry."
            )
        }

    # Drying up (volume menyusut di support)
    if vol_spike < 0.7 and price_change > -3:
        return {
            "signal": "SELLING_DRYING_UP",
            "score": 60,
            "note": (
                f"Volume menyusut ({vol_spike:.1f}x MA20) dengan harga stabil. "
                f"Supply mulai kering — potensi reversal."
            )
        }

    return {
        "signal": "NEUTRAL",
        "score": 30,
        "note": "Pola volume-netral. Belum ada sinyal akumulasi/distribusi jelas."
    }


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────
def main():
    print(f"[{datetime.now()}] Fetching ISAT.JK data...")

    ticker = yf.Ticker("ISAT.JK")
    # Ambil 6 bulan data harian untuk cukup menghitung MA50
    hist = ticker.history(period="6mo", interval="1d")

    if hist.empty or len(hist) < 20:
        print("ERROR: Data tidak cukup dari yfinance.", file=sys.stderr)
        sys.exit(1)

    # Hitung indikator
    indicators = compute_indicators(hist)

    current_price = round(float(hist["Close"].iloc[-1]), 2)
    prev_close = indicators["prev_close"]
    change = round(current_price - prev_close, 2)
    change_pct = round((change / prev_close * 100), 2) if prev_close else 0

    # Fase pasar
    phase_info = determine_phase(
        price=current_price,
        rsi=indicators["rsi14"],
        ma20=indicators["ma20"],
        ma50=indicators["ma50"],
        vol_ratio=indicators["vol_ratio"],
        prev_close=prev_close
    )

    # Deteksi akumulasi
    accumulation = detect_accumulation(hist)

    # Timestamp WIB
    wib = pytz.timezone("Asia/Jakarta")
    now_wib = datetime.now(wib)

    # Hitung lot per termin (1 lot = 100 lembar)
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

    # Output JSON
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
        "strategy": {
            **STRATEGY,
            "termins": termins_with_lots
        },
        "checklist_reminder": {
            "point_1": "Harga tidak terkunci ARB & bergerak di atas Open setelah 09.30",
            "point_2": "Bid tebal (>30.000 lot) dan bertahan >15 menit",
            "point_3": "Dominasi Haka (beli di Offer > jual di Bid)"
        }
    }

    # Simpan ke data/isat.json
    data_dir = Path(__file__).resolve().parent.parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    output_path = data_dir / "isat.json"

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"[OK] Data saved to {output_path}")
    print(f"     Price: {current_price} ({change_pct:+.2f}%)")
    print(f"     Phase: {phase_info['phase_label']}")
    print(f"     Accumulation: {accumulation['signal']}")


if __name__ == "__main__":
    main()
