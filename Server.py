import socket
import threading
import pickle
import struct
import cv2
from Game import Game  # Ensure Game.py is in the same directory

IP = "0.0.0.0"
PORT = 5000

def recv_all(sock, length):
    data = b""
    while len(data) < length:
        packet = sock.recv(length - len(data))
        if not packet:
            raise ConnectionError("Socket closed before we received all data")
        data += packet
    return data

def handle_game(client_socket):
    time = client_socket.recv(8)
    time = struct.unpack("I", time)[0]
    game = Game(time)
    game_active = True
    while game_active:
        data = client_socket.recv(8)
        is_win, size = struct.unpack("? I", data)
        data = recv_all(client_socket, size)
        jpg_frame = pickle.loads(data)
        frame = cv2.imdecode(jpg_frame, cv2.IMREAD_COLOR)
        game_active, frame = game.recv_frame(frame, is_win)
        success, jpg_frame = cv2.imencode('.jpg', frame)
        buffer = pickle.dumps(jpg_frame)
        client_socket.send(struct.pack("? I", game_active, len(buffer)))
        client_socket.send(buffer)
    client_socket.close()

def main():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind((IP, PORT))
    server_socket.listen()
    print(f"Listening for connections on port {PORT}")

    while True:
        client_socket, client_address = server_socket.accept()
        print(f"New connection received from {client_address}")
        client_thread = threading.Thread(target=handle_game, args=(client_socket,))
        client_thread.start()


if __name__ == "__main__":
    main()