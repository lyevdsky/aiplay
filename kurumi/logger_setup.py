"""
日志重定向模块。
直接 import 即可自动生效：所有 print 输出会同时显示在终端，并写入日志文件。

日志保存位置：
- 开发时：脚本所在目录下的 logs/
- 打包后（PyInstaller）：exe 所在目录下的 logs/

用法：
    import logger_setup  # 放在 main.py 最开头即可，之后无需再管
"""
# TODO 仅在出现error时保存相关内容供复现bug就可以了
import sys
import os
from datetime import datetime


def _get_app_dir():
    """获取程序所在目录：打包后是exe目录，开发时是脚本所在目录"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.abspath(__file__))


class _Tee:
    """将输出同时写入多个流（如终端 + 文件）"""

    def __init__(self, *files):
        self.files = files

    def write(self, text):
        for f in self.files:
            f.write(text)
            f.flush()

    def flush(self):
        for f in self.files:
            f.flush()

    def isatty(self):
        # 一些库（如 uvicorn）会检查 stdout 是否是终端，来决定是否输出颜色等
        # 只要原始终端流支持，就认为支持；文件流不影响这个判断
        for f in self.files:
            if hasattr(f, "isatty"):
                try:
                    if f.isatty():
                        return True
                except Exception:
                    pass
        return False

    def fileno(self):
        # 某些库需要拿到底层文件描述符，转发给第一个支持的流
        for f in self.files:
            if hasattr(f, "fileno"):
                try:
                    return f.fileno()
                except Exception:
                    pass
        raise OSError("No underlying fileno available")


def _setup():
    log_dir = os.path.join(_get_app_dir(), "logs")
    os.makedirs(log_dir, exist_ok=True)

    log_filename = os.path.join(
        log_dir,
        f"{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log"
    )

    log_file = open(log_filename, "a", encoding="utf-8")

    sys.stdout = _Tee(sys.stdout, log_file)
    sys.stderr = _Tee(sys.stderr, log_file)

    print(f"[logger_setup] 日志保存路径: {log_filename}")


# 模块被 import 时自动执行一次
_setup()
