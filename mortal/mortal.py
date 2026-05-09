import prelude

import os
import sys
import json
import torch
from datetime import datetime, timezone
from model import Brain, DQN, GRP
from engine import MortalEngine
from common import filtered_trimmed_lines
from libriichi.mjai import Bot
from libriichi.dataset import Grp
from config import config

USAGE = '''Usage: python mortal.py <ID>

ARGS:
    <ID>    The player ID, an integer within [0, 3].'''

def main():
    try:
        player_id = int(sys.argv[-1])
        assert player_id in range(4)
    except:
        print(USAGE, file=sys.stderr)
        sys.exit(1)

    device = torch.device('cpu')
    state = torch.load(config['control']['state_file'], weights_only=False, map_location=torch.device('cpu'))
    cfg = state['config']
    version = cfg['control'].get('version', 1)
    num_blocks = cfg['resnet']['num_blocks']
    conv_channels = cfg['resnet']['conv_channels']
    if 'tag' in state:
        tag = state['tag']
    else:
        if 'timestamp' in state:
            time = datetime.fromtimestamp(state['timestamp'], tz=timezone.utc).strftime('%y%m%d%H')
            tag = f'mortal{version}-b{num_blocks}c{conv_channels}-t{time}'
        else:
            tag = f'mortal{version}-b{num_blocks}c{conv_channels}'

    mortal = Brain(version=version, num_blocks=num_blocks, conv_channels=conv_channels).eval()
    dqn = DQN(version=version).eval()
    mortal.load_state_dict(state['mortal'])
    dqn.load_state_dict(state['current_dqn'])

    engine = MortalEngine(
        mortal,
        dqn,
        version = version,
        is_oracle = False,
        device = device,
        enable_amp = False,
        enable_quick_eval = True,
        enable_rule_based_agari_guard = True,
        name = 'mortal',
    )
    bot = Bot(engine, player_id)
    while True:
        try:             
            line = sys.stdin.readline()
            line = line.rstrip('\n')
            event = json.loads(line)
            if event['type'] == 'end_game':
                break
            if reaction := bot.react(line):
                print(reaction, flush=True)
            else:
                print('{"type":"none","meta":{"mask_bits":0}}', flush=True)
        except:
            break
    
if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
