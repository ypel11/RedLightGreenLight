
import socket, threading, struct, time, random, string, cv2, numpy as np, sqlite3, json, bcrypt
from GameLogic import Game
import Utils
HOST = '0.0.0.0'
PORT = 5000
MAX_PLAYERS = 1
TICK = 0.05



class GameRoom:

    def __init__(self, light_duration, max_players):
        self.users = {}   # username -> { 'game':Game(), 'sock':socket, 'aes_key':bytes, 'frame':None, 'active':True }
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

    def add_player(self, user, sock, aes_key, role):
        with self.lock:
            if role == 'player':
                game = Game()
                self.users[user] = {'game': game, 'sock': sock, 'aes': aes_key,'frame': None, 'active': True}
                print(f"{user} has joined the game")
                threading.Thread(target=self.recv_loop, args=(user, ), daemon=True).start()
                if len(self.users) == self.max_players:
                    threading.Thread(target=self.game_loop, daemon=True).start()
                return True
            elif role == 'spectator':
                self.spectators.append((sock, aes_key))
                print(f"[GameRoom {self.room_id}] A spectator joined.")
                return True
            return False



    def recv_loop(self, user):
        game = self.users[user]['game']
        aes = self.users[user]['aes']
        sock = self.users[user]['sock']
        active = self.users[user]['active']
        try:
            while active and self.winner is None:
                plaintext = Utils.recv_encrypted(sock, aes)
                win_flag = plaintext[0]
                payload = plaintext[1:]
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
                    aes = info['aes']
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
                    success, jpg = cv2.imencode('.jpg', frame)
                    if not success:
                        return
                    buffer = jpg.tobytes()
                    plaintext = struct.pack(">???", True, alive, self.red_light) + buffer
                    Utils.send_encrypted(sock, aes, plaintext)
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
                    success, jpg = cv2.imencode('.jpg', frame)
                    if not success:
                        return
                    buffer = jpg.tobytes()
                    plaintext = struct.pack(">???", True, True, self.red_light) + buffer
                    for sock, aes in self.spectators:
                        Utils.send_encrypted(sock, aes, plaintext)

        # game ended, send final result frames once more
        # overlay result on the last out frame
        frame = 255 * np.ones((300, 800, 3), np.uint8)
        text = f"Winner: player {self.winner[1]} from  {self.winner[0]}'s game" if self.winner else "Everyone Lost"
        color = (0, 255, 0) if self.winner else (0, 0, 255)
        cv2.putText(frame, text, (20, 100), cv2.QT_FONT_NORMAL, 1.2, color, 2)
        success, jpg = cv2.imencode('.jpg', frame)
        if not success:
            return
        buffer = jpg.tobytes()
        plaintext = struct.pack(">???", False, False, self.red_light) + buffer
        conn = sqlite3.connect("Users.db")
        c = conn.cursor()
        for info in self.users.values():
            Utils.send_encrypted(info['sock'], info['aes'], plaintext)
            won = int(self.winner is not None and self.winner[0] == user)
            c.execute("INSERT INTO results(username, won) VALUES (?, ?)", (user, won))
        conn.commit()
        conn.close()
        for spec, aes in self.spectators:
            Utils.send_encrypted(spec, aes, plaintext)

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
        self.sessions  = {}   # username -> aes_key
        self.users = {}   # username -> socket
        self.gameRooms = {}   # room_id  -> GameRoom instance
        self.server_private, self.server_public = Utils.generate_rsa_keypair()


    def init_db(self):
        conn = sqlite3.connect(self.DB)
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                pw_hash   BLOB
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS results (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                username  TEXT,
                won       INTEGER,           -- 1 = win, 0 = loss
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()

    def handle_auth(self, sock, aes_key):
        """
        After encryption handshake is done, we receive:
          {"action":"login"/"signup","user":..,"pass":..}
        over AES. We decrypt via aes_key and then reply (encrypted).
        """
        try:
            plaintext = Utils.recv_encrypted(sock, aes_key)
            msg = json.loads(plaintext.decode())
        except ConnectionError:
            return (None, False)

        username = msg["user"]
        password = msg["pass"].encode()

        db = sqlite3.connect(self.DB)
        cur = db.cursor()

        if msg["action"] == "signup":
            cur.execute("SELECT 1 FROM users WHERE username=?", (username,))
            if cur.fetchone():
                reply = {"ok": False, "error": "Username taken."}
            else:
                pw_hash = bcrypt.hashpw(password, bcrypt.gensalt())
                cur.execute("INSERT INTO users VALUES (?, ?)", (username, pw_hash))
                db.commit()
                reply = {"ok": True}

        elif msg["action"] == "login":
            cur.execute("SELECT pw_hash FROM users WHERE username=?", (username,))
            row = cur.fetchone()
            if not row:
                reply = {"ok": False, "error": "Username not found."}
            elif bcrypt.checkpw(password, row[0]):
                reply = {"ok": True}
            else:
                reply = {"ok": False, "error": "Password invalid."}
        else:
            reply = {"ok": False, "error": "Unknown action."}

        db.close()

        # Send the JSON reply under AES encryption
        out = json.dumps(reply).encode()
        Utils.send_encrypted(sock, aes_key, out)
        return username, reply["ok"]

    def accept_loop(self):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.bind((HOST, PORT))
        srv.listen()
        print(f"Server listening on {PORT}")
        while True:
            sock, addr = srv.accept()
            print(f"[Server] Connection from {addr}")

            # Send server’s RSA public key (DER format), length‐prefixed
            pub_der = self.server_public.export_key(format='DER')
            sock.sendall(len(pub_der).to_bytes(4, "big") + pub_der)

            # Receive client’s RSA-encrypted AES key (length‐prefixed)
            raw = sock.recv(4)
            if not raw:
                sock.close()
                continue
            ek_len = int.from_bytes(raw, "big")
            enc_aes_key = Utils.recv_all(sock, ek_len)
            aes_key = Utils.rsa_decrypt(self.server_private, enc_aes_key)

            # Login dialog
            login_success = False
            username = None
            for i in range(3):
                username, ok = self.handle_auth(sock, aes_key)
                if ok:
                    login_success = True
                    break

            if not login_success:
                sock.close()
                print(f"[Server] Authentication failed for {addr}. Socket closed.")
                continue

            self.sessions[username] = aes_key
            self.users[username] = sock
            print(f"[Server] {username} authenticated, AES key established.")

            threading.Thread(
                 target=self.handle_user_request,
                args=(username, ),
                daemon=True
            ).start()

    def handle_user_request(self, user):

        sock = self.users[user]
        aes_key = self.sessions[user]

        while True:
            try:
                msg_buffer = Utils.recv_encrypted(sock, aes_key)
                msg = json.loads(msg_buffer)
            except ConnectionError:
                print(f"[Server] Connection lost for {user}.")
                return

            action = msg.get("action")
            if action == "create_game":
                light_duration = msg["light_duration"]
                if isinstance(light_duration, str) and light_duration == "random":
                    light_duration = random.randint(1, 30)
                max_players = msg["max_players"]
                role = msg["role"]

                gr = GameRoom(light_duration, max_players)
                self.gameRooms[gr.room_id] = gr
                success = gr.add_player(user, sock, aes_key, role)
                reply = {"ok": success, "room_id": gr.room_id}
                Utils.send_encrypted(sock, aes_key, json.dumps(reply).encode())
                break

            elif action == "join_game":
                room_id = msg["room_id"]
                role    = msg["role"]
                if room_id not in self.gameRooms:
                    reply = {"ok": False, "error": "Room not found"}
                    Utils.send_encrypted(sock, aes_key, json.dumps(reply).encode())
                else:
                    gr = self.gameRooms[room_id]
                    success = gr.add_player(user, sock, aes_key, role)
                    if success:
                        reply = {"ok": True, "players": len(gr.users)}
                    else:
                        reply = {"ok": False, "error": "Could not join"}
                    Utils.send_encrypted(sock, aes_key, json.dumps(reply).encode())
                    break

            elif action == "start_game":
                room_id = msg["room_id"]
                if room_id not in self.gameRooms:
                    reply = {"ok": False, "error": "Room not found"}
                else:
                    gr = self.gameRooms[room_id]
                    # If game_loop not already running, spin it off
                    threading.Thread(target=gr.game_loop, daemon=True).start()
                    reply = {"ok": True}
                Utils.send_encrypted(sock, aes_key, json.dumps(reply).encode())
                break

            elif action == "get_stats":
                # pull tallies for this user
                conn = sqlite3.connect(self.DB)
                c = conn.cursor()
                c.execute("SELECT COUNT(*) FROM results WHERE username=?", (user,))
                games = c.fetchone()[0]
                c.execute("SELECT COUNT(*) FROM results WHERE username=? AND won=1", (user,))
                wins = c.fetchone()[0]
                conn.close()
                losses = games - wins
                reply = {
                    "ok": True,
                    "games_played": games,
                    "wins": wins,
                    "losses": losses
                }
                Utils.send_encrypted(sock, aes_key, json.dumps(reply).encode())

            elif action == "exit":
                reply = {"ok": True}
                Utils.send_encrypted(sock, aes_key, json.dumps(reply).encode())
                try: sock.close()
                except: pass
                break

            else:
                reply = {"ok": False, "error": "Unknown action"}
                Utils.send_encrypted(sock, aes_key, json.dumps(reply).encode())
                break

def main():
    server = Server()
    server.accept_loop()


if __name__ =="__main__":
    main()