from ..mortal2.model import load_model
from fastapi import FastAPI

app = FastAPI()

@app.get('/hello')
def hello():
    return "Hello, World!"

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=5000)
