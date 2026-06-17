import json

mockOutput = {
  "type": "dahai",
  "actor": 2,
  "pai": "9p",
  "tsumogiri": True,
  "values": [],
  "time": 0,
  "meta": {
    "q_values": [
      -1.1929103,
      -1.5628747,
      -1.6204606,
      -1.607082,
      -1.3267958,
      -0.2436666,
      -1.5208447,
      -1.5280346,
      -1.5830542,
      -1.6640469,
      -1.1801766,
      -1.8054415
    ],
    "mask_bits": 17241923593,
    "is_greedy": True,
    "batch_size": 1,
    "shanten": 1,
    "eval_time_ns": 30352000
  }
}

replacements = [
    ('0m', '5mr'),
    ('0p', '5pr'),
    ('0s', '5sr'),
    ('1z', 'E'),
    ('2z', 'S'),
    ('3z', 'W'),
    ('4z', 'N'),
    ('5z', 'P'),
    ('6z', 'F'),
    ('7z', 'C'),
]

reverse_map = { new: old for old, new in replacements}

def actionIndexToTile(index):
    if index >= 0 and index <= 8:
        return f"{index + 1}m"
    if index >= 9 and index <= 17:
        return f"{index - 8}p"
    if index >= 18 and index <= 26:
        return f"{index - 17}s"
    if index >= 27 and index <= 33:
        return ['E', 'S', 'W', 'N', 'P', 'F', 'C'][index - 27]
    return { 34: '5mr', 35: '5pr', 36: '5sr' }.get(index, None)

def actionIndexToAction(index):
    tile = actionIndexToTile(index)
    if tile:
        return tile
    labels = {
        37: 'riichi',
        38: 'chi_low',
        39: 'chi_mid',
        40: 'chi_high',
        41: 'pon',
        42: 'kan',
        43: 'hora',
        44: 'ryukyoku',
        45: 'none',
    }
    if index in labels:
        return labels[index]
    return f'action_{index}'

def maskActionIndexes(maskBits):
    if not isinstance(maskBits, int):
        return []
    mask = maskBits
    indexes = []
    index = 0
    while mask > 0:
        if mask & 1:
            indexes.append(index)
        mask >>= 1
        index += 1
    return indexes

def format_output(output):
    meta = output.get('meta')
    mask_bits = meta.get('mask_bits') if meta is not None else None
    indexes = maskActionIndexes(mask_bits)  # 函数内部应对 None 返回 []
    maskLabels = [actionIndexToAction(idx) for idx in indexes]
    # 假设 maskLabels 是列表，output.meta.q_values 是与 maskLabels 等长的列表
    items = [{"label": reverse_map.get(l, l), "q_value": meta.get('q_values')[idx]} for idx, l in enumerate(maskLabels)]
    sortedLabels = sorted(items, key=lambda x: x["q_value"], reverse=True)
    output['values'] = sortedLabels
    # print('output:', output)
    return output

# format_output(mockOutput)

def format_input(input):
    """将 MjaiEvent 中的牌代号转换为 mjai 格式（红宝牌等）"""
    # 序列化为 JSON 字符串
    
    # print('tran_message_to_mjai_event: ', message)

    str_event = json.dumps(input, ensure_ascii=False)

    for old, new in replacements:
        str_event = str_event.replace(old, new)

    # 反序列化回字典
    event = json.loads(str_event)
    return event

# output2 = {"type":"pon","actor":2,"target":3,"pai":"2p","consumed":["2p","2p"],"meta":{"q_values":[0.22901708,-3.6937587],"mask_bits":37383395344384,"is_greedy":True,"batch_size":1,"eval_time_ns":25450652,"shanten":3,"at_furiten":False}}
# print(format_output(output2))