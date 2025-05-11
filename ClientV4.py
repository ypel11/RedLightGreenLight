
import socket
import struct
import cv2
import numpy as np
import pickle

IP = 'SERVER IP'
PORT = 5000

def send_frame(sock, frame, alive_flag):
    # overlay alive_flag or whatever on frame first…
    success, jpg = cv2.imencode('.jpg', frame)
    if not success:
        return
    buffer = jpg.tobytes()
    # send 1 byte alive_flag + 4 bytes length + raw JPEG
    sock.send(struct.pack(">?I", alive_flag, len(buffer)))
    sock.send(buffer)

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
    alive = True
    while game_active:
        is_win = False
        ret, frame = cap.read()
        # Check for game win
        if cv2.waitKey(1) & 0xFF == ord(" "):
            is_win = True

        # Send recent frame
        if alive:
            send_frame(sock, frame, is_win)

        # Receive result
        header = recv_all(sock, 6)
        game_active, alive, size = struct.unpack(">??I", header)
        payload = recv_all(sock, size)
        arr = np.frombuffer(payload, np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        cv2.imshow("Game", frame)

        # If game is over receive results and close connection
        if not game_active:
            sock.close()
            break

    while True:
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break
    cap.release()
    cv2.destroyAllWindows()




if __name__ == "__main__":
    main()
