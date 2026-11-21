import os
import asyncio
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from google import genai
from google.genai import types

# 랜더 환경변수에서 키를 자동으로 읽어오도록 안전하게 세팅 (직접 키를 적어도 됨)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "여기에_텔레그램_봇_토큰_입력")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "여기에_구글_AI_스튜디오_API_키_입력")

# 최신 플래그십 엔진
MODEL_NAME = "gemini-3.8-flash"

ai_client = genai.Client(api_key=GEMINI_API_KEY)

# 🪙 크립토 v6 프롬프트
CRYPTO_SYSTEM_PROMPT = """
너는 월스트리트 및 글로벌 탑티어 크립토 퀀트 헤지펀드의 최고투자책임자(CIO)이자 최고리스크책임자(CRO)다.
할루시네이션은 절대 금지하며, 확인 불가 지표는 '데이터 미확인'으로 솔직히 명시하라.
반드시 Google Search를 통해 현재 시점의 실시간 데이터를 직접 검색하여 반영하라.

[출력 양식 (6개 섹션 엄수)]
[헤더] 🕒 기준 시각: 현재 한국 시각(KST) 명기
[섹션 0] 🚨 매크로 환경 및 락아웃 게이트키퍼: NQ 선물, DXY, US10Y 및 매크로 이벤트 락아웃(신규 진입 금지 여부)
[섹션 1] 📊 자금 흐름 & 도미넌스: BTC/ETH 현재가, 24시간 변동률, 공포탐욕지수, BTC.D, USDT.D, 시장 레짐 판정
[섹션 2] 🏛️ [거시/일간 필터] 온체인 펀더멘털: STH Realized Price 지지/저항, MVRV Z-Score, aSOPR, ETF 순유출입
[섹션 3] ⚡ [3시간 미시 타점] 오더플로우 & 옵션: 미결제약정(OI) 증감, 펀딩비, 선물 vs 현물 CVD, 호가창 두께, 청산 밀집 구간, Deribit DVOL 및 옵션 꼬리 위험
[섹션 4] 📰 핵심 카탈리스트 & 속보 요약 (3~5개)
[섹션 5] 🎯 CIO/CRO 실행 전략: 마켓 레짐 종합, 진입 구간, 1/2차 목표가, Invalidation 손절가(필수), 손익비(1:2.5 미만 시 PASS), 계좌 리스크 1~2% 포지션 사이징 가이드
"""

# 📈 나스닥·국장 주식 v2 프롬프트
STOCK_SYSTEM_PROMPT = """
너는 뉴욕 월스트리트 매크로 헤지펀드와 서울 여의도 프랍트레이딩 데스크를 총괄하는 수석 매크로·반도체 스트래티지스트이자 최고리스크책임자(CRO)다.
반드시 현재 한국 시각(KST)을 인식하여 [장전 모닝 / 장중 점심 / 장마감 데일리] 중 알맞은 모드로 자동 출력하라.
한국거래소(KRX) 자체 야간 파생시장(코스피200 야간선물)과 넥스트레이드(NXT) 프리/애프터마켓, 외국인 코스피200 선물(왝더독)을 반영하라.

[출력 양식 (6개 섹션 엄수)]
[헤더] 🕒 기준 시각: 현재 한국 시각(KST) 및 현재 모드 명기
[섹션 0] 🚨 글로벌 매크로 & 외환·야간파생: US10Y, DXY, 원/달러 환율 변동 속도, KRX 코스피200 야간선물 등락률, 실시간 NQ 선물
[섹션 1] 🇺🇸 뉴욕증시 코어 & 빅테크 수급: 3대 지수 마감, VIX, M7 빅테크 수급
[섹션 2] ⚡ 필라델피아 반도체(SOX) & 밸류체인: NVDA, AMD, AVGO(ASIC), MU(DRAM/HBM), SNDK(낸드), TSMC, ASML 전이 효과
[섹션 3] 📈 반도체 업황 사이클 & 상대강도: 메모리 가격 모멘텀, SOX/SPX 상대강도
[섹션 4] 🇰🇷 국내 증시(KRX & NXT) 실전 수급: 삼성전자·SK하이닉스(NXT 호가 및 장중 지지력), 외국인 선물(왝더독) 순매수, 섹터 순환매, 공매도/신용 리스크
[섹션 5] 🎯 CRO 실행 프로토콜: 당일 레짐 판정, 뇌동매매 방어 수칙, 코스피 지지/저항, 삼전/하닉 손절 무효화선, 손익비(1:2.5 미만 시 PASS), 현금 비중 가이드
"""

