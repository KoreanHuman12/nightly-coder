import os
import google.generativeai as genai

# 1. 설정 (Secrets에서 가져오기)
api_key = os.environ.get("GEMINI_API_KEY")
genai.configure(api_key=api_key)

def main():
    print("🚀 Nightly Agent Started (Robust Mode)")
    
    # 404 에러를 방지하기 위해 가장 안정적인 모델명 사용
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    try:
        # 에러가 나던 chat_with_gemini 대신 최신 방식 사용
        response = model.generate_content("안녕? 오늘 날씨에 어울리는 맥퀸의 컬렉션을 추천해줘.")
        print(f"✅ Gemini Response: {response.text}")
    except Exception as e:
        print(f"❌ Error: {e}")
        raise e

if __name__ == "__main__":
    main()
