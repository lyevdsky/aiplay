import json
import sys

import model


# class Bot:
#     def __init__(self, player_id: int):
#         self.player_id = player_id
#         self.model = model.load_model(player_id)

#     def react(self, events: str) -> str:
#         events = json.loads(events)
#         print(f"Received events: {events}")
#         return_action = None
#         for e in events:
#             a = json.dumps(e, separators=(",", ":"))
#             print(f"Processing event: {a}")
#             return_action = self.model.react(a)

#         if return_action is None:
#             return json.dumps({"type":"none"}, separators=(",", ":"))
#         else:
#             raw_data = json.loads(return_action)
#             del raw_data["meta"]
#             return json.dumps(raw_data, separators=(",", ":"))


def main():
    player_id = int(sys.argv[1])
    assert player_id in range(4)
    # bot = Bot(player_id)
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