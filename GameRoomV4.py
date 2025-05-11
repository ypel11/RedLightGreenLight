import socket, threading, struct, time, pickle, cv2, numpy as np
from GameLogic import Game
import Utils
HOST = 'SEVER IP'
PORT = 5000
MAX_PLAYERS = 1
TICK = 0.05
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
            self.games[game_id] = {'game': game, 'sock': sock, 'frame': None, 'active': True}
            threading.Thread(target=self.recv_loop, args=(game_id,), daemon=True).start()
            return game_id

    def recv_loop(self, game_id):
        game = self.games[game_id]['game']
        sock = self.games[game_id]['sock']
        active = self.games[game_id]['active']
        try:
            while game.active and self.winner is None:
                header = Utils.recv_all(sock, 5)
                win_flag, size = struct.unpack(">?I", header)
                payload = Utils.recv_all(sock, size)
                arr = np.frombuffer(payload, np.uint8)
                frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                with self.lock:
                    self.games[game_id]['frame'] = (frame, win_flag)
        except (ConnectionAbortedError, ConnectionResetError):
            # The socket was closed from the other side—just exit cleanly
            pass
        except Exception as e:
            print(f"[recv_loop] unexpected error for player {game_id}:", e)
        finally:
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
                    if not info['active']:
                        break
                    game = info['game']
                    sock = info['sock']
                    if info['frame'] is None:
                        continue
                    frame, win_flag = info['frame']
                    frame = game.update_values(frame, win_flag)
                    alive = game.active
                    info['active'] = alive
                    self.winner = game.winner
                    # Check if player won
                    if self.winner is not None:
                        self.winner = (game_id, self.winner)
                        break
                    Utils.send_frame(sock, frame, True, alive)
                    # Check if player lost
                    if alive:
                        alive_frames.append(frame)

                # 2) Check for winner (first win_flag or last alive)
                if self.winner is not None:
                    break
                else:
                    alive_ids = [game_id for game_id, info in self.games.items() if info['active'] == True]
                    if not alive_ids:
                        break  # everyone lost


                # 3) Build grid and send to all sockets
                #if alive_frames:
                    #grid = utils.stack_frames(alive_frames, grid_size=(2, 3))
                    #for info in self.games.values():
                        #utils.send_frame(info['sock'], grid, True)

                # game ended, send final result frames once more
        for info in self.games.values():
            # overlay result on the last out frame
            frame = 255 * np.ones((200, 640, 3), np.uint8)
            text = f"Winner: player {self.winner[1]} from game {self.winner[0]}" if self.winner else "Everyone Lost"
            cv2.putText(frame, text, (20, 100), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 0, 0), 3)
            Utils.send_frame(info['sock'], frame, False, False)



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

if __name__ =="__main__":
    main()