async def generate_briefing(prompt_type: str) -> str:
    system_instruction = CRYPTO_SYSTEM_PROMPT if prompt_type == "crypto" else STOCK_SYSTEM_PROMPT
    user_query = f"현재 시각 기준으로 실시간 구글 검색(Google Search)을 실행하여 최신 데이터를 반영한 [{prompt_type.upper()}] 정기 브리핑 전문을 작성하라."
    try:
        response = ai_client.models.generate_content(
            model=MODEL_NAME,
            contents=user_query,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                tools=[types.Tool(google_search=types.GoogleSearch())],
                temperature=0.3
            )
        )
        return response.text
    except Exception as e:
        return f"🚨 브리핑 생성 중 오류가 발생했습니다: {str(e)}"

async def send_split_message(update: Update, text: str):
    max_len = 4000
    for i in range(0, len(text), max_len):
        await update.message.reply_text(text[i:i + max_len])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "🏛️ [CIO·CRO 퀀트 브리핑 데스크 가동 중]\n\n"
        "특수문자(/) 없이 카톡처럼 단어만 치셔도 됩니다:\n\n"
        "👉 '코인' : 크립토 온체인 & 수급 브리핑\n"
        "👉 '주식' : 나스닥 & 국장 반도체 브리핑\n\n"
        f"현재 탑재된 AI 두뇌: {MODEL_NAME} (실시간 구글 검색 연동)"
    )
    await update.message.reply_text(msg)

async def handle_crypto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_msg = await update.message.reply_text("⏳ [크립토 퀀트 데스크] 최신 온체인·파생 데이터를 검색하고 분석 중입니다... (약 15~20초 소요)")
    report = await generate_briefing("crypto")
    await status_msg.delete()
    await send_split_message(update, report)

async def handle_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_msg = await update.message.reply_text("⏳ [매크로 주식 데스크] 나스닥·환율·외국인 선물 수급을 집계하고 분석 중입니다... (약 15~20초 소요)")
    report = await generate_briefing("stock")
    await status_msg.delete()
    await send_split_message(update, report)

async def route_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    text = update.message.text.strip()
    if any(k in text for k in ["코인", "크립토", "비트코인", "/coin", "/crypto", "/코인"]):
        await handle_crypto(update, context)
    elif any(k in text for k in ["주식", "국장", "나스닥", "/stock", "/주식"]):
        await handle_stock(update, context)
    else:
        await start(update, context)

# -------------------------------------------------------------
# 🌐 랜더(Render) 클라우드 전용 24시간 헬스체크 웹서버 (포트 감지용)
# -------------------------------------------------------------
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Quant Briefing Bot is running 24/7!")

def start_health_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    server.serve_forever()

if __name__ == "__main__":
    # 백그라운드에서 웹서버 구동
    threading.Thread(target=start_health_server, daemon=True).start()
    
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(CommandHandler("coin", handle_crypto))
    app.add_handler(CommandHandler("stock", handle_stock))
    app.add_handler(MessageHandler(filters.TEXT, route_text))
    
    print(f"🤖 텔레그램 봇이 완벽하게 가동되었습니다! (엔진: {MODEL_NAME})")
    app.run_polling()