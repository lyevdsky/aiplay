print("\033[31m红色文字\033[0m")
print("\033[32m绿色文字\033[0m")
print("\033[33m黄色文字\033[0m")
print("\033[34m蓝色文字\033[0m")
print("\033[1m粗体\033[0m")
print("\033[1;31m粗体红色\033[0m")

check_dahai_claimed:  False
 [GAME] 玩家 3 摸牌 < 6p > 
 [AI] {'type': 'dahai', 'actor': 3, 'pai': 'E', 'tsumogiri': False, 'meta': {'q_values': [-8.511177, -8.37874, -8.390881, -2.753611, -8.504467, -8.745304, -9.076334, -5.2041078, -7.6389413, 0.09958553, -7.9971194], 'mask_bits': 2283126876, 'is_greedy': True, 'batch_size': 1, 'eval_time_ns': 34593900, 'shanten': 2, 'at_furiten': False}, 'values': [{'label': '1z', 'q_value': 0.09958553}, {'label': '7m', 'q_value': -2.753611}, {'label': '1s', 'q_value': -5.2041078}, {'label': '3s', 'q_value': -7.6389413}, {'label': '5z', 'q_value': -7.9971194}, {'label': '4m', 'q_value': -8.37874}, {'label': '5m', 'q_value': -8.390881}, {'label': '6p', 'q_value': -8.504467}, {'label': '3m', 'q_value': -8.511177}, {'label': '7p', 'q_value': -8.745304}, {'label': '8p', 'q_value': -9.076334}]} 
rec_daihai:  1z False False
rec_daihai:  1z False False
 [GAME] 玩家 3 打 1z 
 [AI] {'type': 'none'} 
 [GAME] 切换至玩家 0 
check_dahai_claimed:  False
 [GAME] 玩家 0 摸牌 < ? > 
 [AI] {'type': 'none'} 
rec_daihai:  7s False False
rec_daihai:  7s False False
 [GAME] 玩家 0 打 7s 
 [AI] {'type': 'none'} 
 [GAME] 切换至玩家 1 
check_dahai_claimed:  True
 [GAME] 玩家 1 鸣牌 
 [GAME] 玩家 1 chi < ['8s', '9s'] > 
 [AI] {'type': 'none'} 
rec_daihai:  5p False False
rec_daihai:  5p False False
 [GAME] 玩家 1 打 5p 
 [AI] {'type': 'none'} 
 [GAME] 切换至玩家 0 
check_dahai_claimed:  True
 [GAME] 玩家 0 鸣牌 
 [GAME] 玩家 0 pon < ['5p', '0p'] > 
 [AI] {'type': 'none'} 
rec_daihai:  4p False False
rec_daihai:  4p False False
 [GAME] 玩家 0 打 4p 
 [AI] {'type': 'none'} 
 [GAME] 切换至玩家 1 
check_dahai_claimed:  False
 [GAME] 玩家 1 摸牌 < ? > 
 [AI] {'type': 'none'} 
误检测为z5 0.6156156156156156
rec_daihai:  3p False False
rec_daihai:  3p False False
 [GAME] 玩家 1 打 3p 
 [AI] {'type': 'none'} 
 [GAME] 切换至玩家 2 
check_dahai_claimed:  False
 [GAME] 玩家 2 摸牌 < ? > 
 [AI] {'type': 'none'} 
rec_daihai:  9s False False
rec_daihai:  9s False False
 [GAME] 玩家 2 打 9s 
 [AI] {'type': 'none'} 
 [GAME] 切换至玩家 3 
check_dahai_claimed:  False
 [GAME] 玩家 3 摸牌 < 3z > 
 [AI] {'type': 'dahai', 'actor': 3, 'pai': 'W', 'tsumogiri': True, 'meta': {'q_values': [-8.461583, -8.216387, -7.9688263, -3.4648118, -8.418844, -9.238971, -9.434941, -7.2448072, -8.027318, -0.07076025, -7.7529974], 'mask_bits': 2685780060, 'is_greedy': True, 'batch_size': 1, 'eval_time_ns': 35981600, 'shanten': 1, 'at_furiten': False}, 'values': [{'label': '3z', 'q_value': -0.07076025}, {'label': '7m', 'q_value': -3.4648118}, {'label': '1s', 'q_value': -7.2448072}, {'label': '5z', 'q_value': -7.7529974}, {'label': '5m', 'q_value': -7.9688263}, {'label': '3s', 'q_value': -8.027318}, {'label': '4m', 'q_value': -8.216387}, {'label': '6p', 'q_value': -8.418844}, {'label': '3m', 'q_value': -8.461583}, {'label': '7p', 'q_value': -9.238971}, {'label': '8p', 'q_value': -9.434941}]} 
