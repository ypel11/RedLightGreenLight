import socket
import pickle
import struct
import cv2
import numpy as np
import pickle

IP = '10.100.102.84'
PORT = 50002

def recv_all(sock, length):
    data = b""
    while len(data) < length:
        packet = sock.recv(length - len(data))
        if not packet:
            raise ConnectionError("Socket closed before we received all data")
        data += packet
    return data
def main():
    my_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    my_socket.connect((IP, PORT))
    cap = cv2.VideoCapture(0)
    game_active = True
    end = None
    while cap.isOpened() and game_active:
        # Check for game win
        is_win = False
        if cv2.waitKey(1) & 0xFF == ord(" "):
            is_win = True
        ret, frame = cap.read()
        success, encoded_image = cv2.imencode('.jpg', frame)
        buffer = pickle.dumps(encoded_image)
        print(type(buffer))
        my_socket.send(struct.pack("? I", is_win, len(buffer)))
        my_socket.send(buffer)
        data = my_socket.recv(8)
        game_active, size = struct.unpack("? I", data)
        data = recv_all(my_socket, size)
        jpg_frame = pickle.loads(data)
        frame = cv2.imdecode(jpg_frame, cv2.IMREAD_COLOR)
        end = frame
        cv2.imshow("Game", frame)
    cap.release()
    while True:
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break




if __name__ == "__main__":
    main()
