"""API 冒烟测试."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

os.environ.setdefault("HY3_API_BASE", "http://0.0.0.0:8002/v1")
os.environ.setdefault("HY3_MODEL_NAME", "hy3-gptq-int4")

from app.hy3_client import load_client_from_env

client = load_client_from_env()
msgs = [[{"role": "user", "content": "请计算 1+1=?"}]]
out = client.chat_generate(msgs, max_tokens=50)
print("API 输出:", out[0]["text"][:200])
