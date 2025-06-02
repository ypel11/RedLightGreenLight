import socket, threading, struct, time, random, string, pickle, cv2, numpy as np, sqlite3, json, bcrypt
from GameLogic import Game
import Utils
HOST = '0.0.0.0'
PORT = 5000
MAX_PLAYERS = 1
TICK = 0.05



class GameRoom:

    def __init__(self, light_duration, max_players):
        self.users = {}        # pid -> {'game':PlayerGame, 'sock':socket, 'frame':ndarray}
        self.spectators = []
        self.max_players = max_players
        self.room_id = self.generate_game_id(5)
        self.lock = threading.Lock()
        self.winner = None
        self.red_light = False
        self.light_duration = light_duration
        self.start_time = None

    def generate_game_id(self, length):
        characters = string.ascii_letters + string.digits
        return ''.join(random.choice(characters) for _ in range(length))

    def add_player(self, user, sock, role):
        with self.lock:
            if role == 'player':
                game = Game()
                self.users[user] = {'game': game, 'sock': sock, 'frame': None, 'active': True}
                print(f"{user} has joined the game")
                threading.Thread(target=self.recv_loop, args=(user, ), daemon=True).start()
                if len(self.users) == self.max_players:
                    threading.Thread(target=self.game_loop, daemon=True).start()
                return True
            if role == 'spectator':
                self.spectators.append(sock)
                return True



    def recv_loop(self, user):
        game = self.users[user]['game']
        sock = self.users[user]['sock']
        active = self.users[user]['active']
        try:
            while active and self.winner is None:
                header = Utils.recv_all(sock, 5)
                win_flag, size = struct.unpack(">?I", header)
                payload = Utils.recv_all(sock, size)
                arr = np.frombuffer(payload, np.uint8)
                frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                with self.lock:
                    self.users[user]['frame'] = (frame, win_flag)
                    active = self.users[user]['active']
            print("Success")

        except (ConnectionAbortedError, ConnectionResetError):
            # The socket was closed from the other side—just exit cleanly
            pass
        except Exception as e:
            print(f"[recv_loop] unexpected error for player {user}:", e)
        finally:
            with self.lock:
                game.active = False

    def game_loop(self):
        print(f"game started")
        self.start_time = time.time()
        while True:
            self.change_light()
            time.sleep(TICK)
            with self.lock:
                # 1) Process each player
                alive_frames = []
                for user, info in list(self.users.items()):
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
                        self.winner = (user, self.winner)
                        break
                    Utils.send_frame(sock, frame, True, alive, self.red_light)
                    # Check if player lost
                    if alive:
                        alive_frames.append(frame)

                # 2) Check for winner or lost
                alive_ids = [game_id for game_id, info in self.users.items() if info['active'] == True]
                if self.winner is not None or not alive_ids:
                    for info in self.users.values():
                        info['active'] = False
                    break

                if alive_frames:
                    from math import ceil
                    cols = min(len(alive_frames), 3)  # up to 3 columns
                    rows = ceil(len(alive_frames) / cols)
                    grid = Utils.stack_frames(alive_frames, grid_size=(rows, cols))
                    for spec in self.spectators:
                        Utils.send_frame(spec, grid, True, True, self.red_light)

        # game ended, send final result frames once more
        # overlay result on the last out frame
        frame = 255 * np.ones((200, 640, 3), np.uint8)
        text = f"Winner: player {self.winner[1]} from  {self.winner[0]}'s game" if self.winner else "Everyone Lost"
        cv2.putText(frame, text, (20, 100), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 0, 0), 3)
        for info in self.users.values():
            Utils.send_frame(info['sock'], frame, False, False, self.red_light)
        for spec in self.spectators:
            Utils.send_frame(spec, frame,False, False, self.red_light)




    def change_light(self):
        elapsed_time = time.time() - self.start_time
        if elapsed_time > self.light_duration:
            self.red_light = not self.red_light
            for game_id, info in list(self.users.items()):
                game = info['game']
                game.change_light()  # Toggle game state
            self.start_time = time.time()


