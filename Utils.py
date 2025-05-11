import struct
import numpy as np
import cv2
import pickle


def send_frame(sock, frame, recv_more, send_more):
    # overlay alive_flag or whatever on frame first…
    success, jpg = cv2.imencode('.jpg', frame)
    if not success:
        return
    buffer = jpg.tobytes()
    # send 1 byte alive_flag + 4 bytes length + raw JPEG
    sock.send(struct.pack(">??I",  recv_more, send_more, len(buffer)))
    sock.send(buffer)
def recv_all(sock, n):
    data = b""
    while len(data) < n:
        packet = sock.recv(n - len(data))
        if not packet:
            raise ConnectionError("Socket closed")
        data += packet
    return data


def stack_frames(frames, grid_size=(2,3)):
    h, w = frames[0].shape[:2]
    blank = np.zeros_like(frames[0])
    # pad if needed
    while len(frames) < grid_size[0]*grid_size[1]:
        frames.append(blank)
    rows = []
    for i in range(0, len(frames), grid_size[1]):
        rows.append(np.hstack(frames[i:i+grid_size[1]]))
    return np.vstack(rows)