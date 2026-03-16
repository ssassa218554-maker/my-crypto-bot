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

# --- 한국 시간(KST) 설정 ---
KST = timezone(timedelta(hours=9))
now = datetime.now(KST)

# --- 텔레그램 설정 ---
try:
    TOKEN = st.secrets["TELEGRAM_BOT_TOKEN"]
    CHAT_ID = st.secrets["TELEGRAM_CHAT_ID"]
except:
    st.error("Secrets 설정(토큰 정보)을 확인해주세요!")
    st.stop()

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    params = {"chat_id": CHAT_ID, "text": message}
    try:
        requests.get(url, params=params)
    except:
        pass

# 2. 화면 구성
st.title("🚀 실시간 암호화폐 초정밀 대시보드")
st.write(f"현재 한국 시간: {now.strftime('%Y-%m-%d %H:%M:%S')}")

coin_list = ["KRW-BTC", "KRW-ETH", "KRW-SOL"]

# 중복 알림 방지용 세션 상태
if 'last_alert' not in st.session_state:
    st.session_state['last_alert'] = {coin: "" for coin in coin_list}

# 스토캐스틱 계산 함수
def get_stochastic(df, n, m, t):
    low_n = df['low'].rolling(window=n).min()
    high_n = df['high'].rolling(window=n).max()
    k = 100 * ((df['close'] - low_n) / (high_n - low_n))
    d = k.rolling(window=m).mean()
    slow_d = d.rolling(window=t).mean()
    return k, d

# 3. 데이터 분석 및 차트 생성
for coin in coin_list:
    df = pyupbit.get_ohlcv(coin, interval="minute5", count=200)
    if df is None: continue
    current_price = pyupbit.get_current_price(coin)

    # --- 지표 계산 ---
    # 1) 이동평균선
    df['ma5'] = df['close'].rolling(window=5).mean()
    df['ma20'] = df['close'].rolling(window=20).mean()

    # 2) RSI
    delta = df['close'].diff()
    up, down = delta.copy(), delta.copy()
    up[up < 0] = 0
    down[down > 0] = 0
    avg_gain = up.rolling(window=14).mean()
    avg_loss = abs(down.rolling(window=14).mean())
    df['rsi'] = 100 - (100 / (1 + (avg_gain / avg_loss)))

    # 3) 스토캐스틱 3종 세트
    df['k5'], df['d3'] = get_stochastic(df, 5, 3, 3)
    df['k10'], df['d6'] = get_stochastic(df, 10, 6, 6)
    df['k20'], df['d12'] = get_stochastic(df, 20, 12, 12)

    # 4. 상단 지표 표시
    st.markdown(f"### 💎 {coin} 분석 리포트")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("현재가", f"{current_price:,.0f}원")
    m2.metric("RSI", f"{df['rsi'].iloc[-1]:.2f}")
    m3.metric("Stoch(5,3)", f"{df['k5'].iloc[-1]:.1f}")
    m4.metric("Stoch(20,12)", f"{df['k20'].iloc[-1]:.1f}")

    # 5. [전문가용] 5단 통합 차트 (캔들+RSI+스토 3종)
    fig = make_subplots(rows=5, cols=1, shared_xaxes=True, 
                        vertical_spacing=0.02, 
                        row_heights=[0.4, 0.15, 0.15, 0.15, 0.15],
                        subplot_titles=("가격 & 이평선", "RSI", "Stoch(5,3,3)", "Stoch(10,6,6)", "Stoch(20,12,12)"))

    # 메인 캔들
    fig.add_trace(go.Candlestick(x=df.index, open=df['open'], high=df['high'], low=df['low'], close=df['close'], name="Price"), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['ma5'], name="MA5", line=dict(color='orange', width=1)), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['ma20'], name="MA20", line=dict(color='red', width=1)), row=1, col=1)

    # RSI
    fig.add_trace(go.Scatter(x=df.index, y=df['rsi'], name="RSI", line=dict(color='purple')), row=2, col=1)
    
    # 스토캐스틱 3종
    fig.add_trace(go.Scatter(x=df.index, y=df['k5'], name="K5", line=dict(color='blue')), row=3, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['d3'], name="D3", line=dict(color='orange', dash='dot')), row=3, col=1)
    
    fig.add_trace(go.Scatter(x=df.index, y=df['k10'], name="K10", line=dict(color='blue')), row=4, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['d6'], name="D6", line=dict(color='orange', dash='dot')), row=4, col=1)
    
    fig.add_trace(go.Scatter(x=df.index, y=df['k20'], name="K20", line=dict(color='blue')), row=5, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['d12'], name="D12", line=dict(color='orange', dash='dot')), row=5, col=1)

    fig.update_layout(height=1200, xaxis_rangeslider_visible=False, showlegend=False)
    st.plotly_chart(fig, use_container_width=True)

    # --- 6. 실시간 알림 로직 (비트/이더/솔 개별 적용) ---
    alert_msg = ""
    curr_rsi = df['rsi'].iloc[-1]
    curr_k5 = df['k5'].iloc[-1]
    curr_ma5 = df['ma5'].iloc[-1]
    curr_ma20 = df['ma20'].iloc[-1]
    prev_ma5 = df['ma5'].iloc[-2]
    prev_ma20 = df['ma20'].iloc[-2]

    # 알림 조건: 골든/데드크로스 혹은 과매수/과매도
    if prev_ma5 < prev_ma20 and curr_ma5 > curr_ma20:
        alert_msg = f"✨ [골든크로스] {coin}\n현재가: {current_price:,.0f}원\n단기 추세가 상승으로 전환되었습니다!"
    elif prev_ma5 > prev_ma20 and curr_ma5 < curr_ma20:
        alert_msg = f"💀 [데드크로스] {coin}\n현재가: {current_price:,.0f}원\n하락 주의! 추세가 꺾였습니다."
    elif curr_rsi <= 25 or curr_k5 <= 15:
        alert_msg = f"📉 [바닥권 포착] {coin}\nRSI: {curr_rsi:.1f}, Stoch: {curr_k5:.1f}\n현재 매우 저평가 상태입니다."
    elif curr_rsi >= 75 or curr_k5 >= 85:
        alert_msg = f"📈 [천장권 포착] {coin}\nRSI: {curr_rsi:.1f}, Stoch: {curr_k5:.1f}\n단기 과열 상태입니다. 조심하세요!"

    if alert_msg and st.session_state['last_alert'][coin] != alert_msg:
        send_telegram(alert_msg)
        st.session_state['last_alert'][coin] = alert_msg

    st.divider()

time.sleep(60)
st.rerun()
