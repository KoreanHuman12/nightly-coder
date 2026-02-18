import os
import re
import time
import subprocess
import requests
import warnings
import google.generativeai as genai
from google.api_core import exceptions
from datetime import datetime

# --- [설정 및 경고 무시] ---
warnings.filterwarnings("ignore")

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
TODAY_BRANCH = f"nightly-{datetime.now().strftime('%Y-%m-%d')}"

# API 키 공백 제거 안전장치
if GEMINI_API_KEY:
    GEMINI_API_KEY = GEMINI_API_KEY.strip()

genai.configure(api_key=GEMINI_API_KEY)

# --- [AI 페르소나] ---
SYSTEM_PROMPT = """
You are the 'Nightly Autonomous Architect'.
Your goal is to write clean, safe, and optimized code using a Strict TDD approach.
[Core Process]
1. Plan-and-Solve: Create 'docs/PLAN.md' first.
2. Strict TDD: Write failing tests in 'tests/' first, then code in 'src/'.
3. Git Safety: Work on branch. NEVER push to main directly.
4. Safety Guardrail: No dangerous commands (rm -rf).
5. Auto-Documentation: Update README.md after work.
[Output Format]
### FILE: path/to/filename.ext
```python
# content
```
"""

# --- [모델 설정] ---
model = genai.GenerativeModel(
    model_name="gemini-1.5-flash",
    system_instruction=SYSTEM_PROMPT
)


# --- [핵심 함수] ---

def send_message_with_retry(chat, prompt, max_retries=3):
    print("🤖 AI Thinking...")
    for attempt in range(max_retries):
        try:
            return chat.send_message(prompt)
        except Exception as e:
            error_msg = str(e)
            print(f"⚠️ Error (Attempt {attempt+1}): {error_msg}")

            if "404" in error_msg or "400" in error_msg or "API key" in error_msg:
                raise Exception("🚨 API KEY ERROR: Please check your key at aistudio.google.com")

            time.sleep(5)

    raise Exception("💀 Failed after 3 retries. Check GitHub Actions logs.")


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
    subprocess.run(["git", "commit", "-m", f"Nightly AI: TDD Mode ({datetime.now().strftime('%H:%M')})"])
    subprocess.run(["git", "push", "origin", TODAY_BRANCH])
    return True


def read_repository_structure():
    structure = "Current Project Structure:\n"
    for root, dirs, files in os.walk("."):
        if ".git" in root or "__pycache__" in root:
            continue
        for file in files:
            path = os.path.join(root, file)
            structure += f"- {path}\n"
    return structure


def extract_and_save_code(response_text):
    pattern = r"### FILE: (.*?)\n```(?:\w+)?\n(.*?)```"
    matches = re.findall(pattern, response_text, re.DOTALL)
    saved_files = []
    for file_path, code_content in matches:
        file_path = file_path.strip()
        if not file_path:
            continue
        # ★ 버그 수정: dirname이 빈 문자열이면 makedirs 에러 → 방어 처리
        dir_name = os.path.dirname(file_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(code_content.strip())
        saved_files.append(file_path)
        print(f"💾 Saved: {file_path}")
    return saved_files


def run_tests():
    try:
        result = subprocess.run(["pytest", "-v"], capture_output=True, text=True)
        return result.returncode == 0, result.stdout + result.stderr
    except FileNotFoundError:
        return False, "pytest not found"


def send_discord(msg):
    if DISCORD_WEBHOOK_URL:
        try:
            requests.post(DISCORD_WEBHOOK_URL, json={"content": msg})
        except Exception:
            pass


# --- [메인 실행 로직] ---

def main():
    print("🚀 Nightly Autonomous Agent Started (Final Clean Version)")

    if not GEMINI_API_KEY:
        print("💀 CRITICAL: GEMINI_API_KEY is missing!")
        return

    setup_git_branch()

    repo_context = read_repository_structure()
    try:
        chat = model.start_chat(history=[])

        # 1. Plan
        print("🤔 Step 1: Planning...")
        res1 = send_message_with_retry(chat, f"Analyze this structure and create docs/PLAN.md:\n{repo_context}")
        extract_and_save_code(res1.text)

        # 2. Code
        print("🛠️ Step 2: Coding...")
        res2 = send_message_with_retry(chat, "Implement the code and tests based on the plan using TDD.")
        files = extract_and_save_code(res2.text)

        # 3. Validation
        status_msg = "Work Complete"
        if files:
            passed, log = run_tests()
            if passed:
                status_msg = f"Success! ({len(files)} files)"
            else:
                print("❌ Tests Failed. Fixing...")
                res3 = send_message_with_retry(chat, f"Tests failed:\n{log}\nFix the code.")
                extract_and_save_code(res3.text)
                passed_retry, _ = run_tests()
                status_msg = "Fixed and Verified" if passed_retry else "Fix Failed"

        # 4. Documentation
        print("📚 Step 4: Documentation...")
        res4 = send_message_with_retry(chat, "Update README.md.")
        extract_and_save_code(res4.text)

        if push_changes():
            send_discord(f"Nightly Report: {status_msg}")
        else:
            send_discord("No changes.")

    except Exception as e:
        print(f"\n❌ FATAL ERROR: {e}")
        print("👉 Please verify your API Key at aistudio.google.com")
        send_discord(f"Nightly Agent Failed: {e}")

    print("🌙 Job Done.")


if __name__ == "__main__":
    main()
