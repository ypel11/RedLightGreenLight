import socket
import struct
import cv2
import numpy as np
import pickle

IP = '10.100.102.84'
PORT = 5000

def recv_all(sock, length):
    data = b""
    while len(data) < length:
        packet = sock.recv(length - len(data))
        if not packet:
            raise ConnectionError("Socket closed before we received all data")
        data += packet
    return data
def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((IP, PORT))
    cap = cv2.VideoCapture(0)
    game_active = True
    end = None
    while cap.isOpened() and game_active:
        # Check for game win
        is_win = False
        if cv2.waitKey(1) & 0xFF == ord(" "):
            is_win = True
        ret, frame = cap.read()
        success, jpg = cv2.imencode('.jpg', frame)
        buffer = jpg.tobytes()
        print(len(buffer))
        sock.send(struct.pack(">?I", is_win, len(buffer)))
        sock.send(buffer)
        header = recv_all(sock, 5)
        game_active, size = struct.unpack(">?I", header)
        payload = recv_all(sock, size)
        arr = np.frombuffer(payload, np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        end = frame
        cv2.imshow("Game", frame)
    cap.release()
    while True:
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break




if __name__ == "__main__":
    main()
