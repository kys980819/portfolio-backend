import { NextResponse } from 'next/server';
import OpenAI from 'openai';
import { MongoClient } from 'mongodb';
import { v4 as uuidv4 } from 'uuid';
import TelegramBot from 'node-telegram-bot-api';

export const runtime = 'nodejs';

// 환경변수에서 설정값 가져오기
const mongoUri = process.env.MONGO_URI;
const mongoDbName = process.env.MONGO_DB;
const mongoCollectionName = process.env.MONGO_COLLECTION;
const vectorStoreIds = process.env.VECTOR_STORE_IDS ? 
  process.env.VECTOR_STORE_IDS.split(',').map(id => id.trim()) : [];
const maxOutputTokens = parseInt(process.env.MAX_OUTPUT_TOKENS || '256');
const openaiTimeout = parseInt(process.env.OPENAI_TIMEOUT || '30') * 1000; // ms로 변환

// 텔레그램 설정
const telegramBotToken = process.env.TELEGRAM_BOT_TOKEN;
const telegramChatId = process.env.TELEGRAM_CHAT_ID;

// OpenAI 클라이언트 Lazy Singleton
let openaiClientSingleton = null;
function getOpenAIClient() {
  if (openaiClientSingleton) return openaiClientSingleton;
  const apiKey = process.env.OPENAI_API_KEY?.trim();
  if (!apiKey) return null;
  openaiClientSingleton = new OpenAI({
    apiKey,
    timeout: openaiTimeout
  });
  return openaiClientSingleton;
}

// 텔레그램 봇 Lazy Singleton
let telegramBotSingleton = null;
function getTelegramBot() {
  if (!telegramBotToken) return null;
  if (!telegramBotSingleton) {
    telegramBotSingleton = new TelegramBot(telegramBotToken, { polling: false });
  }
  return telegramBotSingleton;
}

// 텔레그램 알림 발송 함수
async function sendTelegramNotification(userMessage, aiResponse, sessionId) {
  const bot = getTelegramBot();
  if (!bot || !telegramChatId) {
    console.warn('텔레그램 설정이 없어 알림을 발송하지 않습니다.');
    return;
  }

  try {
    const message = `🤖 *포트폴리오 챗봇 새 메시지*

👤 *사용자:* ${userMessage}

🤖 *챗봇 응답:* ${aiResponse}

🆔 *세션 ID:* \`${sessionId}\`
⏰ *시간:* ${new Date().toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' })}`;

    await bot.sendMessage(telegramChatId, message, {
      parse_mode: 'Markdown',
      disable_web_page_preview: true
    });
    
    console.log('텔레그램 알림 발송 완료');
  } catch (error) {
    console.error('텔레그램 알림 발송 실패:', error.message);
  }
}

// MongoDB 글로벌 캐시 연결 재사용
const globalForMongo = globalThis;
let cachedMongoClient = globalForMongo._mongoClient || null;
let cachedMongoCollection = globalForMongo._mongoCollection || null;

async function getMongoCollection() {
  if (!mongoUri || !mongoDbName || !mongoCollectionName) {
    return null;
  }

  if (cachedMongoClient && cachedMongoCollection) {
    return cachedMongoCollection;
  }

  if (!cachedMongoClient) {
    try {
      cachedMongoClient = new MongoClient(mongoUri, {
        serverSelectionTimeoutMS: 5000
      });
      await cachedMongoClient.connect();
      globalForMongo._mongoClient = cachedMongoClient;
    } catch (error) {
      console.error("MongoDB 연결 실패:", error);
      return null;
    }
  }

  const db = cachedMongoClient.db(mongoDbName);
  cachedMongoCollection = db.collection(mongoCollectionName);
  globalForMongo._mongoCollection = cachedMongoCollection;
  return cachedMongoCollection;
}

export async function POST(request) {
  try {
    // Content-Type 확인
    const contentType = request.headers.get('content-type');
    if (!contentType || !contentType.includes('application/json')) {
      return NextResponse.json(
        { ok: false, error: "Content-Type must be application/json" },
        { status: 415 }
      );
    }

    // JSON 데이터 파싱
    const data = await request.json();
    
    // 세션/대화 ID 수집
    const sessionId = request.headers.get('x-session-id') || uuidv4();
    const conversationId = data.conversation_id || uuidv4();
    const message = data.message;

    // 메시지 검증
    if (!message || !message.trim()) {
      return NextResponse.json(
        { ok: false, error: "Message is required and cannot be empty" },
        { status: 400 }
      );
    }

    console.log(`수신 메시지 길이: ${message.length}`);

    // OpenAI API 키 확인
    const openaiClient = getOpenAIClient();
    if (!openaiClient) {
      console.error("OpenAI API 키가 설정되지 않았습니다.");
      return NextResponse.json(
        { ok: false, error: "OpenAI API 키가 설정되지 않았습니다" },
        { status: 500 }
      );
    }

    // 벡터스토어 ID 확인
    if (!vectorStoreIds.length) {
      console.error("VECTOR_STORE_IDS 환경변수가 설정되지 않았습니다.");
      return NextResponse.json(
        { ok: false, error: "VECTOR_STORE_IDS가 설정되지 않아 파일 검색을 사용할 수 없습니다" },
        { status: 500 }
      );
    }

    // OpenAI API 호출
    try {
      console.log("OpenAI API 호출 시작");
      
      const response = await openaiClient.responses.create({
        model: "gpt-4.1",
        input: [
          { role: "system", content: "너는 김윤성의 이력서를 보고 답변하는 챗봇이야" },
          { role: "user", content: message }
        ],
        tools: [{ type: "file_search", vector_store_ids: vectorStoreIds }],
        max_output_tokens: maxOutputTokens
      });

      const aiResponse = response.output_text;
      console.log(`AI 응답 생성 완료: ${aiResponse.length}자`);

      // MongoDB 저장 (가능한 경우에만, 글로벌 캐시 재사용)
      try {
        const collection = await getMongoCollection();
        if (collection) {
          const doc = {
            session_id: sessionId,
            conversation_id: conversationId,
            user: "guest",
            message: message,
            response: aiResponse,
            time: new Date().toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' })
          };
          await collection.insertOne(doc);
          console.log("대화 레코드가 MongoDB에 저장되었습니다.");
        } else {
          console.warn("MongoDB 설정이 없어 응답을 저장하지 않습니다.");
        }
      } catch (mongoError) {
        console.error("MongoDB 저장 실패:", mongoError);
      }

      // 텔레그램 알림 발송
      try {
        await sendTelegramNotification(message, aiResponse, sessionId);
      } catch (telegramError) {
        console.error("텔레그램 알림 발송 실패:", telegramError);
        // 텔레그램 알림 실패는 전체 응답에 영향을 주지 않음
      }

      // 성공 응답
      return NextResponse.json({
        ok: true,
        response: aiResponse,
        session_id: sessionId,
        conversation_id: conversationId
      });

    } catch (openaiError) {
      console.error("OpenAI API 에러:", openaiError);
      return NextResponse.json(
        { ok: false, error: "AI 서비스에 문제가 발생했습니다" },
        { status: 500 }
      );
    }

  } catch (error) {
    console.error("예상치 못한 에러 발생:", error);
    return NextResponse.json(
      { ok: false, error: "Internal server error" },
      { status: 500 }
    );
  }
}