class Server:

    def __init__(self):
        self.DB = "Users.db"
        self.init_db()
        self.users = {}   # username -> socket
        self.gameRooms = {}   # room_id  -> GameRoom instance

    def init_db(self):
        conn = sqlite3.connect(self.DB)
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            pw_hash BLOB
            )
        """)
        conn.commit()
        conn.close()

    def handle_auth(self, sock):
        """
        Reads one JSON message: {"action":"login"/"signup", "user":.., "pass":..}
        Replies with JSON {"ok":bool, "error":str?}.
        Returns True if login/signup succeeded.
        """
        raw = sock.recv(4)
        if not raw:
            return False
        length = int.from_bytes(raw, "big")
        msg = json.loads(Utils.recv_all(sock, length).decode())
        username = msg["user"]
        password = msg["pass"].encode()

        db = sqlite3.connect(self.DB)
        cur = db.cursor()

        if msg["action"] == "signup":
            # check if exists
            cur.execute("SELECT 1 FROM users WHERE username=?", (username,))
            if cur.fetchone():
                reply = {"ok":False, "error":"Username taken."}
            else:
                pw_hash = bcrypt.hashpw(password, bcrypt.gensalt())
                cur.execute("INSERT INTO users VALUES (?, ?)", (username, pw_hash))
                db.commit()
                reply = {"ok":True}
        elif msg["action"] == "login":  # login
            cur.execute("SELECT 1 FROM users WHERE username=?", (username,))
            if not cur.fetchone():
                reply = {"ok":False, "error":"Username not found."}
            else:
                cur.execute("SELECT pw_hash FROM users WHERE username=?", (username,))
                row = cur.fetchone()
                if row and bcrypt.checkpw(password, row[0]):
                    reply = {"ok":True}
                else:
                    reply = {"ok":False, "error":"Password invalid."}

        db.close()

        out = json.dumps(reply).encode()
        sock.send(len(out).to_bytes(4, "big") + out)
        return username, reply["ok"]

    def accept_loop(self):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.bind((HOST, PORT))
        srv.listen()
        print(f"Server listening on {PORT} (max {5} players)...")
        while True:
            sock, addr = srv.accept()
            login_success = False
            for i in range(0, 3):
                username, ok = self.handle_auth(sock)
                if ok:
                    login_success = True
                    self.users[username] = sock
                    threading.Thread(target=self.handle_user_request, args=(username, sock, )).start()
                    print(f"User {username} connected from {addr}")
                    break
            if not login_success:
                sock.close()
                continue

    def handle_user_request(self, user, sock):
        while True:
            raw = sock.recv(4)
            if not raw:
                return False
            length = int.from_bytes(raw, "big")
            msg = json.loads(Utils.recv_all(sock, length).decode())

            # Create a new game
            if msg["action"] == "create_game":
                light_duration = msg["light_duration"]
                max_players = msg["max_players"]
                role = msg["role"]
                gr = GameRoom(light_duration, max_players)
                self.gameRooms[gr.room_id] = gr
                success = gr.add_player(user, sock, role)
                msg = json.dumps({"ok": success, "room_id": gr.room_id}).encode()
                sock.send(len(msg).to_bytes(4, "big") + msg)
                return

            elif msg["action"] == "join_game":
                print("join game")
                role = msg["role"]
                room_id = msg["room_id"]
                gr = self.gameRooms[room_id]
                if gr == None:
                    msg = json.dumps({"ok": False}).encode()
                else:
                    gr.add_player(user, sock, role)

                    msg = json.dumps({"ok": True, "players": len(gr.users)}).encode()
                sock.send(len(msg).to_bytes(4, "big") + msg)
                return
            elif msg["action"] == "start_game":
                print("start game")
                room_id = msg["room_id"]
                gr = self.gameRooms.get(room_id)
                if gr is None:
                    reply = {"ok": False, "error": "Room not found."}
                else:
                    threading.Thread(target=gr.game_loop, daemon=True).start()
                    msg = json.dumps({"ok": True}).encode()
                sock.send(len(msg).to_bytes(4, "big") + msg)
                return

            elif msg["action"] == "exit":
                print("exit game")
                msg = json.dumps({"ok": True}).encode()
                sock.send(len(msg).to_bytes(4, "big") + msg)
                sock.close()
                break
            else:
                print("error")
                msg = json.dumps({"ok": False}).encode()
                sock.send(len(msg).to_bytes(4, "big") + msg)
                return


def main():
    server = Server()
    server.accept_loop()


if __name__ =="__main__":
    main()