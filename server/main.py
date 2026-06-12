# import sys
# import os
# sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fastapi import FastAPI, Body
from fastapi.middleware.cors import CORSMiddleware
import bot
import json

app = FastAPI()

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源（生产环境建议指定具体域名）
    allow_credentials=True,  # 允许携带 cookies
    allow_methods=["*"],  # 允许所有 HTTP 方法
    allow_headers=["*"],  # 允许所有请求头
)

@app.get('/hello')
def hello():
    return "Hello, World!"

@app.post('/react')
def react(
    eventStr: str = Body(...),      # 显式声明从请求体读取
    player_id: int = Body(None)
):
    print(f"Received eventStr: {eventStr}, player_id: {player_id}")
    try:
        events = json.loads(eventStr)  # validate json
        print(f"Received events: {events}")
    except json.JSONDecodeError:
        return {"error": "Invalid JSON"}
    reaction = None
    
    for event in events:
        if event['type'] == 'end_game':
            bot.end()
        elif event['type'] == 'start_game':
            bot.start(player_id)
        reaction = bot.react(event)

    return reaction

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=5100)
