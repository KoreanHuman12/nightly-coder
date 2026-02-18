import os
import json
import time
import subprocess
import requests
from datetime import datetime

# --- [설정 및 상수] ---
# 가설 1 해결: 키 뒤에 붙은 공백/엔터를 강제로 삭제 (.strip)
raw_key = os.environ.get("GEMINI_API_KEY", "")
GEMINI_API_KEY = raw_key.strip() if raw_key else None

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
TODAY_BRANCH = f"nightly-{datetime.now().strftime('%Y-%m-%d')}"

# 가설 2 해결: 실패 시 시도할 모델 목록 (순서대로 시도)
MODELS_TO_TRY = [
    "gemini-1.5-flash",  # 1순위: 빠름
    "gemini-1.5-pro",    # 2순위: 똑똑함
    "gemini-pro",        # 3순위: 구형이지만 안정적
    "gemini-1.0-pro"     # 4순위: 호환성
]

# --- [핵심 기능: 스마트 연결] ---
def chat_with_gemini(messages):
    headers = {'Content-Type': 'application/json'}
    payload = {
        "contents": messages,
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 8000
        }
    }
    
    # 모델 목록을 순회하며 시도
    for model_name in MODELS_TO_TRY:
        api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_API_KEY}"
        
        print(f"📡 Connecting to model: {model_name}...")
        
        try:
            response = requests.post(api_url, headers=headers, json=payload, timeout=30)
            
            # 200이면 성공
            if response.status_code == 200:
                print(f"✅ Success with {model_name}!")
                data = response.json()
                try:
                    return data['candidates'][0]['content']['parts'][0]['text']
                except:
                    return "" # 빈 응답 예외처리

            # 404(모델 없음)나 500(서버 오류)이면 다음 모델 시도
            print(f"⚠️ Failed with {model_name} (Status: {response.status_code}). Trying next...")
            
            # 400/403은 키 문제일 확률이 높음 (하지만 혹시 모르니 계속 시도)
            if response.status_code in [400, 403]:
                print(f"🔍 Check API Key details: {response.text[:200]}")

        except Exception as e:
            print(f"❌ Connection Error with {model_name}: {e}")
        
        time.sleep(2) # 모델 변경 전 잠시 대기

    # 모든 모델 실패 시
    raise Exception("💀 All models failed. Please check your GEMINI_API_KEY in GitHub Secrets.")

# --- [Git 및 유틸리티] ---
def add_message(history, role, text):
    history.append({
        "role": "user" if role == "user" else "model",
        "parts": [{"text": text}]
    })
    return history

def setup_git_branch():
    print(f"🛡️ Git Safety: Checking out branch '{TODAY_BRANCH}'...")
    subprocess.run(["git", "config", "--global", "user.name", "Nightly AI"])
    subprocess.run(["git", "config", "--global", "user.email", "ai@nightly.com"])
    subprocess.run(["git", "checkout", "-b", TODAY_BRANCH])

def push_changes():
    print("📦 Git Push: Saving changes...")
    subprocess.run(["git", "add", "."])
    status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
    if not status.stdout.strip():
        print("🚫 No changes to push.")
        return False
    subprocess.run(["git", "commit", "-m", f"Nightly AI: Multi-Model Mode ({datetime.now().strftime('%H:%M')})"])
    subprocess.run(["git", "push", "origin", TODAY_BRANCH])
    return True

def read_repo():
    structure = "Project Structure:\n"
    for root, _, files in os.walk("."):
        if ".git" in root: continue
        for file in files:
            structure += f"- {os.path.join(root, file)}\n"
    return structure

def save_files(text):
    pattern = r"### FILE: (.*?)\n```(?:\w+)?\n(.*?)```"
    import re
    matches = re.findall(pattern, text, re.DOTALL)
    files = []
    for path, content in matches:
        path = path.strip()
        if not path: continue
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content.strip())
        files.append(path)
        print(f"💾 Saved: {path}")
    return files

def send_discord(msg):
    if DISCORD_WEBHOOK_URL:
        try: requests.post(DISCORD_WEBHOOK_URL, json={"content": msg})
        except: pass

# --- [메인 실행] ---
def main():
    print("🚀 Nightly Agent Started (Robust Mode)")
    
    if not GEMINI_API_KEY:
        print("💀 ERROR: 'GEMINI_API_KEY' is missing or empty!")
        return

    setup_git_branch()
    
    history = []
    system_prompt = """
    You are the Nightly Autonomous Architect.
    Process: 
    1. Plan (docs/PLAN.md) -> 2. Code (src/) -> 3. Test (tests/).
    Output format:
    ### FILE: path/filename
    ```python
    code
    ```
    """
    
    repo_info = read_repo()
    
    # 1단계: 계획
    print("🤔 Step 1: Planning...")
    msg1 = f"{system_prompt}\n\nContext:\n{repo_info}\n\nTask: Create docs/PLAN.md for code improvements."
    history = add_message(history, "user", msg1)
    res1 = chat_with_gemini(history)
    history = add_message(history, "model", res1)
    save_files(res1)
    
    # 2단계: 구현
    print("🛠️ Step 2: Coding...")
    msg2 = "Based on the plan, write the code and tests. Use strict TDD."
    history = add_message(history, "user", msg2)
    res2 = chat_with_gemini(history)
    save_files(res2)
    
    # 3단계: 문서화
    print("📚 Step 3: Documentation...")
    msg3 = "Update README.md based on changes."
    history = add_message(history, "user", msg3)
    res3 = chat_with_gemini(history)
    save_files(res3)

    if push_changes():
        send_discord(f"Nightly Report: Success on branch {TODAY_BRANCH}")
    else:
        send_discord("Nightly Report: No changes.")
        
    print("🌙 Job Done.")

if __name__ == "__main__":
    main()
