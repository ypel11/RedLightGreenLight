import socket, threading, time, struct, cv2, numpy as np
from Game import Game

HOST, PORT = '0.0.0.0', 5000
MAX_PLAYERS = 10
TICK = 0.1   # 10 Hz

class Client:
    def __init__(self, sock, role):
        self.sock = sock
        self.role = role  # 'P','H','S'
        self.last_frame = None
        self.win_flag = False
        self.alive = True


def stack_frames(frames, grid_size=(2,5)):
    """Tile a list of same‑sized frames into a grid."""
    h, w = frames[0].shape[:2]
    blank = np.zeros_like(frames[0])
    # pad
    while len(frames) < grid_size[0]*grid_size[1]:
        frames.append(blank)
    rows = []
    for i in range(0, len(frames), grid_size[1]):
        rows.append( np.hstack(frames[i:i+grid_size[1]]) )
    return np.vstack(rows)
def recv_all(sock, length):
    data = b""
    while len(data) < length:
        packet = sock.recv(length - len(data))
        if not packet:
            raise ConnectionError("Socket closed before we received all data")
        data += packet
    return data
def send_frame(sock, frame):
    """Encode & send one BGR frame as JPEG with 4-byte length prefix."""
    success, jpg = cv2.imencode('.jpg', frame)
    if not success:
        return
    data = jpg.tobytes()
    sock.sendall(struct.pack(">I", len(data)) + data)

def handle_player(client: Client, game: Game):
    """Thread: receive (win_flag + frame) repeatedly from a player."""
    sock = client.sock
    try:
        while game.game_active and client.alive:
            # 1 byte win flag + 4 bytes frame length
            header = recv_all(sock, 1 + 4)
            win_flag, size = struct.unpack("?I", header)
            payload = recv_all(sock, size)
            # decode JPEG → BGR
            arr = np.frombuffer(payload, np.uint8)
            frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            client.last_frame = frame
            client.win_flag = win_flag
    except Exception:
        pass
    finally:
        client.alive = False

def accept_clients(server_sock, clients, game):
    """Accept exactly MAX_PLAYERS or until host presses Enter."""
    while len([c for c in clients if clients[c].role=='P']) < MAX_PLAYERS:
        sock, addr = server_sock.accept()
        # handshake: client sends 1 ASCII byte role
        role = sock.recv(1).decode()
        client = Client(sock, role)
        clients[sock] = client
        print(f"Connected {addr} as {role}")
        if role == 'P':
            threading.Thread(target=handle_player, args=(client, game), daemon=True).start()

def main():
    # 1) Setup server & Game
    game = Game(light_duration=5)
    clients = {}  # sock -> Client
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((HOST, PORT))
    server.listen()
    print(f"Listening on port {PORT}…")

    # 2) Accept players & host/spectators
    accept_thread = threading.Thread(target=accept_clients, args=(server, clients, game))
    accept_thread.start()
    input("Press Enter to start the game once everyone has joined…\n")
    game.game_active = True

    # 3) Main game loop
    while game.game_active:
        game.change_light()

        alive_frames = []
        # Process each player
        for client in list(clients.values()):
            if client.role == 'P' and client.last_frame is not None:
                alive, processed = game.recv_frame(client.last_frame, client.win_flag)
                client.alive = alive
                client.win_flag = False
                # send personal processed frame
                send_frame(client.sock, processed)
                if alive:
                    alive_frames.append(processed)

        # Build grid for host & spectators
        if alive_frames:
            grid = stack_frames(alive_frames, grid_size=(2,5))
            for client in clients.values():
                if client.role in ('H','S'):
                    send_frame(client.sock, grid)

        # check for early win (Game logic inside recv_frame can set game_active=False)
        time.sleep(TICK)

    # 4) Game ended—send final frames one last time
    for client in clients.values():
        if client.role == 'P' and client.last_frame is not None:
            _, final = game.recv_frame(client.last_frame, client.win_flag)
            send_frame(client.sock, final)
        elif client.role in ('H','S'):
            # replay final grid
            # (reuse last grid if you stored it)
            send_frame(client.sock, grid)
        client.sock.close()

    server.close()
    print("Server shutdown.")

if __name__ == "__main__":
    main()