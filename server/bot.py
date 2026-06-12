import sys
import json
import torch
from datetime import datetime, timezone
import model

bot = None

def start(player_id):
    global bot
    assert player_id in range(4)
    bot = model.load_model(player_id)
    
def end():
    global bot
    bot = None

def react(event):
    global bot
    try:
        eventstr = json.dumps(event)
        if reaction := bot.react(eventstr):
            print(reaction, flush=True)
            return json.loads(reaction)
        else:
            return { 'type':'none'}
    except Exception as e:
        return {'error': str(e)}
    
def main():
    player_id = int(sys.argv[1])
    assert player_id in range(4)
    bot = model.load_model(player_id)
    while True:
        line = sys.stdin.readline()
        line = line.rstrip('\n')
        event = json.loads(line)
        if event['type'] == 'end_game':
            break
        if reaction := bot.react(line):
            print(reaction, flush=True)

if __name__ == "__main__":
    main()