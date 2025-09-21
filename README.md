# Portfolio Backend

OpenAI API를 활용한 챗봇 백엔드 서버입니다.

## 🚀 시작하기

### 1. 가상환경 활성화
```bash
# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate
```

### 2. 의존성 설치
```bash
pip install -r requirements.txt
```

### 3. 환경변수 설정
`.env` 파일을 생성하고 다음 내용을 추가하세요:
```
OPENAI_API_KEY=your_openai_api_key_here
```

OpenAI API 키는 [OpenAI Platform](https://platform.openai.com/api-keys)에서 발급받을 수 있습니다.

### 4. 서버 실행
```bash
python app.py
```

서버는 `http://localhost:5000`에서 실행됩니다.

## 📡 API 사용법

### POST /sendMessage

사용자 메시지를 AI에게 전송하고 응답을 받습니다.

**요청:**
```json
{
  "message": "안녕하세요!"
}
```

**응답:**
```json
{
  "ok": true,
  "response": "안녕하세요! 무엇을 도와드릴까요?"
}
```

## 🛠️ 기술 스택

- **Flask**: 웹 프레임워크
- **Flask-CORS**: CORS 처리
- **OpenAI API**: GPT-4o 모델
- **python-dotenv**: 환경변수 관리

## 📝 주의사항

- OpenAI API 키가 올바르게 설정되어 있는지 확인하세요
- API 사용량에 따라 비용이 발생할 수 있습니다
- 개발 환경에서는 `debug=True`로 설정되어 있습니다