rec_daihai:  3z True False
rec_daihai:  3z True False
 [GAME] 玩家 3 摸切 3z 
 [AI] {'type': 'none'} 
 [GAME] 切换至玩家 0 
check_dahai_claimed:  False
 [GAME] 玩家 0 摸牌 < ? > 
 [AI] {'type': 'none'} 
rec_daihai:  7p True True
rec_daihai:  8p True False
rec_daihai:  8p True False
 [GAME] 玩家 0 摸切 8p 
 [AI] {'type': 'none'} 
 [GAME] 切换至玩家 1 
check_dahai_claimed:  False
 [GAME] 玩家 1 摸牌 < ? > 
 [AI] {'type': 'none'} 
rec_daihai:  8m False False
rec_daihai:  8m False False
 [GAME] 玩家 1 打 8m 
 [AI] {'type': 'none'} 
 [GAME] 切换至玩家 2 
check_dahai_claimed:  False
 [GAME] 玩家 2 摸牌 < ? > 
 [AI] {'type': 'none'} 
rec_daihai:  3p False False
rec_daihai:  3p False False
 [GAME] 玩家 2 打 3p 
 [AI] {'type': 'none'} 
 [GAME] 切换至玩家 3 
check_dahai_claimed:  False
 [GAME] 玩家 3 摸牌 < 4p > 
 [AI] {'type': 'dahai', 'actor': 3, 'pai': '4p', 'tsumogiri': True, 'meta': {'q_values': [-7.380857, -7.248545, -6.763552, -3.1679654, 0.09284747, -7.167147, -7.0667787, -7.3321967, -4.728627, -6.866676, -6.440533], 'mask_bits': 2148913244, 'is_greedy': True, 'batch_size': 1, 'eval_time_ns': 33904100, 'shanten': 1, 'at_furiten': False}, 'values': [{'label': '4p', 'q_value': 0.09284747}, {'label': '7m', 'q_value': -3.1679654}, {'label': '1s', 'q_value': -4.728627}, {'label': '5z', 'q_value': -6.440533}, {'label': '5m', 'q_value': -6.763552}, {'label': '3s', 'q_value': -6.866676}, {'label': '7p', 'q_value': -7.0667787}, {'label': '6p', 'q_value': -7.167147}, {'label': '4m', 'q_value': -7.248545}, {'label': '8p', 'q_value': -7.3321967}, {'label': '3m', 'q_value': -7.380857}]} 
rec_daihai:  4p False False
rec_daihai:  4p True False
rec_daihai:  4p True False
 [GAME] 玩家 3 摸切 4p 
 [AI] {'type': 'none'} 
 [GAME] 切换至玩家 0 
check_dahai_claimed:  False
 [GAME] 玩家 0 摸牌 < ? > 
 [AI] {'type': 'none'} 
rec_daihai:  2m False False
rec_daihai:  2m False False
 [GAME] 玩家 0 打 2m 
 [AI] {'type': 'none'} 
 [GAME] 切换至玩家 1 
check_dahai_claimed:  False
 [GAME] 玩家 1 摸牌 < ? > 
 [AI] {'type': 'none'} 
rec_daihai:  2p True False
rec_daihai:  2p True False
 [GAME] 玩家 1 摸切 2p 
 [AI] {'type': 'none'} 
 [GAME] 切换至玩家 2 
check_dahai_claimed:  False
 [GAME] 玩家 2 摸牌 < ? > 
 [AI] {'type': 'none'} 
rec_daihai:  5m True False
rec_daihai:  2p True False
rec_daihai:  2p True False
 [GAME] 玩家 2 摸切 2p 
 [AI] {'type': 'none'} 
 [GAME] 切换至玩家 3 
check_dahai_claimed:  False
 [GAME] 玩家 3 摸牌 < 6m > 
 [AI] {'type': 'dahai', 'actor': 3, 'pai': '1s', 'tsumogiri': False, 'meta': {'q_values': [-7.098242, -7.0238934, -6.9582806, -7.393918, -7.2440214, -2.2444239, -2.0262442, -5.815383, 0.03318417, -0.21786273, -4.7955313], 'mask_bits': 2148909180, 'is_greedy': True, 'batch_size': 1, 'eval_time_ns': 34084800, 'shanten': 1, 'at_furiten': False}, 'values': [{'label': '1s', 'q_value': 0.03318417}, {'label': '3s', 'q_value': -0.21786273}, {'label': '7p', 'q_value': -2.0262442}, {'label': '6p', 'q_value': -2.2444239}, {'label': '5z', 'q_value': -4.7955313}, {'label': '8p', 'q_value': -5.815383}, {'label': '5m', 'q_value': -6.9582806}, {'label': '4m', 'q_value': -7.0238934}, {'label': '3m', 'q_value': -7.098242}, {'label': '7m', 'q_value': -7.2440214}, {'label': '6m', 'q_value': -7.393918}]} 
