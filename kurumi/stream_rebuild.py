"""从「已知的 gamestate 节点」+「当前截图」反推中间产生过的 mjai 事件。

用途：bot 的 PlayerState 与画面失同步（丢帧、误读）时，用画面重建一条**自洽**的事件流，
把新 bot 直接喂到当前局面。只保证「终点等价于画面」，不保证过程与真实经过一致。

约定：
  - gs 是**已经喂给 bot 的**那个节点；返回的事件从它之后开始。
  - 调用期间会把 gs 写到全局 gamestate（rec_new_meld 算 target 需要 player_to_id），
    结束后恢复原值。
  - 不在 main 里自动调用，由调用方决定何时重建。

限制（拿不回来的东西）：
  - 牌山剩余数只能间接影响，会有偏差；
  - 别家手牌全是 '?'，bot 对别家手牌的推断从零开始；
  - 立直只能按牌河上的标记补，具体是第几手立的可能不准。
"""
import cv2

from config import HAND_FIRST_REGION
from gamestate import get_gamestate, set_gamestate
from kawa import rec_dahai
from meld import rec_new_meld
from kyoku import get_dora_marker, get_active_player
from tile import check_tile, TileType
from hand import rec_tsumo

MAX_KAWA = 24          # 牌河最多 18 张，留点余量
MAX_DORA = 5           # 宝牌指示牌最多 5 张
MAX_LOOP = 300         # 防御性上限，正常一局远小于这个


def read_hand(shot, meld_count):
    """读自己手牌（不含摸牌），张数 = 13 - 3 * meld_count。"""
    x, y, w, h = HAND_FIRST_REGION
    tiles = []
    for i in range(max(13 - 3 * meld_count, 0)):
        offset = i * w
        tile_img = shot[y - 95:y + h, x + offset:x + offset + w]
        tile = check_tile(tile_img, type=TileType.Hand, debug=False)
        if tile is None:
            break
        tiles.append(tile)
    return tiles


def read_river(shot, player, start, riichi_index=None):
    """读该玩家牌河从 start 起的可见牌。"""
    tiles = []
    pos = start
    while pos < MAX_KAWA:
        r = rec_dahai(shot, player, pos, riichi_index)
        if r is None:
            break
        tile, tsumogiri, riichi = r
        tiles.append({'tile': tile, 'tsumogiri': tsumogiri, 'riichi': riichi})
        pos += 1
    return tiles


def read_new_melds(shot, player, existing):
    """读该玩家在 existing 之后的新副露（rec_new_meld 已带 target）。"""
    melds = []
    cur = list(existing)
    while len(cur) < 4:
        m = rec_new_meld(shot, player, cur)
        if m is None:
            break
        melds.append(m)
        cur.append(m)
    return melds


def read_new_dora(shot, gs):
    """读画面上比 gs 多的宝牌指示牌。"""
    out = []
    total = len(gs.get('dora_markers') or [])
    for i in range(total, MAX_DORA):
        tile = get_dora_marker(shot, i)
        if tile is None:
            break
        out.append(tile)
    return out


def _claim_event(q, m, p):
    """把副露变成 mjai 事件。p 是被鸣者。"""
    t = m.get('type')
    if t in ('pon', 'chi'):
        return {'type': t, 'actor': q, 'target': p,
                'pai': m.get('tile'), 'consumed': m.get('consumed') or []}
    if t == 'daiminkan':
        tile = m.get('tile')
        return {'type': 'daiminkan', 'actor': q, 'target': p,
                'pai': tile, 'consumed': [tile] * 3}
    if t == 'ankan':
        tile = m.get('tile')
        return {'type': 'ankan', 'actor': q, 'consumed': [tile] * 3 + [tile]}
    if t == 'kakan':
        tile = m.get('tile')
        return {'type': 'kakan', 'actor': q, 'pai': tile, 'consumed': [tile] * 3}
    return None


def build_mjai_to_state(gs, shot=None, own_drawn=...):
    """返回 gs → 现在 的事件列表。

    own_drawn: 自己是否已摸牌。传 ... 表示自动从画面判断（rec_tsumo），
               也可以显式传 True/False 或具体牌面来避开识别抖动。
    """
    if shot is None:
        from screenshot import get_screenshot
        shot = get_screenshot()

    backup = dict(get_gamestate())
    set_gamestate(gs)
    try:
        return _build(gs, shot, own_drawn)
    finally:
        set_gamestate(backup)


def _build(gs, shot, own_drawn):
    position = gs['position']
    my_id = gs['my_id']
    events = []

    # ---- 1. 宝牌（先发，bot 只关心集合）
    for marker in read_new_dora(shot, gs):
        events.append({'type': 'dora', 'dora_marker': marker})

    # ---- 2. 读盘：牌河 / 新副露 / 自己手牌
    river = {}
    melds = {}
    for pid in range(4):
        player = position[pid]
        info = gs['player_info'][pid]
        river[pid] = read_river(shot, player, info['kawa_index'], info.get('riichi_index'))
        melds[pid] = read_new_melds(shot, player, info['melds'])

    meld_count = len(gs['player_info'][my_id]['melds']) + len(melds[my_id])
    hand = read_hand(shot, meld_count)
    drawn = rec_tsumo(shot) if own_drawn is ... else (
        (hand[-1] if own_drawn is True and hand else None) if isinstance(own_drawn, bool) else own_drawn)

    # ---- 3. 起点
    phase = gs.get('phase')
    last_player = gs.get('last_player')
    if phase == 'Claim' and last_player is not None:
        # 上一手打牌已经发过；先看有没有人鸣它
        claimed = None
        for q in range(4):
            if melds[q] and melds[q][0].get('target') == last_player:
                claimed = q
                break
        if claimed is not None:
            m = melds[claimed].pop(0)
            ev = _claim_event(claimed, m, last_player)
            if ev:
                events.append(ev)
            cur, need_draw = claimed, False
        else:
            cur, need_draw = (last_player + 1) % 4, True
    elif phase == 'Dahai':
        cur, need_draw = gs['current_player'], False
    else:
        cur, need_draw = gs['current_player'], True

    # ---- 4. 按轮次补事件
    for _ in range(MAX_LOOP):
        p = cur
        claimer = None
        for q in range(4):
            if melds[q] and melds[q][0].get('target') == p:
                claimer = q
                break
        if claimer is None and not river[p]:
            break

        if need_draw:
            tile = drawn if (p == my_id and drawn is not None) else '?'
            events.append({'type': 'tsumo', 'actor': p, 'pai': tile})

        if claimer is not None:
            m = melds[claimer].pop(0)
            events.append({'type': 'dahai', 'actor': p, 'pai': m.get('tile'), 'tsumogiri': False})
            ev = _claim_event(claimer, m, p)
            if ev:
                events.append(ev)
            cur, need_draw = claimer, False
            continue

        r = river[p].pop(0)
        if r['riichi']:
            events.append({'type': 'reach', 'actor': p})
        events.append({'type': 'dahai', 'actor': p, 'pai': r['tile'],
                       'tsumogiri': r['tsumogiri']})
        if r['riichi']:
            events.append({'type': 'reach_accepted', 'actor': p})
        cur, need_draw = (p + 1) % 4, True

    # ---- 5. 收尾：轮到自己且已经摸牌
    if need_draw and cur == my_id and drawn is not None:
        events.append({'type': 'tsumo', 'actor': my_id, 'pai': drawn})

    return events
