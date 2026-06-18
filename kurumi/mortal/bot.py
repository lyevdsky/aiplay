import sys
import json
import traceback
from kurumi.mortal.model import load_model
from kurumi.mortal.conv import format_input, format_output

class Bot:
    def __init__(self):
        self.ai = None

    def start(self, player_id):
        global bot
        assert player_id in range(4)
        self.ai = load_model(player_id, './mortal/model/mortal.pth')
        
    def end(self):
        self.ai = None

    # 每次一个事件
    def react(self, event):
        try:
            event = format_input(event)
            eventstr = json.dumps(event)
            if reaction := self.ai.react(eventstr):
                # print(reaction, flush=True)
                return format_output(json.loads(reaction))
            else:
                return { 'type':'none' }
        except Exception as e:
            traceback.print_exc()
            return {'error': str(e)}

def main():
    player_id = int(sys.argv[1])
    assert player_id in range(4)
    bot = load_model(player_id)
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