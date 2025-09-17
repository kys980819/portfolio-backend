from flask import Flask, request, jsonify
from flask_cors import CORS

# Flask 앱 생성
app = Flask(__name__)
CORS(app)

# /sendMessage 엔드포인트 생성 (POST 요청만 받음)
@app.route('/sendMessage', methods=['POST'])
def send_message():
    data = request.get_json()  # 요청에서 JSON 데이터 꺼내기
    message = data.get('message')  # "message" 키 값 가져오기

    print("사용자가 보낸 메시지:", message)
    
    return jsonify({"ok": True, "response": message}),200# 응답 반환
    # return jsonify({"response": f"Message received: {message}"})  "Message received: ..."라는 보기 조금더 좋은 방법

# 실행
if __name__ == '__main__':
    app.run(debug=True)
    # def = 함수를 묶는것 function 과 비슷
