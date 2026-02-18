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

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
MEMORY_FILE = "agent_memory.json"

TODAY_BRANCH = f"nightly-{datetime.now().strftime('%Y-%m-%d')}"

genai.configure(api_key=GEMINI_API_KEY)

SYSTEM_PROMPT = """
당신은 Nightly Autonomous Architect입니다.
목표: 기존 코드를 분석하고 최적화하며 안전하게 기능을 추가하는 것입니다.

1. Plan-and-Solve: 코드를 짜기 전 docs/PLAN.md에 계획 작성.
2. Strict TDD: 테스트 코드 먼저 작성.
3. No Direct Shell: 위험한 쉘 명령어 금지.
4. Optimization: 알고리즘 최적화.
5. Documentation: README.md 업데이트.

출력 형식:
### FILE: 경로/파일명
```python
코드 내용
"""

model = genai.GenerativeModel(
model_name="gemini-2.0-flash",
system_instruction=SYSTEM_PROMPT
)
# --- [2. 핵심 기능: 불굴의 재시도 (30회)] ---

def send_message_with_retry(chat, prompt, max_retries=30):
    wait_time = 60 
    
    for attempt in range(max_retries):
        try:
            return chat.send_message(prompt)
        except exceptions.ResourceExhausted:
            print(f"⚠️ [Quota Exceeded] 구글이 막았습니다. {wait_time}초 대기... ({attempt+1}/{max_retries})")
            time.sleep(wait_time)
            wait_time = min(wait_time + 10, 300) # 대기 시간 점진적 증가 (최대 5분)
        except Exception as e:
            print(f"❌ 일시적 오류: {e}. 10초 뒤 재시도...")
            time.sleep(10)
    
    raise Exception("💀 30번 시도했으나 실패했습니다.")

# --- [3. Git 안전장치 (브랜치 관리)] ---

def setup_git_branch():
    print(f"🛡️ Git 안전장치 가동: '{TODAY_BRANCH}' 브랜치 생성 중...")
    subprocess.run(["git", "config", "--global", "user.name", "Nightly AI"])
    subprocess.run(["git", "config", "--global", "user.email", "ai@nightly.com"])
    
    # 브랜치 생성 및 이동 (이미 있으면 이동만)
    subprocess.run(["git", "checkout", "-b", TODAY_BRANCH])
    print(f"✅ 현재 작업 브랜치: {TODAY_BRANCH}")

def push_changes():
    print("📦 변경 사항을 Git에 저장 중...")
    subprocess.run(["git", "add", "."])
    
    # 변경 사항이 있는지 확인
    status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
    if not status.stdout.strip():
        print("🚫 변경된 내용이 없어 푸시하지 않습니다.")
        return False
        
    subprocess.run(["git", "commit", "-m", f"🤖 Nightly AI: Code Optimization & TDD Result ({datetime.now().strftime('%H:%M')})"])
    # 원격 브랜치로 푸시
    subprocess.run(["git", "push", "origin", TODAY_BRANCH])
    return True
# --- [4. 유틸리티 함수] ---

def read_repository_structure():
    structure = "Current Project Structure:\n"
    for root, dirs, files in os.walk("."):
        if ".git" in root or "__pycache__" in root: continue
        for file in files:
            path = os.path.join(root, file)
            structure += f"- {path}\n"
            if file.endswith((".py", ".md", ".txt")) and "agent_brain.py" not in file:
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        content = f.read()
                        structure += f"  (Preview):\n{content[:500]}...\n"
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
        return False, "pytest not found"

def send_discord(msg):
    if DISCORD_WEBHOOK_URL:
        try: requests.post(DISCORD_WEBHOOK_URL, json={"content": msg})
        except: pass

# --- [5. 메인 실행 로직] ---

def main():
    print("🚀 Nightly Autonomous Agent 시작 (Ultimate Mode)")
    setup_git_branch() 
    
    repo_context = read_repository_structure()
    chat = model.start_chat(history=[])
    
    # 1단계: 계획 수립
    print("🤔 1단계: 코드 분석 및 계획 수립 중...")
    plan_prompt = f"""
    [현재 프로젝트 상태]
    {repo_context}

    [임무]
    1. 현재 코드의 문제점이나 최적화가 필요한 부분을 찾으세요.
    2. 새로운 기능을 제안하거나 버그를 찾으세요.
    3. docs/PLAN.md 파일을 생성하여 상세 구현 계획을 작성하세요.
    """
    res1 = send_message_with_retry(chat, plan_prompt)
    extract_and_save_code(res1.text)
    
    # 2단계: TDD 및 구현
    print("🛠️ 2단계: TDD 기반 구현 및 최적화 중...")
    tdd_prompt = """
    위 계획에 따라 작업을 수행하세요.
    1. tests/ 폴더에 테스트 코드를 먼저 작성하세요.
    2. 테스트를 통과하도록 src/ 코드를 구현하세요.
    3. 구현된 코드의 알고리즘 복잡도를 검토하고 최적화하세요.
    """
    res2 = send_message_with_retry(chat, tdd_prompt)
    files = extract_and_save_code(res2.text)
    
    # 3단계: 검증 및 자가 수정
    status_msg = "작업 완료"
    if files:
        passed, log = run_tests()
        if passed:
            print("✅ 모든 테스트 통과!")
            status_msg = f"✅ 성공! (테스트 통과, {len(files)}개 파일 수정)"
        else:
            print("❌ 테스트 실패. 자가 수정 모드 진입...")
            fix_prompt = f"테스트 실패 로그:\n{log}\n코드를 수정하고 다시 제출하세요."
            res3 = send_message_with_retry(chat, fix_prompt)
            extract_and_save_code(res3.text)
            
            passed_retry, _ = run_tests()
            if passed_retry:
                status_msg = "⚠️ 1차 실패 후 수정 성공!"
            else:
                status_msg = "❌ 수정 실패. 사람의 검토가 필요합니다."

    # 4단계: 문서화
    print("📚 4단계: 문서화 진행 중...")
    doc_prompt = "변경된 내용을 바탕으로 README.md와 requirements.txt를 최신화하세요."
    res4 = send_message_with_retry(chat, doc_prompt)
    extract_and_save_code(res4.text)

    # 5단계: Git 푸시 및 보고
    if push_changes():
        final_report = f"""
        🤖 **Nightly Report (Ultimate Edition)**
        - **Branch:** `{TODAY_BRANCH}`
        - **Status:** {status_msg}
        - **Plan:** `docs/PLAN.md` 확인 요망
        - **Next Step:** GitHub에서 `Compare & pull request` 버튼을 눌러 승인(Merge)해주세요.
        """
        send_discord(final_report)
    else:
        send_discord("🤖 변경 사항이 없어 조기 종료합니다.")
        
    print("🌙 작업 종료.")

if __name__ == "__main__":
    main()  그러 이거야?
