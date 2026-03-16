import os, requests, sys
from dotenv import load_dotenv
load_dotenv()
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
def send(msg):
    try: requests.get(f"https://api.telegram.org/bot{TOKEN}/sendMessage", params={"chat_id": CHAT_ID, "text": msg}, timeout=10)
    except: pass
if __name__ == "__main__":
    status = sys.argv[1] if len(sys.argv) > 1 else "check"
    if status == "on": send("🖥️ 컴퓨터가 켜졌습니다! 비트코인 봇이 감시를 시작할 준비가 되었습니다.")
    elif status == "off": send("🔌 컴퓨터가 종료됩니다. 감시를 중단합니다.")
