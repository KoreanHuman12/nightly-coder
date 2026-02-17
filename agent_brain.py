import os
import re
import json
import subprocess
import requests
import glob
import google.generativeai as genai
from datetime import datetime

# --- [1. 설정 및 초기화] ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
MEMORY_FILE = "agent_memory.json"
DECISION_LOG = "docs/decisions.md"

# API 키 설정
genai.configure(api_key=GEMINI_API_KEY)

# --- [🔍 진단: 내 키로 사용 가능한 모델 확인] ---
print("🔍 Checking available models for your API key...")
try:
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            print(f" - Found: {m.name}")
except Exception as e:
    print(f"⚠️ Error listing models: {e}")

# 페르소나 설정
SYSTEM_PROMPT = """
당신은 'Nightly Autonomous Agent'입니다.
1. [Strict TDD]: 실패하는 테스트(Red) -> 구현(Green) -> 리팩토링 순서를 지키세요.
2. [Format]: 코드는 `### FILE: 경로/파일명` 형식으로 작성하세요.
"""

# [중요] 가장 안정적인 모델 이름 사용 (gemini-1.5-flash)
# 만약 이것도 안 되면 로그에 출력된 모델 이름 중 하나로 바꿔야 함
model = genai.GenerativeModel(
    model_name="gemini-1.5-flash", 
    system_instruction=SYSTEM_PROMPT
)

# --- [2. 기능 모듈] ---

def load_memory():
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_memory(history):
    trimmed_history = history[-20:] if len(history) > 20 else history
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(trimmed_history, f, indent=2, ensure_ascii=False)

def read_repository_structure():
    structure = "Current Project Structure:\n"
    for root, dirs, files in os.walk("."):
        if ".git" in root or "__pycache__" in root: continue
        for file in files:
            path = os.path.join(root, file)
            structure += f"- {path}\n"
            if file.endswith((".py", ".md")) and "agent_brain.py" not in file:
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        content = f.read()
                        structure += f"  (Content Preview):\n{content[:300]}...\n"
                except: pass
    return structure

def extract_and_save_code(response_text):
    pattern = r"### FILE: (.*?)\n```\w*\n(.*?)```"
    matches = re.findall(pattern, response_text, re.DOTALL)
    saved_files = []
    for file_path, code_content in matches:
        file_path = file_path.strip()
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(code_content.strip())
        saved_files.append(file_path)
        print(f"💾 파일 저장: {file_path}")
    return saved_files

def run_tests():
    try:
        # pytest가 없거나 테스트 파일이 없으면 에러 나지 않게 처리
        result = subprocess.run(["pytest", "-v"], capture_output=True, text=True)
        return result.returncode == 0, result.stdout + result.stderr
    except FileNotFoundError:
        return False, "pytest가 설치되지 않았습니다."

def send_discord(msg):
    if DISCORD_WEBHOOK_URL:
        try:
            requests.post(DISCORD_WEBHOOK_URL, json={"content": msg})
        except: pass

# --- [3. 메인 로직] ---

def main():
    print("🚀 Nightly Agent 시작...")
    
    history_data = load_memory()
    repo_context = read_repository_structure()
    
    formatted_history = [{"role": h["role"], "parts": [h["text"]]} for h in history_data]
    chat = model.start_chat(history=formatted_history)
    
    task_prompt = f"""
    [현재 프로젝트 상태]
    {repo_context}

    [오늘의 미션]
    1. `tests/test_sample.py` 파일을 하나 만들어서 간단한 덧셈 테스트를 작성하세요. (TDD Red)
    2. `src/sample.py`에 덧셈 함수를 구현하세요. (Green)
    """
    
    print("🤖 AI 분석 및 코딩 중...")
    try:
        response = chat.send_message(task_prompt)
        print("✅ AI 응답 수신 완료")
    except Exception as e:
        print(f"❌ AI 요청 실패: {e}")
        send_discord(f"🚨 에러 발생: {e}")
        return # 에러 나면 종료

    saved_files = extract_and_save_code(response.text)
    
    status_msg = "작업 내역 없음"
    if saved_files:
        passed, log = run_tests()
        if passed:
            print("✅ 테스트 통과")
            status_msg = f"✅ 성공! 파일 {len(saved_files)}개 생성."
        else:
            print("❌ 테스트 실패 (첫 실행이라 정상일 수 있음)")
            status_msg = f"⚠️ 테스트 실패/파일 생성됨. ({len(saved_files)}개)"

    # 결과 저장
    new_history = []
    for msg in chat.history:
        text_parts = [part.text for part in msg.parts if hasattr(part, 'text')]
        if text_parts:
            new_history.append({"role": msg.role, "text": " ".join(text_parts)})
    
    save_memory(new_history)
    send_discord(f"🤖 **Nightly Report:**\n{status_msg}")
    print("🌙 작업 종료.")

if __name__ == "__main__":
    main()
