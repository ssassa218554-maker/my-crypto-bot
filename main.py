import streamlit as st
import pyupbit
import pandas as pd
import time
import requests
from datetime import datetime, timedelta, timezone
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# 1. 페이지 설정
st.set_page_config(page_title="동탄 코인 비서 PRO", layout="wide")

# --- 한국 시간(KST) 및 세션 상태 설정 ---
KST = timezone(timedelta(hours=9))
now = datetime.now(KST)

# 알림 기록을 저장할 리스트 초기화 (앱이 켜져 있는 동안 유지)
if 'alert_log' not in st.session_state:
    st.session_state['alert_log'] = []

if 'last_alert' not in st.session_state:
    st.session_state['last_alert'] = {}

# --- 텔레그램 설정 ---
try:
    TOKEN = st.secrets["TELEGRAM_BOT_TOKEN"]
    CHAT_ID = st.secrets["TELEGRAM_CHAT_ID"]
except:
    st.error("Secrets 설정을 확인해주세요!")
    st.stop()

# 알림을 보내고 기록하는 함수
def send_and_log_alert(coin, message):
    # 텔레그램 전송
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    params = {"chat_id": CHAT_ID, "text": message}
    try:
        requests.get(url, params=params)
    except:
        pass
    
    # 히스토리에 기록 추가 (시간, 코인, 내용)
    log_entry = {
        "시간": datetime.now(KST).strftime('%H:%M:%S'),
        "코인": coin,
        "알림 내용": message.split('\n')[0] # 첫 줄만 깔끔하게 저장
    }
    # 최신 알림이 맨 위로 오게 추가
    st.session_state['alert_log'].insert(0, log_entry)
    # 너무 많아지면 성능을 위해 최근 50개만 유지
    if len(st.session_state['alert_log']) > 50:
        st.session_state['alert_log'].pop()

# 2. 메인 화면
st.title("🚀 실시간 암호화폐 PRO 관제센터")
st.write(f"현재 한국 시간: {now.strftime('%Y-%m-%d %H:%M:%S')}")

coin_list = ["KRW-BTC", "KRW-ETH", "KRW-SOL"]

# 스토캐스틱 계산 함수
def get_stochastic(df, n, m, t):
    low_n = df['low'].rolling(window=n).min()
    high_n = df['high'].rolling(window=n).max()
    k = 100 * ((df['close'] - low_n) / (high_n - low_n))
    d = k.rolling(window=m).mean()
    return k, d

# 3. 데이터 분석 및 차트 (코인별 반복)
for coin in coin_list:
    df = pyupbit.get_ohlcv(coin, interval="minute5", count=200)
    if df is None: continue
    current_price = pyupbit.get_current_price(coin)

    # 지표 계산 (MA, RSI, Stochastic 5/10/20)
    df['ma5'] = df['close'].rolling(window=5).mean()
    df['ma20'] = df['close'].rolling(window=20).mean()
    
    delta = df['close'].diff()
    up, down = delta.copy(), delta.copy()
    up[up < 0] = 0; down[down > 0] = 0
    df['rsi'] = 100 - (100 / (1 + (up.rolling(14).mean() / abs(down.rolling(14).mean()))))
    
    df['k5'], df['d3'] = get_stochastic(df, 5, 3, 3)
    df['k10'], df['d6'] = get_stochastic(df, 10, 6, 6)
    df['k20'], df['d12'] = get_stochastic(df, 20, 12, 12)

    # 차트 그리기 (생략 - 기존 코드와 동일)
    # ... (Plotly 코드) ...
    st.plotly_chart(go.Figure(...)) # 실제 코드에는 이전의 5단 차트가 들어갑니다.

    # --- 실시간 알림 로직 ---
    curr_ma5, prev_ma5 = df['ma5'].iloc[-1], df['ma5'].iloc[-2]
    curr_ma20, prev_ma20 = df['ma20'].iloc[-1], df['ma20'].iloc[-2]
    curr_rsi = df['rsi'].iloc[-1]

    alert_msg = ""
    if prev_ma5 < prev_ma20 and curr_ma5 > curr_ma20:
        alert_msg = f"✨ [골든크로스] {coin} 상승 추세 전환!"
    elif prev_ma5 > prev_ma20 and curr_ma5 < curr_ma20:
        alert_msg = f"💀 [데드크로스] {coin} 하락 주의!"
    elif curr_rsi <= 25:
        alert_msg = f"📉 [과매도] {coin} RSI {curr_rsi:.1f} 바닥권"
    elif curr_rsi >= 75:
        alert_msg = f"📈 [과매수] {coin} RSI {curr_rsi:.1f} 천장권"

    # 알림 발송 및 기록
    if alert_msg and st.session_state['last_alert'].get(coin) != alert_msg:
        send_and_log_alert(coin, alert_msg)
        st.session_state['last_alert'][coin] = alert_msg

    st.divider()

# 4. [신규] 하단 알림 히스토리 섹션
st.subheader("📋 최근 알림 기록 (실시간 로그)")
if st.session_state['alert_log']:
    log_df = pd.DataFrame(st.session_state['alert_log'])
    st.table(log_df) # 깔끔한 표 형태로 출력
else:
    st.write("아직 발생한 알림이 없습니다. 감시 중...")

time.sleep(60)
st.rerun()
