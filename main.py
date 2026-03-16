import streamlit as st
import pyupbit
import pandas as pd
import time
import requests
from datetime import datetime, timedelta, timezone
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# 1. 페이지 설정
st.set_page_config(page_title="동탄 코인 관제센터 PRO", layout="wide")

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

# 알림 및 로그 통합 함수
def send_and_log_alert(coin, message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    params = {"chat_id": CHAT_ID, "text": message}
    try:
        response = requests.get(url, params=params)
        if response.status_code != 200:
            st.error(f"텔레그램 전송 실패: {response.text}")
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

# 지표 계산 함수 (RSI, Stochastic)
def get_indicators(df):
    # MA
    df['ma5'] = df['close'].rolling(5).mean()
    df['ma20'] = df['close'].rolling(20).mean()
    # RSI
    delta = df['close'].diff()
    up, down = delta.copy(), delta.copy()
    up[up < 0] = 0; down[down > 0] = 0
    df['rsi'] = 100 - (100 / (1 + (up.rolling(14).mean() / abs(down.rolling(14).mean()))))
    # Stochastic (5,3,3 / 10,6,6 / 20,12,12)
    def stoch(df, n, m):
        ln, hn = df['low'].rolling(n).min(), df['high'].rolling(n).max()
        k = 100 * ((df['close'] - ln) / (hn - ln))
        d = k.rolling(m).mean()
        return k, d
    df['k5'], df['d3'] = stoch(df, 5, 3)
    df['k10'], df['d6'] = stoch(df, 10, 6)
    df['k20'], df['d12'] = stoch(df, 20, 12)
    return df

# 2. 메인 화면 및 테스트 버튼
st.title("🚀 실시간 암호화폐 초정밀 관제센터")
if st.button("🔔 시스템 작동 테스트 (텔레그램 전송)"):
    send_and_log_alert("시스템", "✅ 관제 시스템이 정상 작동 중입니다.")

st.write(f"현재 한국 시간: {now.strftime('%Y-%m-%d %H:%M:%S')}")

coin_list = ["KRW-BTC", "KRW-ETH", "KRW-SOL"]

# 3. 데이터 분석 및 시각화 루프
for coin in coin_list:
    # 데이터 로드 (5분봉 & 4시간봉)
    df5 = pyupbit.get_ohlcv(coin, interval="minute5", count=200)
    df4h = pyupbit.get_ohlcv(coin, interval="minute240", count=200)
    
    if df5 is None or df4h is None: continue
    
    df5 = get_indicators(df5)
    df4h = get_indicators(df4h)
    curr_p = pyupbit.get_current_price(coin)

    # --- [필수] 상단 지표 수치 표시 (Metric) ---
    st.markdown(f"## 💎 {coin}")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("현재가", f"{curr_p:,.0f}원")
    c2.metric("RSI(5m)", f"{df5['rsi'].iloc[-1]:.1f}")
    c3.metric("RSI(4h)", f"{df4h['rsi'].iloc[-1]:.1f}")
    c4.metric("Stoch(5m)", f"{df5['k5'].iloc[-1]:.1f}")
    c5.metric("Stoch(4h)", f"{df4h['k20'].iloc[-1]:.1f}")

    # 5단 차트 (5분봉 기준 시각화)
    fig = make_subplots(rows=5, cols=1, shared_xaxes=True, vertical_spacing=0.02, 
                        row_heights=[0.4, 0.15, 0.15, 0.15, 0.15],
                        subplot_titles=("가격/이평선(5m)", "RSI", "Stoch(5,3,3)", "Stoch(10,6,6)", "Stoch(20,12,12)"))
    fig.add_trace(go.Candlestick(x=df5.index, open=df5['open'], high=df5['high'], low=df5['low'], close=df5['close'], name="Price"), row=1, col=1)
    fig.add_trace(go.Scatter(x=df5.index, y=df5['ma5'], name="MA5", line=dict(color='orange')), row=1, col=1)
    fig.add_trace(go.Scatter(x=df5.index, y=df5['ma20'], name="MA20", line=dict(color='red')), row=1, col=1)
    fig.add_trace(go.Scatter(x=df5.index, y=df5['rsi'], name="RSI", line=dict(color='purple')), row=2, col=1)
    fig.add_trace(go.Scatter(x=df5.index, y=df5['k5'], name="K5", line=dict(color='blue')), row=3, col=1)
    fig.add_trace(go.Scatter(x=df5.index, y=df5['k10'], name="K10", line=dict(color='blue')), row=4, col=1)
    fig.add_trace(go.Scatter(x=df5.index, y=df5['k20'], name="K20", line=dict(color='blue')), row=5, col=1)
    fig.update_layout(height=1000, xaxis_rangeslider_visible=False, showlegend=False)
    st.plotly_chart(fig, use_container_width=True)

    # --- [핵심] 알림 로직 (5분봉 & 4시간봉 통합) ---
    def check_alerts(df, timeframe_name):
        msg = ""
        c_ma5, p_ma5 = df['ma5'].iloc[-1], df['ma5'].iloc[-2]
        c_ma20, p_ma20 = df['ma20'].iloc[-1], df['ma20'].iloc[-2]
        c_rsi = df['rsi'].iloc[-1]
        c_k5 = df['k5'].iloc[-1]
        
        # 1) 이평선 교차
        if p_ma5 < p_ma20 and c_ma5 > c_ma20:
            msg = f"✨ [{coin}] {timeframe_name} 골든크로스!"
        elif p_ma5 > p_ma20 and c_ma5 < c_ma20:
            msg = f"💀 [{coin}] {timeframe_name} 데드크로스!"
        
        # 2) RSI + 스토캐스틱 과매수/매도 (4시간봉일 때 더 강력한 메시지)
        elif c_rsi <= 30 and c_k5 <= 20:
            msg = f"📉 [{coin}] {timeframe_name} 바닥권 포착! (RSI/Stoch 저점)"
        elif c_rsi >= 70 and c_k5 >= 80:
            msg = f"📈 [{coin}] {timeframe_name} 고점 주의! (RSI/Stoch 고점)"
        
        return msg

    # 5분봉 알림 체크
    alert5 = check_alerts(df5, "5분봉")
    if alert5 and st.session_state['last_alert'].get(f"{coin}_5m") != alert5:
        send_and_log_alert(coin, alert5)
        st.session_state['last_alert'][f"{coin}_5m"] = alert5

    # 4시간봉 알림 체크
    alert4h = check_alerts(df4h, "4시간봉")
    if alert4h and st.session_state['last_alert'].get(f"{coin}_4h") != alert4h:
        send_and_log_alert(coin, f"🔥 [중요] {alert4h}")
        st.session_state['last_alert'][f"{coin}_4h"] = alert4h

    st.divider()

# 4. 정기 브리핑 (9, 13, 17, 21시)
if now.hour in [9, 13, 17, 21] and now.minute == 0:
    if st.session_state.get('last_report_hour') != now.hour:
        report = f"🔔 [{now.hour}시 정기 보고]\n"
        for c in coin_list:
            p = pyupbit.get_current_price(c)
            report += f"- {c}: {p:,.0f}원\n"
        send_and_log_alert("전체", report)
        st.session_state['last_report_hour'] = now.hour

# 5. 하단 알림 기록 표
st.subheader("📋 실시간 알림 타임라인 (최근 50개)")
if st.session_state['alert_log']:
    st.table(pd.DataFrame(st.session_state['alert_log']))

time.sleep(60)
st.rerun()