rec_daihai:  1s False False
rec_daihai:  1s False False
 [GAME] 玩家 3 打 1s 
 [AI] {'type': 'none'} 
 [GAME] 切换至玩家 0 
check_dahai_claimed:  False
 [GAME] 玩家 0 摸牌 < ? > 
 [AI] {'type': 'none'} 
rec_daihai:  4m False False
rec_daihai:  4m False False
 [GAME] 玩家 0 打 4m 
 [AI] {'type': 'none'} 
 [GAME] 切换至玩家 1 
check_dahai_claimed:  False
 [GAME] 玩家 1 摸牌 < ? > 
 [AI] {'type': 'none'} 
rec_daihai:  8m True False
rec_daihai:  8m True False
 [GAME] 玩家 1 摸切 8m 
 [AI] {'type': 'none'} 
 [GAME] 切换至玩家 2 
check_dahai_claimed:  False
 [GAME] 玩家 2 摸牌 < ? > 
 [AI] {'type': 'none'} 
rec_daihai:  8m True False
rec_daihai:  5z True False
rec_daihai:  5z True False
 [GAME] 玩家 2 摸切 5z 
 [AI] {'type': 'pon', 'actor': 3, 'target': 2, 'pai': 'P', 'consumed': ['P', 'P'], 'meta': {'q_values': [-0.13319972, -0.1570409], 'mask_bits': 37383395344384, 'is_greedy': True, 'batch_size': 1, 'eval_time_ns': 35165100, 'shanten': 1, 'at_furiten': False}, 'values': [{'label': 'pon', 'q_value': -0.13319972}, {'label': 'none', 'q_value': -0.1570409}]} 
 [GAME] 切换至玩家 3 
check_dahai_claimed:  True
 [GAME] 玩家 3 鸣牌 
 [GAME] 玩家 3 pon < ['5z', '5z'] > 
 [AI] {'type': 'dahai', 'actor': 3, 'pai': '3s', 'tsumogiri': False, 'meta': {'q_values': [-7.8987646, -7.421377, -8.260894, -8.45757, -7.636697, -6.081897, -4.694007, -6.078923, -0.005927086], 'mask_bits': 1163388, 'is_greedy': True, 'batch_size': 1, 'eval_time_ns': 34172800, 'shanten': 1, 'at_furiten': False}, 'values': [{'label': '3s', 'q_value': -0.005927086}, {'label': '7p', 'q_value': -4.694007}, {'label': '8p', 'q_value': -6.078923}, {'label': '6p', 'q_value': -6.081897}, {'label': '4m', 'q_value': -7.421377}, {'label': '7m', 'q_value': -7.636697}, {'label': '3m', 'q_value': -7.8987646}, {'label': '5m', 'q_value': -8.260894}, {'label': '6m', 'q_value': -8.45757}]} 
rec_daihai:  8p False False
rec_daihai:  8p False False
 [GAME] 玩家 3 打 8p 
 [AI] {'type': 'none'} 
 [GAME] 切换至玩家 0 
check_dahai_claimed:  False
 [GAME] 玩家 0 摸牌 < ? > 
 [AI] {'type': 'none'} 
rec_daihai:  3m True False
rec_daihai:  3m True False
 [GAME] 玩家 0 摸切 3m 
 [AI] {'type': 'none'} 
 [GAME] 切换至玩家 1 
check_dahai_claimed:  False
 [GAME] 玩家 1 摸牌 < ? > 
 [AI] {'type': 'none'} 
rec_daihai:  9m False False
rec_daihai:  9m False False
 [GAME] 玩家 1 打 9m 
 [AI] {'type': 'none'} 
 [GAME] 切换至玩家 2 
check_dahai_claimed:  False
 [GAME] 玩家 2 摸牌 < ? > 
 [AI] {'type': 'none'} 
rec_daihai:  1s False True
rec_daihai:  1s False False
rec_daihai:  1s False False
 [GAME] 玩家 2 打 1s 
 [AI] {'type': 'none'} 
 [GAME] 切换至玩家 3 
