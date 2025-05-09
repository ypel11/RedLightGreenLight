import socket, threading, struct, time, pickle, cv2, numpy as np

import Utils
from GameLogic import Game

HOST = '0.0.0.0'
PORT = 5000
MAX_PLAYERS = 2
TICK = 0.01
class GameRoom:

    def __init__(self, light_duration=5):
        self.games = {}        # pid -> {'game':PlayerGame, 'sock':socket, 'frame':ndarray}
        self.game_id = 1
        self.lock = threading.Lock()
        self.winner = None
        self.light_duration = light_duration
        self.start_time = None

    def add_player(self, sock):
        with self.lock:
            game_id = self.game_id
            self.game_id += 1
            game = Game()
            self.games[game_id] = {'game': game, 'sock': sock, 'frame': None}
            threading.Thread(target=self.recv_loop, args=(game_id,), daemon=True).start()
            return game_id

    def recv_loop(self, game_id):
        game = self.games[game_id]['game']
        sock = self.games[game_id]['sock']
        while game.active and self.winner is None:
            data = sock.recv(8)
            win_flag, size = struct.unpack("? I", data)
            data = Utils.recv_all(sock, size)
            jpg_frame = pickle.loads(data)
            frame = cv2.imdecode(jpg_frame, cv2.IMREAD_COLOR)
            with self.lock:
                self.games[game_id]['frame'] = (frame, win_flag)

        with self.lock:
            game.active = False

    def game_loop(self):
        self.start_time = time.time()
        while True:
            self.change_light()
            time.sleep(TICK)
            with self.lock:
                # 1) Process each player
                alive_frames = []
                for game_id, info in list(self.games.items()):
                    game = info['game']
                    sock = info['sock']
                    if info['frame'] is None:
                        continue
                    frame, win_flag = info['frame']
                    if frame is None:
                        continue
                    frame = game.update_values(frame, win_flag)
                    alive = game.active
                    winner = game.winner
                    Utils.send_frame(sock, frame, alive)
                    if winner is not None:
                        self.winner = (game_id, winner)
                        break
                    if alive:
                        alive_frames.append(frame)

                # 2) Check for winner (first win_flag or last alive)
                if self.winner is None:
                    alive_ids = [game_id for game_id, info in self.games.items() if info['game'].active]
                    if len(alive_ids) == 1:
                        self.winner = alive_ids[0]
                    elif not alive_ids:
                        self.winner = None  # everyone lost
                if self.winner is not None:
                    break

                # 3) Build grid and send to all sockets
                #if alive_frames:
                    #grid = utils.stack_frames(alive_frames, grid_size=(2, 3))
                    #for info in self.games.values():
                        #utils.send_frame(info['sock'], grid, True)

                # game ended, send final result frames once more
        for info in self.games.values():
            # overlay result on the last out frame
            frame = info['frame'][0] if info['frame'] else np.zeros((480, 640, 3), np.uint8)
            text = ("Winner: " + str(self.winner)) if self.winner else "Everyone Lost"
            cv2.putText(frame, text, (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 0, 0), 3)
            Utils.send_frame(info['sock'], frame, False)
            info['sock'].close()



    def change_light(self):
        elapsed_time = time.time() - self.start_time
        if elapsed_time > self.light_duration:
            for game_id, info in list(self.games.items()):
                game = info['game']
                game.change_light()  # Toggle game state
            self.start_time = time.time()

def main():
    room = GameRoom(light_duration=5)
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind((HOST, PORT))
    srv.listen()
    print(f"Server listening on {PORT} (max {MAX_PLAYERS} players)...")

    # accept players
    while len(room.games) < MAX_PLAYERS or cv2.waitKey(1) & 0xFF == ord('s'):
        sock, addr = srv.accept()
        game_id = room.add_player(sock)
        print(f"Player {game_id} connected from {addr}")
    print("All players connected, starting game!")
    room.game_loop()
    srv.close()
    print("Game over, server shutting down.")

if __name__=="__main__":
    main()