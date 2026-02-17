import os
import re
import json
import time
import subprocess
import requests
import glob
import google.generativeai as genai
from google.api_core import exceptions
from datetime import datetime

# --- [1. 설정 및 초기화] ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
MEMORY_FILE = "agent_memory.json"
DECISION_LOG = "docs/decisions.md"

# API 키 설정
genai.configure(api_key=GEMINI_API_KEY)

# 페르소나: 포기를 모르는 집요한 수석 엔지니어
SYSTEM_PROMPT = """
당신은 'Nightly Autonomous Agent'입니다.
1. [Strict TDD]: 실패하는 테스트(Red) -> 구현(Green) -> 리팩토링 순서를 지키세요.
2. [Format]: 코드는 `### FILE: 경로/파일명` 형식으로 작성하세요.
3. [Persistence]: 절대 포기하지 마세요. 복잡한 문제는 단계별로 해결하세요.
"""

# ★★★ 최고 성능 Gemini 2.0 (재시도 로직으로 에러 극복) ★★★
model = genai.GenerativeModel(
    model_name="gemini-2.0-flash", 
    system_instruction=SYSTEM_PROMPT
)

# --- [2. 핵심 기능: 불멸의 대화 함수] ---

def send_message_with_retry(chat, prompt, max_retries=10):
    """
    에러가 나면 죽지 않고 기다렸다가 다시 시도하는 좀비 함수
    429(Too Many Requests)가 뜨면 60초씩 쉽니다.
    """
    wait_time = 60 # 대기 시간 (초)
    
    for attempt in range(max_retries):
        try:
            return chat.send_message(prompt)
        except exceptions.ResourceExhausted:
            # 429 에러(사용량 초과) 발생 시
            print(f"⚠️ [사용량 초과] 구글이 막았습니다. {wait_time}초 뒤에 다시 뚫습니다... (시도 {attempt+1}/{max_retries})")
            time.sleep(wait_time)
            wait_time += 30 # 기다리는 시간을 점점 늘림 (60초 -> 90초 -> 120초...)
        except Exception as e:
            # 다른 알 수 없는 에러
            print(f"❌ 알 수 없는 에러: {e}. 10초 뒤 재시도...")
            time.sleep(10)
    
    raise Exception("💀 10번 시도했으나 실패했습니다. 구글 서버가 완전히 막힌 것 같습니다.")

# --- [3. 보조 기능 모듈] ---

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
        result = subprocess.run(["pytest", "-v"], capture_output=True, text=True)
        return result.returncode == 0, result.stdout + result.stderr
    except FileNotFoundError:
        return False, "pytest가 설치되지 않았습니다."

def send_discord(msg):
    if DISCORD_WEBHOOK_URL:
        try:
            requests.post(DISCORD_WEBHOOK_URL, json={"content": msg})
        except: pass

# --- [4. 메인 로직] ---

def main():
    print("🚀 Nightly Agent 시작 (불멸 모드)...")
    
    history_data = load_memory()
    repo_context = read_repository_structure()
    
    formatted_history = [{"role": h["role"], "parts": [h["text"]]} for h in history_data]
    chat = model.start_chat(history=formatted_history)
    
    # 작업 지시
    task_prompt = f"""
    [현재 프로젝트 상태]
    {repo_context}

    [오늘의 미션]
    1. 프로젝트 상태를 분석하고, '기능 추가' 또는 '버그 수정' 또는 '리팩토링' 중 가장 필요한 작업을 스스로 결정하세요.
    2. [TDD]: 테스트 코드를 먼저 작성하세요.
    3. [Implement]: 기능을 구현하세요.
    """
    
    print("🤖 AI 분석 및 코딩 중...")
    
    # ★ 여기서 그냥 send_message가 아니라 '불멸의 함수'를 씁니다.
    try:
        response = send_message_with_retry(chat, task_prompt)
        print("✅ AI 응답 수신 완료")
    except Exception as e:
        print(f"❌ 최종 실패: {e}")
        send_discord(f"🚨 에러 발생 (재시도 실패): {e}")
        return

    saved_files = extract_and_save_code(response.text)
    
    status_msg = "작업 내역 없음"
    if saved_files:
        passed, log = run_tests()
        if passed:
            print("✅ 테스트 통과")
            status_msg = f"✅ 성공! (Gemini 2.0 사용)\n파일 {len(saved_files)}개 생성/수정."
        else:
            print("❌ 테스트 실패. 자가 수정 시도...")
            # 수정할 때도 재시도 로직 사용
            fix_prompt = f"테스트 실패 로그:\n{log}\n코드를 수정하세요."
            try:
                response = send_message_with_retry(chat, fix_prompt)
                extract_and_save_code(response.text)
                status_msg = f"⚠️ 1차 실패 후 자가 수정 완료. ({len(saved_files)}개 파일)"
            except:
                status_msg = "❌ 자가 수정 중 멈춤."

    # 결과 저장
    new_history = []
    for msg in chat.history:
        text_parts = [part.text for part in msg.parts if hasattr(part, 'text')]
        if text_parts:
            new_history.append({"role": msg.role, "text": " ".join(text_parts)})
    
    save_memory(new_history)
    send_discord(f"🤖 **Nightly Report (Gemini 2.0):**\n{status_msg}")
    print("🌙 작업 종료.")

if __name__ == "__main__":
    main()
