"""远程部署测试脚本"""
import subprocess
import sys

HOST = "47.113.118.5"
USER = "root"
PASS = "i-wz9i16mpyemrq8jmb31m"

PYTHON_CMD = """
cd /root/midline_strategy
git pull
python3 -c '
from data_fetcher import refresh_trading_pool, get_trading_pool
pool = refresh_trading_pool()
print("全市场股票数量:", len(pool))
print(pool.head().to_string())
'
"""

# Write a temp batch script for the password
import os
import tempfile

bat_path = os.path.join(tempfile.gettempdir(), "ssh_pass.bat")
with open(bat_path, "w") as f:
    f.write(f"@echo {PASS}\n")

os.environ["SSH_ASKPASS"] = bat_path
os.environ["SSH_ASKPASS_REQUIRE"] = "force"

# Run SSH without TTY so it uses SSH_ASKPASS
result = subprocess.run(
    [
        "C:\\Windows\\System32\\OpenSSH\\ssh.exe",
        "-o", "StrictHostKeyChecking=no",
        "-o", "BatchMode=no",
        f"{USER}@{HOST}",
        PYTHON_CMD
    ],
    capture_output=True,
    text=True,
    timeout=120,
    # Don't allocate a TTY, so SSH uses SSH_ASKPASS
    # On Windows, we need to ensure no console is attached
    creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0,
)

print("STDOUT:", result.stdout)
print("STDERR:", result.stderr)
print("EXIT:", result.returncode)
