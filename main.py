import json
import os
import time
from dataclasses import dataclass
from typing import Optional

import pandas as pd
import pyupbit
import requests
from dotenv import load_dotenv


STATE_PATH = os.path.join(os.path.dirname(__file__), "state.json")
TICKER = "KRW-BTC"


@dataclass(frozen=True)
class StochConfig:
    k: int
    d: int
    smooth_k: int


STOCH_CONFIGS = (
    StochConfig(5, 3, 3),
    StochConfig(10, 6, 6),
    StochConfig(20, 12, 12),
)


def _load_state() -> dict:
    if not os.path.exists(STATE_PATH):
        return {}
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_state(state: dict) -> None:
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STATE_PATH)


def _get_ohlcv(interval: str, count: int) -> pd.DataFrame:
    df = pyupbit.get_ohlcv(TICKER, interval=interval, count=count)
    if df is None or df.empty:
        raise RuntimeError(f"Failed to fetch OHLCV: interval={interval}")
    return df


def _compute_rsi14(close: pd.Series) -> pd.Series:
    # Wilder's RSI with RMA (alpha = 1/length)
    close = close.astype("float64")
    delta = close.diff()

    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)

    length = 14
    avg_gain = gain.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()
    avg_loss = loss.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()

    rs = avg_gain / avg_loss.replace(0.0, pd.NA)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi


def _compute_stoch_slow(
    high: pd.Series, low: pd.Series, close: pd.Series, cfg: StochConfig
) -> pd.DataFrame:
    high = high.astype("float64")
    low = low.astype("float64")
    close = close.astype("float64")

    lowest_low = low.rolling(window=cfg.k, min_periods=cfg.k).min()
    highest_high = high.rolling(window=cfg.k, min_periods=cfg.k).max()
    denom = (highest_high - lowest_low).replace(0.0, pd.NA)

    fast_k = 100.0 * (close - lowest_low) / denom
    slow_k = fast_k.rolling(window=cfg.smooth_k, min_periods=cfg.smooth_k).mean()
    slow_d = slow_k.rolling(window=cfg.d, min_periods=cfg.d).mean()

    k_col = f"STOCHk_{cfg.k}_{cfg.d}_{cfg.smooth_k}"
    d_col = f"STOCHd_{cfg.k}_{cfg.d}_{cfg.smooth_k}"
    return pd.DataFrame({k_col: slow_k, d_col: slow_d})


def _cross_up(prev_k: float, prev_d: float, cur_k: float, cur_d: float) -> bool:
    return prev_k <= prev_d and cur_k > cur_d


def _cross_down(prev_k: float, prev_d: float, cur_k: float, cur_d: float) -> bool:
    return prev_k >= prev_d and cur_k < cur_d


RED = "\033[91m"
RESET = "\033[0m"


def _print_red(msg: str) -> None:
    print(f"{RED}{msg}{RESET}", flush=True)


