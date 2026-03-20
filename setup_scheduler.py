"""
Run this once to register a daily Windows Task Scheduler job.
The task will run main.py every day at 06:30 AM.
"""

import subprocess
import sys
from pathlib import Path


TASK_NAME = "InstagramContentIdeasGenerator"
SCHEDULE_TIME = "06:30"  # 24-hour format


def create_task():
    python_exe = sys.executable
    script_path = Path(__file__).parent.resolve() / "main.py"

    if not script_path.exists():
        print(f"ERROR: main.py not found at {script_path}")
        return

    # schtasks command — runs daily at SCHEDULE_TIME
    cmd = [
        "schtasks", "/Create",
        "/TN", TASK_NAME,
        "/TR", f'"{python_exe}" "{script_path}"',
        "/SC", "DAILY",
        "/ST", SCHEDULE_TIME,
        "/F",          # overwrite if task already exists
        "/RL", "HIGHEST",  # run with highest privileges
    ]

    print(f"Creating scheduled task: {TASK_NAME}")
    print(f"  Script : {script_path}")
    print(f"  Python : {python_exe}")
    print(f"  Time   : {SCHEDULE_TIME} daily")
    print()

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode == 0:
        print("Task created successfully!")
        print("It will run every day at", SCHEDULE_TIME)
        print()
        print("Useful commands:")
        print(f"  Run now  : schtasks /Run /TN \"{TASK_NAME}\"")
        print(f"  Delete   : schtasks /Delete /TN \"{TASK_NAME}\" /F")
        print(f"  Check    : schtasks /Query /TN \"{TASK_NAME}\"")
    else:
        print("ERROR creating task:")
        print(result.stderr or result.stdout)
        print()
        print("Try running this script as Administrator.")


if __name__ == "__main__":
    create_task()
