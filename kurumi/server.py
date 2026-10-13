import logger_setup
import asyncio
import os
import threading
import time
import traceback

from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse
import uvicorn

from game import Game
from screenshot import save_img_q
from logger_setup import save_log

app = FastAPI()
clients = set()
loop = None

# ---- game 控制状态（主线程与 server 线程共享）----
start_event = threading.Event()   # API 置位 -> 主线程开始一局
status = "idle"                   # idle | running | error
last_error = None                 # 最近一次异常信息
current_game = None               # 当前正在跑的 Game 实例（供 stop / save 接口用）
state_lock = threading.Lock()


@app.get("/")
def index():
    with open("kurumi_overlay.html", "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    clients.add(websocket)
    try:
        await websocket.receive_text()  # 保持连接
    finally:
        clients.remove(websocket)

@app.post("/game/start")
def game_start():
    with state_lock:
        if status == "running":
            return {"ok": False, "status": status, "msg": "游戏已在运行"}
        start_event.set()
        return {"ok": True, "status": "starting"}


@app.post("/game/stop")
def game_stop():
    """中断当前对局：置停止标志让 game.main 下一轮退出、回收 watcher，
    supervisor 随后自动回到 idle。没有在跑的游戏则无操作。"""
    with state_lock:
        game = current_game if status == "running" else None
    if game is None:
        return {"ok": False, "status": status, "msg": "当前没有在运行的游戏"}
    game.stop()
    return {"ok": True, "status": "stopping"}


@app.post("/game/save")
def game_save():
    """保存现场：把 watcher 的每次 put 记录与最近截图落盘，便于事后排查。
    不中断游戏，可在对局进行中随时调用。"""
    with state_lock:
        game = current_game
    if game is None:
        return {"ok": False, "status": status, "msg": "当前没有在运行的游戏"}
    try:
        log_path = game.watcher.save_log()
        save_img_q()
    except Exception as e:
        return {"ok": False, "msg": f"保存失败: {e}"}
    return {"ok": True, "log": log_path}


@app.get("/game/status")
def game_status():
    with state_lock:
        return {"status": status, "last_error": last_error}


def send_message(data: dict):
    for client in clients.copy():
        asyncio.run_coroutine_threadsafe(client.send_json(data), loop)


def start_server():
    global loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    config = uvicorn.Config(app, port=5500, loop="asyncio")
    server = uvicorn.Server(config)
    loop.run_until_complete(server.serve())


def _set_status(new_status, error=None):
    global status, last_error
    with state_lock:
        status = new_status
        last_error = error


def run_one_game():
    """在主线程跑一局，异常被捕获后存图并记录，不向上抛出。"""
    global current_game
    game = None
    try:
        game = Game(listener=lambda data: send_message(data))
        with state_lock:
            current_game = game
        print('run one game')
        game.start()
    except Exception as e:
        send_message({ 'type': 'error' })
        err_text = f"{type(e).__name__}: {e}"
        print(f"[SERVER] 游戏异常，已捕获，进程继续运行：{err_text}")
        traceback.print_exc()
        save_log()
        return err_text
    finally:
        with state_lock:
            current_game = None
    return None


# 服务器放子线程
thread = threading.Thread(target=start_server, daemon=True)
thread.start()

# 等待服务器启动
time.sleep(3)

# 主线程跑 supervisor：等 API 发来启动信号 -> 跑一局 -> 回到空闲
print("[SERVER] 就绪，等待 POST /game/start 启动游戏")
try:
    while True:
        # 带超时轮询，否则主线程会卡在 C 级锁里，Ctrl+C 无法生效
        if not start_event.wait(timeout=0.5):
            continue
        start_event.clear()
        _set_status("running")

        err = run_one_game()

        if err is None:
            _set_status("idle")
            print("[SERVER] 本局结束，回到空闲，可再次启动")
        else:
            _set_status("error", err)
            print("[SERVER] 本局异常结束，回到空闲，可再次启动")
except KeyboardInterrupt:
    print("[SERVER] 收到 Ctrl+C，退出进程")
    # 存在 uvicorn / pynput 等非主线程，强制退出确保进程真正结束
    os._exit(0)