def _telegram_send(token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    resp = requests.post(url, timeout=10, data={"chat_id": chat_id, "text": text})
    resp.raise_for_status()


def _telegram_send_or_log(token: str, chat_id: str, text: str) -> bool:
    """Send Telegram message; on failure print error in red and return False."""
    try:
        _telegram_send(token, chat_id, text)
        return True
    except Exception as e:
        _print_red(f"[텔레그램 전송 실패] {type(e).__name__}: {e}")
        return False


def _get_current_price() -> Optional[float]:
    try:
        price = pyupbit.get_current_price(TICKER)
        if price is None:
            return None
        return float(price)
    except Exception:
        return None


def _signal_key(ts: pd.Timestamp, side: str) -> str:
    # ts: candle close/open timestamp from OHLCV index; using it as a stable key
    return f"{side}:{ts.isoformat()}"


def check_signals_and_alert(token: str, chat_id: str) -> dict:
    # 1) Data fetch (requirement: 5m, 4h, 1d)
    df_5m = _get_ohlcv("minute5", count=400)
    _ = _get_ohlcv("minute240", count=200)
    _ = _get_ohlcv("day", count=200)

    # Use last *closed* candle to avoid intrabar noise:
    # prev = -3, cur = -2
    if len(df_5m) < 50:
        raise RuntimeError("Not enough 5m candles to compute indicators")

    rsi14 = _compute_rsi14(df_5m["close"])

    stoch_results = []
    for cfg in STOCH_CONFIGS:
        stoch = _compute_stoch_slow(df_5m["high"], df_5m["low"], df_5m["close"], cfg)
        stoch_results.append((cfg, stoch))

    cur_ts = df_5m.index[-2]
    prev_ts = df_5m.index[-3]

    cur_rsi = float(rsi14.loc[cur_ts])
    if pd.isna(cur_rsi):
        return {"ts": cur_ts, "price": _get_current_price(), "rsi14": None, "stoch": [], "signal": None}

    buy_ok = cur_rsi < 30
    sell_ok = cur_rsi > 70

    all_buy_cross = True
    all_sell_cross = True
    stoch_snapshot = []

    for cfg, stoch in stoch_results:
        k_col = f"STOCHk_{cfg.k}_{cfg.d}_{cfg.smooth_k}"
        d_col = f"STOCHd_{cfg.k}_{cfg.d}_{cfg.smooth_k}"

        if k_col not in stoch.columns or d_col not in stoch.columns:
            raise RuntimeError(f"Unexpected stoch columns for {cfg}: {list(stoch.columns)}")

        cur_k = float(stoch.loc[cur_ts, k_col])
        cur_d = float(stoch.loc[cur_ts, d_col])
        prev_k = float(stoch.loc[prev_ts, k_col])
        prev_d = float(stoch.loc[prev_ts, d_col])

        if any(pd.isna(x) for x in (cur_k, cur_d, prev_k, prev_d)):
            return {"ts": cur_ts, "price": _get_current_price(), "rsi14": cur_rsi, "stoch": [], "signal": None}

        is_buy_piece = cur_k < 20 and _cross_up(prev_k, prev_d, cur_k, cur_d)
        is_sell_piece = cur_k >= 80 and _cross_down(prev_k, prev_d, cur_k, cur_d)
        all_buy_cross = all_buy_cross and is_buy_piece
        all_sell_cross = all_sell_cross and is_sell_piece

        stoch_snapshot.append(
            {
                "cfg": f"{cfg.k}-{cfg.d}-{cfg.smooth_k}",
                "k": cur_k,
                "d": cur_d,
                "buy_piece": is_buy_piece,
                "sell_piece": is_sell_piece,
            }
        )

    state = _load_state()
    price = _get_current_price()

    if buy_ok and all_buy_cross:
        key = _signal_key(cur_ts, "BUY")
        if state.get("last_signal") != key:
            price_text = f"\n현재가: {price:,.0f} KRW" if price is not None else ""
            _telegram_send_or_log(
                token,
                chat_id,
                f"📢 [매수 신호] 모든 지표 바닥권 통과! (5분봉 골든크로스){price_text}",
            )
            state["last_signal"] = key
            _save_state(state)
            return {
                "ts": cur_ts,
                "price": price,
                "rsi14": cur_rsi,
                "stoch": stoch_snapshot,
                "buy_ok": buy_ok,
                "sell_ok": sell_ok,
                "all_buy_cross": all_buy_cross,
                "all_sell_cross": all_sell_cross,
                "signal": "BUY",
            }
        return {
            "ts": cur_ts,
            "price": price,
            "rsi14": cur_rsi,
            "stoch": stoch_snapshot,
            "buy_ok": buy_ok,
            "sell_ok": sell_ok,
            "all_buy_cross": all_buy_cross,
            "all_sell_cross": all_sell_cross,
            "signal": "BUY_DUPLICATE",
        }

    if sell_ok and all_sell_cross:
        key = _signal_key(cur_ts, "SELL")
        if state.get("last_signal") != key:
            price_text = f"\n현재가: {price:,.0f} KRW" if price is not None else ""
            _telegram_send_or_log(
                token,
                chat_id,
                f"🚨 [매도 신호] 에너지 과부하! 수익실현 검토 (5분봉 데드크로스){price_text}",
            )
            state["last_signal"] = key
            _save_state(state)
            return {
                "ts": cur_ts,
                "price": price,
                "rsi14": cur_rsi,
                "stoch": stoch_snapshot,
                "buy_ok": buy_ok,
                "sell_ok": sell_ok,
                "all_buy_cross": all_buy_cross,
                "all_sell_cross": all_sell_cross,
                "signal": "SELL",
            }
        return {
            "ts": cur_ts,
            "price": price,
            "rsi14": cur_rsi,
            "stoch": stoch_snapshot,
            "buy_ok": buy_ok,
            "sell_ok": sell_ok,
            "all_buy_cross": all_buy_cross,
            "all_sell_cross": all_sell_cross,
            "signal": "SELL_DUPLICATE",
        }

    return {
        "ts": cur_ts,
        "price": price,
        "rsi14": cur_rsi,
        "stoch": stoch_snapshot,
        "buy_ok": buy_ok,
        "sell_ok": sell_ok,
        "all_buy_cross": all_buy_cross,
        "all_sell_cross": all_sell_cross,
        "signal": None,
    }


def _fmt_snapshot(snap: dict) -> str:
    ts = snap.get("ts")
    price = snap.get("price")
    rsi = snap.get("rsi14")
    sig = snap.get("signal")

    ts_text = str(ts) if ts is not None else "-"
    price_text = f"{price:,.0f}" if isinstance(price, (int, float)) else "?"
    rsi_text = f"{rsi:.2f}" if isinstance(rsi, (int, float)) else "?"

    stoch_parts = []
    for s in snap.get("stoch", []) or []:
        stoch_parts.append(
            f"{s.get('cfg')} K={s.get('k', float('nan')):6.2f} D={s.get('d', float('nan')):6.2f}"
        )

    cond = []
    if "buy_ok" in snap:
        cond.append(f"buy_ok={snap.get('buy_ok')}")
        cond.append(f"all_buy_cross={snap.get('all_buy_cross')}")
        cond.append(f"sell_ok={snap.get('sell_ok')}")
        cond.append(f"all_sell_cross={snap.get('all_sell_cross')}")

    stoch_text = " | ".join(stoch_parts) if stoch_parts else "(stoch n/a)"
    cond_text = " ".join(cond) if cond else ""
    sig_text = f" signal={sig}" if sig else ""

    return f"[{ts_text}] price={price_text}KRW RSI14={rsi_text} {stoch_text} {cond_text}{sig_text}".strip()


def main() -> None:
    load_dotenv()
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID in .env")

    print("Starting BTC alert bot (Upbit) ...", flush=True)
    print(f"- ticker: {TICKER}", flush=True)
    print("- check interval: 60s", flush=True)
    print("- indicators: RSI(14), StochSlow(5-3-3/10-6-6/20-12-12)", flush=True)

    price = _get_current_price()
    start_msg = (
        f"비트코인 감시를 시작합니다! 현재 가격은 {price:,.0f}원입니다."
        if price is not None
        else "비트코인 감시를 시작합니다! 현재 가격은 조회되지 않았습니다."
    )
    _telegram_send_or_log(token, chat_id, start_msg)

    while True:
        try:
            snap = check_signals_and_alert(token, chat_id)
            print(_fmt_snapshot(snap), flush=True)
        except Exception as e:
            print(f"[ERROR] {type(e).__name__}: {e}", flush=True)
        time.sleep(60)


if __name__ == "__main__":
    main()
