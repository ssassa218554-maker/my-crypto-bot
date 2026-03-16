import streamlit as st
import pyupbit
import pandas as pd
import time
import requests
from datetime import datetime, timedelta, timezone

# 1. 페이지 설정
st.set_page_config(page_title="동탄 비트코인 비서", layout="centered")

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
st.title("🚀 실시간 비트코인 대시보드")
st.write(f"현재 한국 시간: {now.strftime('%Y-%m-%d %H:%M:%S')}")

# 3. 데이터 가져오기
df = pyupbit.get_ohlcv("KRW-BTC", interval="minute5", count=50)
current_price = pyupbit.get_current_price("KRW-BTC")

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

# 4. 화면 표시
col1, col2 = st.columns(2)
with col1:
    st.metric("현재 가격", f"{current_price:,.0f}원")
with col2:
    st.metric("RSI (5분봉)", f"{now_rsi:.2f}")

st.line_chart(df['close'])

# 5. 한국 시간 기준 정기 브리핑 (9, 13, 17, 21시)
report_hours = [9, 13, 17, 21]
current_hour = now.hour
current_minute = now.minute

if 'last_report_hour' not in st.session_state:
    st.session_state['last_report_hour'] = -1

# 정각(0분)에 알림 전송
if current_hour in report_hours and current_minute == 0:
    if st.session_state['last_report_hour'] != current_hour:
        msg = f"🔔 [동탄 비서 정기 알림]\n현재 한국 시간: {current_hour}시 정각\n비트코인 가격: {current_price:,.0f}원\nRSI: {now_rsi:.2f}"
        send_telegram(msg)
        st.session_state['last_report_hour'] = current_hour
        st.success(f"한국 시간 {current_hour}시 알림을 보냈습니다!")

# 6. 실시간 RSI 알림 로직
if now_rsi <= 30:
    st.warning("⚠️ 과매도 구간입니다. (매수 검토)")
elif now_rsi >= 70:
    st.success("⚠️ 과매수 구간입니다. (매도 검토)")

# 1분마다 자동 새로고침
time.sleep(60)
st.rerun()
