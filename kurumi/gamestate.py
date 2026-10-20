from enum import Enum


class Phase(Enum):
    StartKyoku = 0
    Dahai = 1
    Tsumo = 2
    Claim = 3
    Hora = 4
    Ryukyoku = 5
    EndKyoku = 6
    EndGame = 7
    StartGame = 8
    Unknown = 9

gamestate = {
    "honba": 0,
    "kyotaku": 0,
    "bakaze": 'E',
    "kyoku": 1,
    "phase": None,
    "last_player": None,
    "last_dahai": None,
    "dora_markers": [],
    "scores": [25000, 25000, 25000, 25000],
    "players": [0, 1, 2, 3],
    "position": ["self", "next", "across", "prev"],
    "current_player": 3,
    "player_to_id": {
        "self": 0,
        "next": 1,
        "across": 2,
        "prev": 3
    },
    "oya": 0,
    "player_info": [
        {
            "kawa_index": 1, # 当前下一张打牌在牌河显示的位置，不包括被鸣的牌
            "riichi_index": None, # 立直牌在牌河的位置，用于修正裁剪牌位置
            "melds": [{},{}] 
        },
        {
            "kawa_index": 0,
            "riichi_index": None,
            "melds": []
        },
        {
            "kawa_index": 0,
            "riichi_index": None,
            "melds": []
        },
        {
            "kawa_index": 0,
            "riichi_index": None,
            "melds": [
                { 'type': 'pon' },
            ]
        }
    ],
}

def set_gamestate(state):
    for key, value in state.items():
        gamestate[key] = value

def get_gamestate():
    return gamestate


def get_playerinfo(player):
    return gamestate['player_info'][player]


def init_gamestate():
    global gamestate
    gamestate["honba"] = 0
    gamestate["kyotaku"] = 0
    gamestate["bakaze"] = 'E'
    gamestate["kyoku"] = 1
    gamestate["dora_markers"] = []
    gamestate["scores"] = [25000, 25000, 25000, 25000]
    gamestate["players"] = [0, 1, 2, 3]
    gamestate["position"] = ["self", "next", "across", "prev"]
    gamestate["current_player"] = 0
    gamestate["oya"] = 0
    gamestate["phase"] = None       # 当前阶段（Phase 枚举），由 main 写，watcher 读作 check 前置条件
    gamestate["last_player"] = None # 上一个打牌的玩家；watcher 靠 current_player != last_player 判断当前玩家是否已打牌
    gamestate["last_dahai"] = None  # 上一张打出的牌，供 claim 构造鸣牌事件
    gamestate["player_info"] = [
        {
            "kawa_index": 0, # 当前下一张打牌在牌河显示的位置，不包括被鸣的牌
            "riichi_index": None, # 立直牌在牌河的位置，用于修正裁剪牌位置
            "melds": [],
            "riichi": False,
        },
        {
            "kawa_index": 0,
            "riichi_index": None,
            "riichi": False,
            "melds": []
        },
        {
            "kawa_index": 0,
            "riichi": False,
            "riichi_index": None,
            "melds": []
        },
        {
            "kawa_index": 0,
            "riichi": False,
            "riichi_index": None,
            "melds": []
        }
    ]

# init_gamestate()