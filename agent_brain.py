import os
import re
import time
import subprocess
import requests
import google.generativeai as genai
from google.api_core import exceptions
from datetime import datetime

# --- [설정 및 상수] ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
TODAY_BRANCH = f"nightly-{datetime.now().strftime('%Y-%m-%d')}"

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

model = genai.GenerativeModel(
    model_name="gemini-1.5-flash",
    system_instruction=SYSTEM_PROMPT
)


# --- [핵심 함수] ---

def send_message_with_retry(chat, prompt, max_retries=3):
    wait_time = 10
    for attempt in range(max_retries):
        try:
            return chat.send_message(prompt)
        except exceptions.ResourceExhausted:
            print(f"⚠️ Quota Exceeded. Waiting {wait_time}s... ({attempt+1}/{max_retries})")
            time.sleep(wait_time)
            wait_time += 10
        except Exception as e:
            print(f"❌ Error: {e}. Waiting 10s...")
            time.sleep(10)
    raise Exception("💀 Failed after 3 retries. Check API Key or Model.")


def setup_git_branch():
    print(f"🛡️ Git Safety: Checking out branch '{TODAY_BRANCH}'...")
    subprocess.run(["git", "config", "--global", "user.name", "Nightly AI"])
    subprocess.run(["git", "config", "--global", "user.email", "ai@nightly.com"])
    subprocess.run(["git", "checkout", "-b", TODAY_BRANCH])
    print(f"✅ Switched to branch: {TODAY_BRANCH}")


def push_changes():
    print("📦 Git Push: Saving changes...")
    subprocess.run(["git", "add", "."])
    status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
    if not status.stdout.strip():
        print("🚫 No changes to push.")
        return False
    commit_msg = f"Nightly AI: TDD & Optimization ({datetime.now().strftime('%H:%M')})"
    subprocess.run(["git", "commit", "-m", commit_msg])
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
            if file.endswith((".py", ".md", ".txt")) and "agent_brain" not in file:
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        content = f.read()
                    structure += f"  (Preview):\n{content[:500]}...\n"
                except Exception:
                    pass
    return structure


def extract_and_save_code(response_text):
    pattern = r"### FILE: (.*?)\n```(?:\w+)?\n(.*?)```"
    matches = re.findall(pattern, response_text, re.DOTALL)
    saved_files = []
    for file_path, code_content in matches:
        file_path = file_path.strip()
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
    print("🚀 Nightly Autonomous Agent Started (Stable 1.5 Mode)")
    setup_git_branch()

    repo_context = read_repository_structure()
    chat = model.start_chat(history=[])

    # 1. Plan Phase
    print("🤔 Step 1: Planning...")
    plan_prompt = f"""
[Project Context]
{repo_context}

[Mission]
1. Analyze the structure.
2. Identify optimization points.
3. Create 'docs/PLAN.md' with a TDD plan.
"""
    res1 = send_message_with_retry(chat, plan_prompt)
    extract_and_save_code(res1.text)

    # 2. TDD & Coding Phase
    print("🛠️ Step 2: TDD Cycle...")
    tdd_prompt = """
Execute the plan.
1. Write failing tests in 'tests/' folder.
2. Implement code in 'src/' to pass tests.
3. Optimize complexity.
"""
    res2 = send_message_with_retry(chat, tdd_prompt)
    files = extract_and_save_code(res2.text)

    # 3. Validation
    status_msg = "Work Complete"
    if files:
        passed, log = run_tests()
        if passed:
            print("✅ All Tests Passed!")
            status_msg = f"Success! ({len(files)} files modified)"
        else:
            print("❌ Tests Failed. Self-Repairing...")
            fix_prompt = f"Tests failed:\n{log}\nFix the code and tests."
            res3 = send_message_with_retry(chat, fix_prompt)
            extract_and_save_code(res3.text)

            passed_retry, _ = run_tests()
            if passed_retry:
                status_msg = "⚠️ Success after fix!"
            else:
                status_msg = "❌ Fix failed. Human review needed."

    # 4. Documentation
    print("📚 Step 4: Documentation...")
    doc_prompt = "Update 'README.md' based on changes."
    res4 = send_message_with_retry(chat, doc_prompt)
    extract_and_save_code(res4.text)

    # 5. Push
    if push_changes():
        final_report = f"""
**Nightly Report**
- Branch: `{TODAY_BRANCH}`
- Status: {status_msg}
- Plan: `docs/PLAN.md`
"""
        send_discord(final_report)
    else:
        send_discord("🤖 No changes made.")

    print("🌙 Job Done.")


if __name__ == "__main__":
    main()
