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

if 'alert_log' not in st.session_state:
    st.session_state['alert_log'] = []
if 'last_alert' not in st.session_state:
    st.session_state['last_alert'] = {}

# --- 텔레그램 설정 ---
try:
    TOKEN = st.secrets["TELEGRAM_BOT_TOKEN"]
    CHAT_ID = st.secrets["TELEGRAM_CHAT_ID"]
except:
    st.error("Secrets 설정(TOKEN, CHAT_ID)을 확인해주세요!")
    st.stop()

# 알림 및 로그 함수
def send_and_log_alert(coin, message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    params = {"chat_id": CHAT_ID, "text": message}
    try:
        response = requests.get(url, params=params)
        if response.status_code == 200:
            st.toast("텔레그램 전송 성공!")
    except:
        pass
    
    log_entry = {
        "시간": datetime.now(KST).strftime('%H:%M:%S'),
        "코인": coin,
        "알림 내용": message.replace('\n', ' ')
    }
    st.session_state['alert_log'].insert(0, log_entry)
    if len(st.session_state['alert_log']) > 50:
        st.session_state['alert_log'].pop()

# 스토캐스틱 함수
def get_stochastic(df, n, m):
    low_n = df['low'].rolling(window=n).min()
    high_n = df['high'].rolling(window=n).max()
    k = 100 * ((df['close'] - low_n) / (high_n - low_n))
    d = k.rolling(window=m).mean()
    return k, d

# 2. 메인 화면
st.title("🚀 실시간 암호화폐 PRO 관제센터")

# 테스트 버튼 섹션
st.info("작동 여부를 확인하려면 아래 버튼을 눌러보세요.")
if st.button("🔔 텔레그램 테스트 알림 보내기"):
    prices = [f"- {c.replace('KRW-','')}: {pyupbit.get_current_price(c):,.0f}원" for c in ["KRW-BTC", "KRW-ETH", "KRW-SOL"]]
    send_and_log_alert("테스트", "✅ [테스트 알림] 비서가 정상 작동 중입니다!\n" + "\n".join(prices))

st.write(f"현재 한국 시간: {now.strftime('%H:%M:%S')}")

coin_list = ["KRW-BTC", "KRW-ETH", "KRW-SOL"]

# 3. 데이터 분석 및 시각화
for coin in coin_list:
    df = pyupbit.get_ohlcv(coin, interval="minute5", count=200)
    if df is None: continue
    current_price = pyupbit.get_current_price(coin)
    
    # 지표 계산
    df['ma5'] = df['close'].rolling(5).mean()
    df['ma20'] = df['close'].rolling(20).mean()
    delta = df['close'].diff()
    up, down = delta.copy(), delta.copy()
    up[up < 0] = 0; down[down > 0] = 0
    df['rsi'] = 100 - (100 / (1 + (up.rolling(14).mean() / abs(down.rolling(14).mean()))))
    df['k5'], df['d3'] = get_stochastic(df, 5, 3)
    df['k10'], df['d6'] = get_stochastic(df, 10, 6)
    df['k20'], df['d12'] = get_stochastic(df, 20, 12)

    # --- [복구 완료] 상단 수치 표시 ---
    st.markdown(f"### 💎 {coin}")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("현재가", f"{current_price:,.0f}원")
    m2.metric("RSI", f"{df['rsi'].iloc[-1]:.2f}")
    m3.metric("Stoch(5,3)", f"{df['k5'].iloc[-1]:.1f}")
    m4.metric("Stoch(20,12)", f"{df['k20'].iloc[-1]:.1f}")

    # 5단 차트
    fig = make_subplots(rows=5, cols=1, shared_xaxes=True, vertical_spacing=0.02, 
                        row_heights=[0.4, 0.15, 0.15, 0.15, 0.15],
                        subplot_titles=("가격 & 이평선", "RSI", "Stoch(5,3,3)", "Stoch(10,6,6)", "Stoch(20,12,12)"))
    fig.add_trace(go.Candlestick(x=df.index, open=df['open'], high=df['high'], low=df['low'], close=df['close'], name="Price"), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['ma5'], name="MA5", line=dict(color='orange')), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['ma20'], name="MA20", line=dict(color='red')), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['rsi'], name="RSI", line=dict(color='purple')), row=2, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['k5'], name="K5", line=dict(color='blue')), row=3, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['k10'], name="K10", line=dict(color='blue')), row=4, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['k20'], name="K20", line=dict(color='blue')), row=5, col=1)
    fig.update_layout(height=1000, xaxis_rangeslider_visible=False, showlegend=False)
    st.plotly_chart(fig, use_container_width=True)

    # 실시간 신호 감지
    curr_ma5, prev_ma5 = df['ma5'].iloc[-1], df['ma5'].iloc[-2]
    curr_ma20, prev_ma20 = df['ma20'].iloc[-1], df['ma20'].iloc[-2]
    alert_msg = ""
    if prev_ma5 < prev_ma20 and curr_ma5 > curr_ma20:
        alert_msg = f"✨ [{coin.replace('KRW-','')}] 골든크로스 발생!"
    elif prev_ma5 > prev_ma20 and curr_ma5 < curr_ma20:
        alert_msg = f"💀 [{coin.replace('KRW-','')}] 데드크로스 경고!"
    
    if alert_msg and st.session_state['last_alert'].get(coin) != alert_msg:
        send_and_log_alert(coin, alert_msg)
        st.session_state['last_alert'][coin] = alert_msg
    st.divider()

# 4. 정기 브리핑
report_hours = [9, 13, 17, 21]
if now.hour in report_hours and now.minute == 0:
    if st.session_state.get('last_report_hour') != now.hour:
        prices = [f"- {c.replace('KRW-','')}: {pyupbit.get_current_price(c):,.0f}원" for c in coin_list]
        send_and_log_alert("전체", f"🔔 [{now.hour}시 정기 보고]\n" + "\n".join(prices))
        st.session_state['last_report_hour'] = now.hour

# 5. 하단 기록 표
st.subheader("📋 최근 알림 기록")
if st.session_state['alert_log']:
    st.table(pd.DataFrame(st.session_state['alert_log']))

time.sleep(60)
st.rerun()
