import streamlit as st
import pyupbit
import pandas as pd

st.set_page_config(page_title="나의 비트코인 비서", layout="centered")
st.title("🚀 실시간 비트코인 대시보드")
st.write("동탄에서 가동 중인 AI 비서의 분석 결과입니다.")

price = pyupbit.get_current_price("KRW-BTC")
df = pyupbit.get_ohlcv("KRW-BTC", interval="minute5", count=20)

col1, col2 = st.columns(2)
with col1:
    st.metric("현재가", f"{price:,.0f}원")
with col2:
    delta = df['close'].diff()
    up, down = delta.copy(), delta.copy()
    up[up < 0] = 0
    down[down > 0] = 0
    avg_gain = up.rolling(window=14).mean()
    avg_loss = abs(down.rolling(window=14).mean())
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    st.metric("RSI(5분봉)", f"{rsi.iloc[-1]:.2f}")

st.subheader("최근 가격 흐름")
st.line_chart(df['close'])