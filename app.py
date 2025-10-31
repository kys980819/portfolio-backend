from flask import Flask, request, jsonify
from flask_cors import CORS
import openai
import os
import logging
from dotenv import load_dotenv
from pymongo import MongoClient, errors as pymongo_errors
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo
import requests

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# .env 파일 로드 (파일이 없어도 에러가 발생하지 않도록 처리)
try:
    load_dotenv()
except Exception as e:
    logger.error(f".env 파일 로드 중 오류 발생: {e}")
    logger.info("환경변수를 직접 설정하거나 .env 파일을 생성해주세요.")

# Flask 앱 생성
app = Flask(__name__)
# CORS 제한 (환경변수 ALLOWED_ORIGINS 사용, 콤마로 구분)
allowed_origins_env = os.getenv('ALLOWED_ORIGINS', '').strip()
if allowed_origins_env:
    allowed_origins = [origin.strip() for origin in allowed_origins_env.split(',') if origin.strip()]
    logger.info(f"허용된 CORS 오리진: {allowed_origins}")
else:
    allowed_origins = "*"
    logger.warning("ALLOWED_ORIGINS 환경변수가 설정되지 않아 모든 오리진을 허용합니다. 배포 시 제한을 권장합니다.")
CORS(app, resources={r"/*": {"origins": allowed_origins}})

# 요청 크기 제한 설정 (1MB)
app.config['MAX_CONTENT_LENGTH'] = 1 * 1024 * 1024

# OpenAI 타임아웃/토큰 제한 설정
timeout_env = os.getenv('OPENAI_TIMEOUT', '30').strip()
try:
    openai_timeout = float(timeout_env)
except ValueError:
    logger.warning("OPENAI_TIMEOUT 값이 잘못되었습니다. 기본 30초로 설정합니다.")
    openai_timeout = 30.0

max_tokens_env = os.getenv('MAX_OUTPUT_TOKENS', '256').strip()
try:
    max_output_tokens = int(max_tokens_env)
except ValueError:
    logger.warning("MAX_OUTPUT_TOKENS 값이 잘못되었습니다. 기본 256으로 설정합니다.")
    max_output_tokens = 256

# OpenAI API 키 설정 (환경변수에서 가져오기)
api_key = os.getenv('OPENAI_API_KEY')
if not api_key:
    logger.warning("OPENAI_API_KEY 환경변수가 설정되지 않았습니다.")
    logger.info("다음 중 하나의 방법으로 API 키를 설정해주세요:")
    logger.info("1. .env 파일을 생성하고 OPENAI_API_KEY=your_key_here 추가")
    logger.info("2. 환경변수로 직접 설정")
    logger.info("3. 코드에서 직접 설정")
    client = None
elif not api_key.startswith('sk-'):
    logger.warning("API 키 형식이 올바르지 않습니다. 'sk-'로 시작해야 합니다.")
    client = None
else:
    client = openai.OpenAI(api_key=api_key, timeout=openai_timeout)
    logger.info("OpenAI 클라이언트가 성공적으로 초기화되었습니다.")

# 벡터스토어 ID 환경변수 로드 (.env: VECTOR_STORE_IDS=vs_xxx[,vs_yyy])
vector_store_ids_env = os.getenv('VECTOR_STORE_IDS', '').strip()
if vector_store_ids_env:
    VECTOR_STORE_IDS = [v.strip() for v in vector_store_ids_env.split(',') if v.strip()]
    logger.info(f"벡터스토어 ID가 {len(VECTOR_STORE_IDS)}개 설정되었습니다.")
else:
    VECTOR_STORE_IDS = []
    logger.warning("VECTOR_STORE_IDS 환경변수가 설정되지 않았습니다. 파일 검색 도구를 사용할 수 없습니다.")

# MongoDB 연결 설정 (.env: MONGO_URI, MONGO_DB, MONGO_COLLECTION)
mongo_client = None
mongo_collection = None
mongo_uri = os.getenv('MONGO_URI')
mongo_db_name = os.getenv('MONGO_DB')
mongo_collection_name = os.getenv('MONGO_COLLECTION')

