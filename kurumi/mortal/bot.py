import sys
import json
import traceback
from kurumi.mortal.model import load_model
from kurumi.mortal.conv import format_input, format_output

class Bot:
    """一局游戏只创建一次、模型只加载一次，跨 kyoku 复用。

    - start() 幂等：同一 player_id 重复调用不会重新 torch.load。
    - end() 之后 react() 只返回 none，不会再抛 AttributeError。
    """

    def __init__(self):
        self.ai = None
        self.player_id = None

    def start(self, player_id):
        assert player_id in range(4)
        if self.ai is not None and self.player_id == player_id:
            return
        self.ai = load_model(player_id, './mortal/model/mortal.pth')
        self.player_id = player_id
        
    def end(self):
        self.ai = None
        self.player_id = None

    # 每次一个事件
    def react(self, event):
        # 还没 start（或已经 end）：本次对局不需要 AI 参与，直接放行
        if self.ai is None:
            return { 'type':'none' }
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