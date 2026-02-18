import os
import re
import time
import subprocess
import requests
from datetime import datetime

# --- [설정값] ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
TODAY_BRANCH = f"nightly-{datetime.now().strftime('%Y-%m-%d')}"
API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"

# --- [핵심 기능: 라이브러리 없이 직접 연결] ---
def chat_with_gemini(messages):
    headers = {'Content-Type': 'application/json'}
    payload = {
        "contents": messages,
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 8000
        }
    }

    for attempt in range(3):
        try:
            response = requests.post(API_URL, headers=headers, json=payload, timeout=60)

            if response.status_code in (400, 403):
                print(f"🚨 [CRITICAL] API Key Error! Status: {response.status_code}")
                print(f"Details: {response.text}")
                raise Exception("API Key is invalid or expired.")

            if response.status_code == 200:
                data = response.json()
                try:
                    return data['candidates'][0]['content']['parts'][0]['text']
                except (KeyError, IndexError):
                    return ""

            print(f"⚠️ API Error (Attempt {attempt+1}): {response.status_code}")
            time.sleep(5)

        except Exception as e:
            print(f"❌ Connection Error: {e}")
            if attempt == 2:
                raise
            time.sleep(5)

    raise Exception("💀 Failed to connect to Gemini after 3 attempts.")


# --- [채팅 기록 관리자] ---
def add_message(history, role, text):
    history.append({
        "role": "user" if role == "user" else "model",
        "parts": [{"text": text}]
    })
    return history


# --- [Git 및 유틸리티] ---
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
    subprocess.run(["git", "commit", "-m", f"Nightly AI: REST API Mode ({datetime.now().strftime('%H:%M')})"])
    subprocess.run(["git", "push", "origin", TODAY_BRANCH])
    return True

def read_repo():
    structure = "Project Structure:\n"
    for root, _, files in os.walk("."):
        if ".git" in root:
            continue
        for file in files:
            structure += f"- {os.path.join(root, file)}\n"
    return structure

def save_files(text):
    pattern = r"### FILE: (.*?)\n```(?:\w+)?\n(.*?)```"
    matches = re.findall(pattern, text, re.DOTALL)
    files = []
    for path, content in matches:
        path = path.strip()
        # ★ 버그 수정 1: dirname이 빈 문자열이면 makedirs 에러 발생 → 방어 처리
        dir_name = os.path.dirname(path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content.strip())
        files.append(path)
        print(f"💾 Saved: {path}")
    return files

def send_discord(msg):
    if DISCORD_WEBHOOK_URL:
        try:
            requests.post(DISCORD_WEBHOOK_URL, json={"content": msg})
        except Exception:
            pass


# --- [메인 실행] ---
def main():
    print("🚀 Nightly Agent Started (Direct REST API Mode)")

    if not GEMINI_API_KEY:
        print("💀 ERROR: 'GEMINI_API_KEY' is missing in GitHub Secrets!")
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
    msg1 = f"{system_prompt}\n\nContext:\n{repo_info}\n\nTask: Create docs/PLAN.md for improvements."
    history = add_message(history, "user", msg1)
    res1 = chat_with_gemini(history)
    history = add_message(history, "model", res1)  # ★ 버그 수정 2: 응답을 기록에 추가해야 다음 대화가 이어짐
    save_files(res1)

    # 2단계: 구현
    print("🛠️ Step 2: Coding...")
    msg2 = "Based on the plan, write the code and tests. Use strict TDD."
    history = add_message(history, "user", msg2)
    res2 = chat_with_gemini(history)
    history = add_message(history, "model", res2)  # ★ 버그 수정 3: 동일하게 응답 기록 누락됐던 부분
    save_files(res2)

    # 3단계: 문서화
    print("📚 Step 3: Documentation...")
    msg3 = "Update README.md based on changes."
    history = add_message(history, "user", msg3)
    res3 = chat_with_gemini(history)
    history = add_message(history, "model", res3)
    save_files(res3)

    if push_changes():
        send_discord(f"Nightly Report: Success on branch {TODAY_BRANCH}")
    else:
        send_discord("Nightly Report: No changes.")

    print("🌙 Job Done.")


if __name__ == "__main__":
    main()
