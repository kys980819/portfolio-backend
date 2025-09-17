from flask import Flask, request, jsonify
from flask_cors import CORS
import openai
import os
from dotenv import load_dotenv

# .env 파일 로드 (파일이 없어도 에러가 발생하지 않도록 처리)
try:
    load_dotenv()
except Exception as e:
    print(f".env 파일 로드 중 오류 발생: {e}")
    print("환경변수를 직접 설정하거나 .env 파일을 생성해주세요.")

# Flask 앱 생성
app = Flask(__name__)
CORS(app)

# OpenAI API 키 설정 (환경변수에서 가져오기)
api_key = os.getenv('OPENAI_API_KEY')
if not api_key:
    print("경고: OPENAI_API_KEY 환경변수가 설정되지 않았습니다.")
    print("다음 중 하나의 방법으로 API 키를 설정해주세요:")
    print("1. .env 파일을 생성하고 OPENAI_API_KEY=your_key_here 추가")
    print("2. 환경변수로 직접 설정")
    print("3. 코드에서 직접 설정")
    client = None
else:
    client = openai.OpenAI(api_key=api_key)

# /sendMessage 엔드포인트 생성 (POST 요청만 받음)
@app.route('/sendMessage', methods=['POST'])
def send_message():
    try:
        data = request.get_json()  # 요청에서 JSON 데이터 꺼내기
        
        # JSON 파싱 실패 시 처리
        if data is None:
            return jsonify({"ok": False, "error": "Invalid JSON data"}), 400
        
        message = data.get('message')  # "message" 키 값 가져오기
        
        # message 필드 검증
        if not message or not message.strip():
            return jsonify({"ok": False, "error": "Message is required and cannot be empty"}), 400

        print("사용자가 보낸 메시지:", message)
        
        # API 키 확인
        if not client:
            return jsonify({"ok": False, "error": "OpenAI API 키가 설정되지 않았습니다"}), 500
        
        # OpenAI API 호출
        try:
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "user", "content": message}
                ],
                max_tokens=1000,
                temperature=0.7
            )
            
            ai_response = response.choices[0].message.content
            print("AI 응답:", ai_response)
            
            return jsonify({"ok": True, "response": ai_response}), 200
            
        except openai.OpenAIError as e:
            print(f"OpenAI API 에러: {str(e)}")
            return jsonify({"ok": False, "error": "AI 서비스에 문제가 발생했습니다"}), 500
        
    except Exception as e:
        print(f"에러 발생: {str(e)}")
        return jsonify({"ok": False, "error": "Internal server error"}), 500

# 실행
if __name__ == '__main__':
    app.run(debug=True)
