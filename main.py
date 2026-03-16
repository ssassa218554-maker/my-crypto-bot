import streamlit as st
import pyupbit
import pandas as pd
import time
import requests
from datetime import datetime

# 1. 페이지 설정
st.set_page_config(page_title="동탄 비트코인 비서", layout="centered")

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
    try:
        requests.get(url, params=params)
    except Exception as e:
        st.error(f"메시지 전송 실패: {e}")

# 2. 화면 구성
st.title("🚀 실시간 비트코인 대시보드")
st.write(f"현재 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

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

# 5. [신규] 시간별 정기 브리핑 로직
# 지정된 시간(시) 목록
report_hours = [9, 13, 17, 21]
current_hour = datetime.now().hour
current_minute = datetime.now().minute

# 정각(0분)에 해당 시간대라면 알림 전송 (중복 방지를 위해 세션 상태 활용)
if 'last_report_hour' not in st.session_state:
    st.session_state['last_report_hour'] = -1

if current_hour in report_hours and current_minute == 0:
    if st.session_state['last_report_hour'] != current_hour:
        msg = f"🔔 [정기 브리핑]\n현재 시간: {current_hour}시 정각\n비트코인 가격: {current_price:,.0f}원\nRSI: {now_rsi:.2f}"
        send_telegram(msg)
        st.session_state['last_report_hour'] = current_hour
        st.success(f"{current_hour}시 정기 알림 전송 완료!")

# 6. 실시간 RSI 알림 로직 (기존)
if now_rsi <= 30:
    st.warning("⚠️ 과매도 구간 알림 발송")
elif now_rsi >= 70:
    st.success("⚠️ 과매수 구간 알림 발송")

# 화면 자동 새로고침 (1분마다)
time.sleep(60)
st.rerun()
