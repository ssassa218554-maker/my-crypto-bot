import streamlit as st
import pyupbit
import pandas as pd
import time
import requests
from datetime import datetime, timedelta, timezone
import plotly.graph_objects as go

# 1. 페이지 설정
st.set_page_config(page_title="동탄 비트코인 비서", layout="wide")

# --- 한국 시간(KST) 설정 ---
KST = timezone(timedelta(hours=9))
now = datetime.now(KST) # 이제 서버가 어디있든 한국 시간을 가져옵니다.

# --- 텔레그램 설정 ---
try:
    TOKEN = st.secrets["TELEGRAM_BOT_TOKEN"]
    CHAT_ID = st.secrets["TELEGRAM_CHAT_ID"]
except:
    st.error("Secrets 설정에서 토큰 정보를 확인해주세요!")
    st.stop()

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    params = {"chat_id": CHAT_ID, "text": message}
    requests.get(url, params=params)

# 2. 화면 구성
st.title("🚀 실시간 암호화폐 대시보드")
st.write(f"현재 한국 시간: {now.strftime('%Y-%m-%d %H:%M:%S')}")

# 코인 목록 설정 (비트코인, 이더리움, 솔라나)
coin_list = ["KRW-BTC", "KRW-ETH", "KRW-SOL"]

# 3. 각 코인 데이터 가져오기 및 분석
for coin in coin_list:
    df = pyupbit.get_ohlcv(coin, interval="minute5", count=50)
    current_price = pyupbit.get_current_price(coin)

    # RSI 계산
    delta = df['close'].diff()
    up, down = delta.copy(), delta.copy()
    up[up < 0] = 0
    down[down > 0] = 0
    avg_gain = up.rolling(window=14).mean()
    avg_loss = abs(down.rolling(window=14).mean())
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    now_rsi = rsi.iloc[-1]

    # 4. 화면 표시 (각 코인별)
    st.subheader(f"{coin} 정보")
    col1, col2 = st.columns(2)
    with col1:
        st.metric("현재 가격", f"{current_price:,.0f}원")
    with col2:
        st.metric("RSI (5분봉)", f"{now_rsi:.2f}")

    # 5. 멋진 캔들 차트 그리기
    fig = go.Figure(data=[go.Candlestick(x=df.index,
                    open=df['open'],
                    high=df['high'],
                    low=df['low'],
                    close=df['close'])])
    fig.update_layout(xaxis_rangeslider_visible=False)
    st.plotly_chart(fig, use_container_width=True)

    # 6. 실시간 RSI 알림 로직 (코인별로 개별 적용)
    if now_rsi <= 30:
        st.warning(f"⚠️ {coin} 과매도 구간입니다. (매수 검토)")
    elif now_rsi >= 70:
        st.success(f"⚠️ {coin} 과매수 구간입니다. (매도 검토)")

# 7. 한국 시간 기준 정기 브리핑 (9, 13, 17, 21시)
report_hours = [9, 13, 17, 21]
current_hour = now.hour
current_minute = now.minute

if 'last_report_hour' not in st.session_state:
    st.session_state['last_report_hour'] = -1

# 정각(0분)에 알림 전송 (세 코인 모두)
if current_hour in report_hours and current_minute == 0:
    if st.session_state['last_report_hour'] != current_hour:
        # 모든 코인의 가격 정보를 하나의 메시지로 묶어서 전송
        msg = f"🔔 [동탄 비서 정기 알림]\n현재 한국 시간: {current_hour}시 정각\n\n"
        for coin in coin_list:
             current_price = pyupbit.get_current_price(coin)
             # RSI 계산
             df = pyupbit.get_ohlcv(coin, interval="minute5", count=50)
             delta = df['close'].diff()
             up, down = delta.copy(), delta.copy()
             up[up < 0] = 0
             down[down > 0] = 0
             avg_gain = up.rolling(window=14).mean()
             avg_loss = abs(down.rolling(window=14).mean())
             rs = avg_gain / avg_loss
             rsi = 100 - (100 / (1 + rs))
             now_rsi = rsi.iloc[-1]
             msg += f"- {coin} 가격: {current_price:,.0f}원, RSI: {now_rsi:.2f}\n"

        send_telegram(msg)
        st.session_state['last_report_hour'] = current_hour
        st.success(f"한국 시간 {current_hour}시 알림을 보냈습니다!")

# 1분마다 자동 새로고침
time.sleep(60)
st.rerun()
