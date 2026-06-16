import asyncio
import time
from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse
import uvicorn
import threading
from game import Game
from screenshot import save_img_q

app = FastAPI()
clients = set()

@app.get("/")
def index():
    with open("index.html") as f:
        return HTMLResponse(f.read())

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    clients.add(websocket)
    try:
        await websocket.receive_text()  # 保持连接
    finally:
        clients.remove(websocket)

def update_ui(data: dict):
    for client in clients.copy():
        asyncio.run_coroutine_threadsafe(
            client.send_json(data),
            loop
        )

def start_server():
    global loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    config = uvicorn.Config(app, port=5500, loop="asyncio")
    server = uvicorn.Server(config)
    loop.run_until_complete(server.serve())

# 服务器放子线程
thread = threading.Thread(target=start_server, daemon=True)
thread.start()

# 主线程跑game
try:
    game = Game(listener=lambda data: update_ui(data))
    game.main()
except Exception as e:
    save_img_q()
while True:
    time.sleep(100)
