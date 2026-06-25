"""
日志重定向模块。
直接 import 即可自动生效：所有 print 输出照常显示在终端，并缓存在内存中。
**默认不写文件**，只有外部主动调用 logger_setup.save_log() 时才落盘，用于复现 bug。

日志保存位置：
- 开发时：脚本所在目录下的 logs/
- 打包后（PyInstaller）：exe 所在目录下的 logs/

用法：
    import logger_setup            # 放在 main.py 最开头
    ...
    except Exception as e:
        logger_setup.save_log(f"xxx 出错: {e}")   # 需要时主动保存
"""
import sys
import os
import threading
from collections import deque
from datetime import datetime

# 内存中保留的最近输出上限（字符数），避免长时间运行占用过多内存
_BUFFER_MAX_CHARS = 1_000_000

_lock = threading.Lock()
_buffer = deque()      # 最近输出的分片
_buffer_chars = 0      # 当前缓冲区字符总数

def _get_app_dir():
    """获取程序所在目录：打包后是exe目录，开发时是脚本所在目录"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.abspath(__file__))


def _buffer_add(text):
    """把一段输出加入内存缓冲，超出上限时丢弃最旧的内容"""
    global _buffer_chars
    _buffer.append(text)
    _buffer_chars += len(text)
    while _buffer_chars > _BUFFER_MAX_CHARS and len(_buffer) > 1:
        _buffer_chars -= len(_buffer.popleft())


def save_log(reason=""):
    """
    把当前内存缓冲里的输出写入日志文件，返回文件路径。
    供外部在出错时主动调用。
    """
    log_dir = os.path.join(_get_app_dir(), "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_filename = os.path.join(
        log_dir,
        f"{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log"
    )
    with _lock:
        content = "".join(_buffer)
    with open(log_filename, "w", encoding="utf-8") as f:
        if reason:
            f.write(f"===== 保存原因: {reason} =====\n")
        f.write(content)
    # 提示走原始终端流，避免再次进入缓冲
    sys.__stderr__.write(f"[logger_setup] 已保存日志: {log_filename}\n")
    return log_filename


class _Tee:
    """输出照常写终端，同时存入内存缓冲"""

    def __init__(self, real):
        self.real = real

    def write(self, text):
        self.real.write(text)
        self.real.flush()
        with _lock:
            _buffer_add(text)

    def flush(self):
        self.real.flush()

    def isatty(self):
        # 一些库（如 uvicorn）会检查 stdout 是否是终端，来决定是否输出颜色等
        try:
            return self.real.isatty()
        except Exception:
            return False

    def fileno(self):
        # 某些库需要拿到底层文件描述符，转发给原始终端流
        return self.real.fileno()


def _setup():
    # 幂等：即使模块被以不同路径重复导入，也只包一层
    if isinstance(sys.stdout, _Tee):
        return
    sys.stdout = _Tee(sys.stdout)
    sys.stderr = _Tee(sys.stderr)
    print("[logger_setup] 日志缓存已就绪：调用 save_log() 时才落盘")


# 模块被 import 时自动执行一次
_setup()
