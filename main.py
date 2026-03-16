import streamlit as st
import pyupbit
import pandas as pd
import time
import requests

# 1. 페이지 설정 (스마트폰용)
st.set_page_config(page_title="동탄 비트코인 비서", layout="centered")

# --- 텔레그램 설정 (Streamlit Secrets에서 가져옴) ---
try:
    TOKEN = st.secrets["TELEGRAM_BOT_TOKEN"]
    CHAT_ID = st.secrets["TELEGRAM_CHAT_ID"]
except:
    st.error("Secrets 설정이 필요합니다!")
    st.stop()

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    params = {"chat_id": CHAT_ID, "text": message}
    requests.get(url, params=params)

# 2. 화면 상단 타이틀
st.title("🚀 실시간 비트코인 대시보드")
st.write("24시간 감시 및 차트 분석 중입니다.")

# 3. 데이터 가져오기 및 분석
df = pyupbit.get_ohlcv("KRW-BTC", interval="minute5", count=50)
current_price = pyupbit.get_current_price("KRW-BTC")

# RSI 지표 계산
delta = df['close'].diff()
up, down = delta.copy(), delta.copy()
up[up < 0] = 0
down[down > 0] = 0
avg_gain = up.rolling(window=14).mean()
avg_loss = abs(down.rolling(window=14).mean())
rs = avg_gain / avg_loss
rsi = 100 - (100 / (1 + rs))
now_rsi = rsi.iloc[-1]

# 4. 화면에 수치 표시
col1, col2 = st.columns(2)
with col1:
    st.metric("현재 가격", f"{current_price:,.0f}원")
with col2:
    st.metric("RSI (5분봉)", f"{now_rsi:.2f}")

# 5. 차트 표시
st.subheader("최근 5분봉 흐름")
st.line_chart(df['close'])

# 6. 알림 로직 (화면이 새로고침될 때마다 체크)
if now_rsi <= 30:
    st.warning("⚠️ RSI 과매도 구간! 매수 검토 중...")
    # 여기에 알림 발송 로직 추가 가능
elif now_rsi >= 70:
    st.success("⚠️ RSI 과매수 구간! 매도 검토 중...")

st.info("💡 화면을 새로고침하면 최신 시세로 업데이트됩니다.")