check_dahai_claimed:  False
 [GAME] 玩家 3 摸牌 < 0s > 
 [AI] {'type': 'dahai', 'actor': 3, 'pai': '7p', 'tsumogiri': False, 'meta': {'q_values': [-4.810805, -5.200379, -7.0890794, -6.011933, -5.5747523, -0.39527285, 0.23790896, -2.8362622, -4.5456777], 'mask_bits': 68720574588, 'is_greedy': True, 'batch_size': 1, 'eval_time_ns': 35672700, 'shanten': 1, 'at_furiten': False}, 'values': [{'label': '7p', 'q_value': 0.23790896}, {'label': '6p', 'q_value': -0.39527285}, {'label': '3s', 'q_value': -2.8362622}, {'label': '0s', 'q_value': -4.5456777}, {'label': '3m', 'q_value': -4.810805}, {'label': '4m', 'q_value': -5.200379}, {'label': '7m', 'q_value': -5.5747523}, {'label': '6m', 'q_value': -6.011933}, {'label': '5m', 'q_value': -7.0890794}]} 
rec_daihai:  7p False False
rec_daihai:  7p False False
 [GAME] 玩家 3 打 7p 
 [AI] {'type': 'none'} 
 [GAME] 切换至玩家 0 
check_dahai_claimed:  True
 [GAME] 玩家 0 鸣牌 
共保存 500 张图片到文件夹 ./logs/20260621_234115
快照保存 3 张图片到文件夹 ./logs/20260621_234115\snapshot_00_is_ryukyoku_L26
快照保存 4 张图片到文件夹 ./logs/20260621_234115\snapshot_01_is_hora_L15
快照保存 2 张图片到文件夹 ./logs/20260621_234115\snapshot_02_check_new_kyoku_L159
快照保存 1 张图片到文件夹 ./logs/20260621_234115\snapshot_03_rec_hand_L13
快照保存 5 张图片到文件夹 ./logs/20260621_234115\snapshot_04_rec_kyoku_info_L105
快照保存 5 张图片到文件夹 ./logs/20260621_234115\snapshot_05_rec_tsumo_L35
快照保存 10 张图片到文件夹 ./logs/20260621_234115\snapshot_06_is_interrupt_L36
快照保存 5 张图片到文件夹 ./logs/20260621_234115\snapshot_07_rec_kakan_L109
快照保存 5 张图片到文件夹 ./logs/20260621_234115\snapshot_08_rec_new_meld_L131
快照保存 100 张图片到文件夹 ./logs/20260621_234115\snapshot_09_rec_dahai_L61
快照保存 2 张图片到文件夹 ./logs/20260621_234115\snapshot_10_get_active_player_L124
 [GAME] 游戏中止，打印中止时的GAME STATE 
{'honba': 0, 'kyotaku': 0, 'bakaze': 'S', 'kyoku': 4, 'dora_markers': ['6s'], 'scores': [32800, 33300, 8300, 25600], 'players': [0, 1, 2, 3], 'position': ['next', 'across', 'prev', 'self'], 'current_player': 0, 'player_to_id': {'self': 3, 'next': 0, 'across': 1, 'prev': 2}, 'oya': 3, 'player_info': [{'kawa_index': 10, 'riichi_index': None, 'melds': [{'type': 'pon', 'consumed': ['5p', '0p'], 'tile': '5p'}], 'riichi': False}, {'kawa_index': 10, 'riichi_index': None, 'riichi': False, 'melds': [{'type': 'chi', 'consumed': ['8s', '9s'], 'tile': '7s'}]}, {'kawa_index': 9, 'riichi': False, 'riichi_index': None, 'melds': []}, {'kawa_index': 10, 'riichi': False, 'riichi_index': None, 'melds': [{'type': 'pon', 'consumed': ['5z', '5z'], 'tile': '5z'}]}], 'my_id': 3}
[SERVER] 游戏异常，已捕获，进程继续运行：RuntimeError: 未识别出新的副露
Traceback (most recent call last):
  File "C:\game\code\mjai\aiplay\kurumi\server.py", line 83, in run_one_game
    game.main()
  File "C:\game\code\mjai\aiplay\kurumi\game.py", line 329, in main
    meld = check_new_meld()
           ^^^^^^^^^^^^^^^^
  File "C:\game\code\mjai\aiplay\kurumi\meld.py", line 206, in check_new_meld
    raise RuntimeError('未识别出新的副露')
RuntimeError: 未识别出新的副露
[SERVER] 本局异常结束，回到空闲，可再次启动