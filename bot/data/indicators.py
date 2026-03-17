"""Technical indicator calculations using pandas-ta."""

from __future__ import annotations

import pandas as pd
import pandas_ta as ta


def add_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add a standard set of indicators to an OHLCV DataFrame.

    Expects columns: open, high, low, close, volume.
    Returns the DataFrame with extra indicator columns appended.
    """
    if df.empty or len(df) < 2:
        return df

    # ── Trend ──────────────────────────────────────────
    df["ema_5"] = ta.ema(df["close"], length=5)
    df["ema_13"] = ta.ema(df["close"], length=13)
    df["ema_20"] = ta.ema(df["close"], length=20)
    df["ema_50"] = ta.ema(df["close"], length=50)
    df["ema_200"] = ta.ema(df["close"], length=200)

    # ADX (trend strength)
    adx = ta.adx(df["high"], df["low"], df["close"], length=14)
    if adx is not None and not adx.empty:
        df["adx"] = adx.iloc[:, 0]  # ADX_14
        df["di_plus"] = adx.iloc[:, 1]  # DMP_14
        df["di_minus"] = adx.iloc[:, 2]  # DMN_14

    # ── Momentum ───────────────────────────────────────
    df["rsi"] = ta.rsi(df["close"], length=14)

    macd = ta.macd(df["close"], fast=12, slow=26, signal=9)
    if macd is not None and not macd.empty:
        df["macd"] = macd.iloc[:, 0]  # MACD_12_26_9
        df["macd_histogram"] = macd.iloc[:, 1]  # MACDh_12_26_9
        df["macd_signal"] = macd.iloc[:, 2]  # MACDs_12_26_9

    stoch = ta.stoch(df["high"], df["low"], df["close"])
    if stoch is not None and not stoch.empty:
        df["stoch_k"] = stoch.iloc[:, 0]
        df["stoch_d"] = stoch.iloc[:, 1]

    # ── Volatility ─────────────────────────────────────
    df["atr"] = ta.atr(df["high"], df["low"], df["close"], length=14)

    bbands = ta.bbands(df["close"], length=20, std=2.0)
    if bbands is not None and not bbands.empty:
        df["bb_lower"] = bbands.iloc[:, 0]
        df["bb_mid"] = bbands.iloc[:, 1]
        df["bb_upper"] = bbands.iloc[:, 2]
        df["bb_bandwidth"] = bbands.iloc[:, 3] if bbands.shape[1] > 3 else None
        df["bb_pct_b"] = bbands.iloc[:, 4] if bbands.shape[1] > 4 else None

    # ── Volume ─────────────────────────────────────────
    df["vwap"] = ta.vwap(df["high"], df["low"], df["close"], df["volume"])
    obv = ta.obv(df["close"], df["volume"])
    if obv is not None:
        df["obv"] = obv

    return df


def detect_regime(df: pd.DataFrame) -> str:
    """Detect market regime from indicators.

    Returns one of: 'trending', 'ranging', 'volatile'.
    """
    if df.empty or "adx" not in df.columns:
        return "ranging"

    adx_val = df["adx"].iloc[-1]
    atr_val = df["atr"].iloc[-1] if "atr" in df.columns else 0
    close_val = df["close"].iloc[-1]
    atr_pct = (atr_val / close_val * 100) if close_val else 0

    if pd.isna(adx_val):
        return "ranging"

    if adx_val > 25:
        if atr_pct > 3.0:
            return "volatile"
        return "trending"
    elif adx_val < 20:
        return "ranging"
    else:
        return "volatile" if atr_pct > 2.5 else "ranging"


def ema_alignment(df: pd.DataFrame) -> str:
    """Check EMA alignment: 'bullish', 'bearish', or 'neutral'."""
    if df.empty:
        return "neutral"
    for col in ("ema_20", "ema_50", "ema_200"):
        if col not in df.columns or pd.isna(df[col].iloc[-1]):
            return "neutral"

    ema20 = df["ema_20"].iloc[-1]
    ema50 = df["ema_50"].iloc[-1]
    ema200 = df["ema_200"].iloc[-1]

    if ema20 > ema50 > ema200:
        return "bullish"
    elif ema20 < ema50 < ema200:
        return "bearish"
    return "neutral"