if mongo_uri and mongo_db_name and mongo_collection_name:
    try:
        mongo_client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
        # 연결 확인 (ping)
        mongo_client.admin.command('ping')
        db = mongo_client[mongo_db_name]
        mongo_collection = db[mongo_collection_name]
        logger.info(f"MongoDB 연결 성공: db={mongo_db_name}, collection={mongo_collection_name}")
    except pymongo_errors.PyMongoError as e:
        logger.error(f"MongoDB 연결 실패: {str(e)}")
        mongo_client = None
        mongo_collection = None
else:
    logger.warning("MONGO_URI/MONGO_DB/MONGO_COLLECTION 환경변수가 설정되지 않았습니다. 응답 저장이 비활성화됩니다.")

# 텔레그램 설정
telegram_bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
telegram_chat_id = os.getenv('TELEGRAM_CHAT_ID')

# 텔레그램 알림 발송 함수
def send_telegram_notification(user_message, ai_response, session_id):
    if not telegram_bot_token or not telegram_chat_id:
        logger.warning('텔레그램 설정이 없어 알림을 발송하지 않습니다.')
        return
    
    try:
        # Markdown 특수 문자 이스케이프 처리
        def escape_markdown(text):
            if not text:
                return ""
            # Markdown 특수 문자 이스케이프: * _ [ ] ( ) ~ ` > # + - = | { } . !
            return text.replace('\\', '\\\\').replace('*', '\\*').replace('_', '\\_').replace('[', '\\[').replace(']', '\\]').replace('(', '\\(').replace(')', '\\)').replace('~', '\\~').replace('`', '\\`').replace('>', '\\>').replace('#', '\\#').replace('+', '\\+').replace('-', '\\-').replace('=', '\\=').replace('|', '\\|').replace('{', '\\{').replace('}', '\\}').replace('.', '\\.').replace('!', '\\!')
        
        escaped_user_message = escape_markdown(user_message)
        escaped_ai_response = escape_markdown(ai_response)
        escaped_session_id = escape_markdown(str(session_id))
        
        message = f"""🤖 *포트폴리오 챗봇 새 메시지*

👤 *사용자:* {escaped_user_message}

🤖 *챗봇 응답:* {escaped_ai_response}

🆔 *세션 ID:* `{escaped_session_id}`
⏰ *시간:* {datetime.now(ZoneInfo("Asia/Seoul")).strftime('%Y-%m-%d %H:%M:%S')}"""
        
        # 텔레그램 메시지 길이 제한 처리 (4096자)
        MAX_TELEGRAM_MESSAGE_LENGTH = 4096
        if len(message) > MAX_TELEGRAM_MESSAGE_LENGTH:
            # 메시지가 너무 길면 자르고 안내 메시지 추가
            truncated_length = MAX_TELEGRAM_MESSAGE_LENGTH - 200  # 안내 메시지 공간 확보
            truncated_user = escaped_user_message[:truncated_length // 2] if len(escaped_user_message) > truncated_length // 2 else escaped_user_message
            truncated_ai = escaped_ai_response[:truncated_length // 2] if len(escaped_ai_response) > truncated_length // 2 else escaped_ai_response
            
            message = f"""🤖 *포트폴리오 챗봇 새 메시지*

👤 *사용자:* {truncated_user}...

🤖 *챗봇 응답:* {truncated_ai}...

⚠️ *메시지가 길어 일부가 잘렸습니다*

🆔 *세션 ID:* `{escaped_session_id}`
⏰ *시간:* {datetime.now(ZoneInfo("Asia/Seoul")).strftime('%Y-%m-%d %H:%M:%S')}"""
        
        url = f"https://api.telegram.org/bot{telegram_bot_token}/sendMessage"
        payload = {
            "chat_id": telegram_chat_id,
            "text": message,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True
        }
        
        response = requests.post(url, json=payload, timeout=5)
        response.raise_for_status()
        logger.info('텔레그램 알림 발송 완료')
    except requests.RequestException as e:
        logger.error(f'텔레그램 알림 발송 실패: {str(e)}')
    except Exception as e:
        logger.error(f'텔레그램 알림 발송 중 예상치 못한 오류: {str(e)}')

# 헬스체크 엔드포인트
@app.route('/health', methods=['GET'])
def health_check():
    """서버 상태 확인 엔드포인트"""
    return jsonify({
        "ok": True,
        "status": "healthy",
        "openai_configured": client is not None
    }), 200

# /sendMessage 엔드포인트 생성 (POST 요청만 받음)
@app.route('/sendMessage', methods=['POST'])
def send_message():
    try:
        # Content-Type 확인 및 JSON 파싱
        if not request.is_json:
            return jsonify({"ok": False, "error": "Content-Type must be application/json"}), 415
        data = request.get_json(silent=True)  # 요청에서 JSON 데이터 꺼내기 (silent)
        
        # JSON 파싱 실패 시 처리
        if data is None:
            return jsonify({"ok": False, "error": "Invalid JSON data"}), 400
        
        # 세션/대화 ID 수집
        session_id = request.headers.get('x-session-id') or str(uuid.uuid4())
        conversation_id = data.get('conversation_id') or str(uuid.uuid4())

        message = data.get('message')  # "message" 키 값 가져오기
        
        # message 필드 검증
        if not message or not message.strip():
            return jsonify({"ok": False, "error": "Message is required and cannot be empty"}), 400

        logger.info(f"사용자가 보낸 메시지: {message}")
        logger.info(f"수신 메시지 길이: {len(message)}")
        
        # API 키 확인
        if not client:
            logger.error("OpenAI API 키가 설정되지 않았습니다.")
            return jsonify({"ok": False, "error": "OpenAI API 키가 설정되지 않았습니다"}), 500
        
        # 벡터스토어 ID 확인
        if not VECTOR_STORE_IDS:
            logger.error("VECTOR_STORE_IDS 환경변수가 설정되지 않았습니다.")
            return jsonify({"ok": False, "error": "VECTOR_STORE_IDS가 설정되지 않아 파일 검색을 사용할 수 없습니다"}), 500
        
        # OpenAI API 호출 (Responses API 사용)
        try:
            logger.info("OpenAI API 호출 시작")
            response = client.responses.create(
                model="gpt-4.1",
                input=[
                    {"role": "system", "content": "너는 김윤성의 이력서를 보고 답변하는 챗봇이야"},
                    {"role": "user", "content": message}
                ],
                tools=[{"type": "file_search", "vector_store_ids": VECTOR_STORE_IDS}],
                max_output_tokens=max_output_tokens
            )

            
            ai_response = response.output_text
            logger.info(f"AI 응답 생성 완료: {len(ai_response)}자")

            # MongoDB 저장 (가능한 경우에만)
            if mongo_collection is not None:
                try:
                    doc = {
                        "session_id": session_id,
                        "conversation_id": conversation_id,
                        "user": "guest",
                        "message": message,
                        "response": ai_response,
                        "time": datetime.now(ZoneInfo("Asia/Seoul")).isoformat()
                    }
                    mongo_collection.insert_one(doc)
                    logger.info("대화 레코드가 MongoDB에 저장되었습니다.")
                except pymongo_errors.PyMongoError as e:
                    logger.error(f"MongoDB 저장 실패: {str(e)}")
            else:
                logger.warning("MongoDB 컬렉션이 설정되지 않아 응답을 저장하지 않습니다.")

            # 텔레그램 알림 발송
            try:
                send_telegram_notification(message, ai_response, session_id)
            except Exception as telegram_error:
                logger.error(f"텔레그램 알림 발송 실패: {str(telegram_error)}")
                # 텔레그램 알림 실패는 전체 응답에 영향을 주지 않음

            # 클라이언트 응답 (일관된 성공 스키마)
            return jsonify({
                "ok": True,
                "response": ai_response,
                "session_id": session_id,
                "conversation_id": conversation_id
            }), 200
            
        except openai.OpenAIError as e:
            logger.error(f"OpenAI API 에러: {str(e)}")
            return jsonify({"ok": False, "error": "AI 서비스에 문제가 발생했습니다"}), 500
        
    except Exception as e:
        logger.error(f"예상치 못한 에러 발생: {str(e)}")
        return jsonify({"ok": False, "error": "Internal server error"}), 500

# 실행
if __name__ == '__main__':
    logger.info("Flask 서버를 시작합니다...")
    logger.info(f"OpenAI 클라이언트 상태: {'연결됨' if client else '연결 안됨'}")
    app.run(host='0.0.0.0', port=5000)