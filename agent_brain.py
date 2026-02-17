import os
import re
import json
import subprocess
import requests
import glob
import google.generativeai as genai
from datetime import datetime

# --- [설정 및 초기화] ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
MEMORY_FILE = "agent_memory.json"
DECISION_LOG = "docs/decisions.md"

genai.configure(api_key=GEMINI_API_KEY)

# 페르소나: TDD, 최적화, 시각적 디버깅을 수행하는 수석 엔지니어
SYSTEM_PROMPT = """
당신은 'Nightly Autonomous Agent'입니다. 당신의 목표는 최고의 코드 품질을 유지하는 것입니다.
다음 원칙을 철저히 지키세요:
1. [Strict TDD]: 기능 구현 전, 반드시 '실패하는 테스트(Red)'를 먼저 작성하세요.
2. [Visual Debugging]: 제공된 이미지가 있다면 UI 버그를 분석하세요.
3. [Optimization]: 코드가 작동하더라도 시간 복잡도를 줄일 방법이 있다면 리팩토링하세요.
4. [File Format]: 코드는 반드시 `### FILE: 경로/파일명` 형식으로 작성하세요.
5. [Context]: 기존 파일 구조를 파악하고, 불필요한 중복 생성을 피하세요.
"""

model = genai.GenerativeModel(
    model_name="gemini-pro", 
    system_instruction=SYSTEM_PROMPT
)

# --- [기능 모듈] ---

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

def get_visual_context():
    image_files = glob.glob("*.png") + glob.glob("*.jpg") + glob.glob("screenshots/*.png")
    images = []
    if image_files:
        print(f"👁️ 시각 데이터 발견: {len(image_files)}개")
        for img_path in image_files[:3]:
            img = genai.upload_file(img_path)
            images.append(img)
    return images

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
        requests.post(DISCORD_WEBHOOK_URL, json={"content": msg})

# --- [메인 로직] ---

def main():
    print("🚀 Nightly Agent 시작...")
    
    history_data = load_memory()
    repo_context = read_repository_structure()
    images = get_visual_context()
    
    formatted_history = [{"role": h["role"], "parts": [h["text"]]} for h in history_data]
    chat = model.start_chat(history=formatted_history)
    
    task_prompt = f"""
    [현재 프로젝트 상태]
    {repo_context}

    [오늘의 미션]
    1. 파일 구조를 분석하고, 테스트가 없거나 부족한 핵심 기능을 찾으세요.
    2. [TDD]: 먼저 '실패하는 테스트 코드'를 작성하세요.
    3. [Implementation]: 테스트를 통과하는 기능을 구현하세요.
    4. [Refactor]: 구현된 코드의 효율성을 검토하고 최적화하세요.
    5. 만약 이미지가 제공되었다면, UI/UX 관점에서 버그를 찾고 수정하세요.
    """
    
    print("🤖 AI 분석 및 코딩 중...")
    inputs = [task_prompt] + images if images else [task_prompt]
    response = chat.send_message(inputs)
    
    saved_files = extract_and_save_code(response.text)
    
    status_msg = "작업 내역 없음"
    if saved_files:
        for attempt in range(1, 4):
            passed, log = run_tests()
            if passed:
                print(f"✅ 테스트 통과 (시도 {attempt}회)")
                status_msg = f"✅ 성공! (파일 {len(saved_files)}개 생성/수정, 테스트 통과)"
                break
            else:
                print(f"❌ 테스트 실패 (시도 {attempt}회). 수정 중...")
                fix_prompt = f"테스트 실패 로그:\n{log}\n코드를 수정하고 최적화하세요."
                response = chat.send_message(fix_prompt)
                extract_and_save_code(response.text)
        else:
            status_msg = "⚠️ 3회 시도 후에도 테스트 실패. 사람의 개입 필요."

    adr_prompt = "오늘의 작업 내용을 docs/decisions.md에 추가할 마크다운 형식으로 요약해줘."
    adr_res = chat.send_message(adr_prompt)
    
    os.makedirs("docs", exist_ok=True)
    with open(DECISION_LOG, "a", encoding="utf-8") as f:
        f.write(f"\n## {datetime.now().strftime('%Y-%m-%d Report')}\n{adr_res.text}\n")

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
