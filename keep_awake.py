"""防止电脑休眠 — 每10分钟移动一下鼠标。

用法:
    python keep_awake.py

按 Ctrl+C 停止。
"""

import ctypes
import time
import sys

# Windows API: 模拟鼠标移动（相对移动 0,0 — 不可见但能阻止休眠）
MOUSEEVENTF_MOVE = 0x0001

def move_mouse():
    ctypes.windll.user32.mouse_event(MOUSEEVENTF_MOVE, 1, 0, 0, 0)
    ctypes.windll.user32.mouse_event(MOUSEEVENTF_MOVE, -1, 0, 0, 0)

def main():
    interval = 600  # 10分钟
    print(f"防休眠已启动 — 每 {interval//60} 分钟移动一次鼠标")
    print("按 Ctrl+C 停止")
    try:
        while True:
            move_mouse()
            now = time.strftime("%H:%M:%S")
            print(f"[{now}] 已移动鼠标，下次: {interval//60} 分钟后", end="\r")
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n已停止")

if __name__ == "__main__":
    main()
