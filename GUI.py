import sys
import cv2
import struct
import numpy as np
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QLabel, QPushButton, QWidget, QVBoxLayout,
    QHBoxLayout, QMessageBox
)
import socket

# Network client worker thread
def recv_all(sock, length):
    data = b""
    while len(data) < length:
        packet = sock.recv(length - len(data))
        if not packet:
            raise ConnectionError("Socket closed")
        data += packet
    return data

class NetworkWorker(QThread):
    frame_received = pyqtSignal(np.ndarray)
    game_over = pyqtSignal(bool)

    def __init__(self, ip, port, parent=None):
        super().__init__(parent)
        self.ip = ip
        self.port = port
        self.running = False
        self.win_flag = False

    def run(self):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((self.ip, self.port))
        except Exception as e:
            QMessageBox.critical(None, "Connection Error", f"Failed to connect: {e}")
            return

        cap = cv2.VideoCapture(0)
        self.running = True

        while self.running:
            ret, frame = cap.read()
            if not ret:
                continue

            # Send frame and win status
            success, jpg = cv2.imencode('.jpg', frame)
            if not success:
                continue
            buf = jpg.tobytes()
            header = struct.pack('>?I', self.win_flag, len(buf))
            sock.send(header + buf)
            self.win_flag = False

            # Receive header
            header_size = struct.calcsize('>??I')
            raw = recv_all(sock, header_size)
            game_active, alive, size = struct.unpack('>??I', raw)

            data = recv_all(sock, size)
            arr = np.frombuffer(data, np.uint8)
            out_frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)

            # Emit new frame
            self.frame_received.emit(out_frame)

            if not game_active:
                self.running = False
                self.game_over.emit(alive)

        cap.release()
        sock.close()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Red Light, Green Light Game')
        self.ip = 'server ip'
        self.port = 5000

        # UI Elements
        self.video_label = QLabel()
        self.video_label.setFixedSize(640, 480)
        self.status_label = QLabel('Status: Disconnected')
        self.win_button = QPushButton('Declare Win (Space)')
        self.start_button = QPushButton('Start Game')
        self.quit_button = QPushButton('Quit')

        # Layouts
        btn_layout = QHBoxLayout()
        btn_layout.addWidget(self.start_button)
        btn_layout.addWidget(self.win_button)
        btn_layout.addWidget(self.quit_button)

        main_layout = QVBoxLayout()
        main_layout.addWidget(self.video_label)
        main_layout.addWidget(self.status_label)
        main_layout.addLayout(btn_layout)

        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)

        # Connections
        self.start_button.clicked.connect(self.start_game)
        self.win_button.clicked.connect(self.declare_win)
        self.quit_button.clicked.connect(self.close)

        self.network_thread = None

    def start_game(self):
        if self.network_thread and self.network_thread.running:
            return
        self.network_thread = NetworkWorker(self.ip, self.port)
        self.network_thread.frame_received.connect(self.update_video)
        self.network_thread.game_over.connect(self.handle_game_over)
        self.network_thread.start()
        self.status_label.setText('Status: Playing...')

    def declare_win(self):
        if self.network_thread and self.network_thread.running:
            self.network_thread.win_flag = True

    def update_video(self, frame):
        # Convert to QImage and display
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        bytes_per_line = ch * w
        qt_img = QImage(rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
        pix = QPixmap.fromImage(qt_img)
        self.video_label.setPixmap(pix)

    def handle_game_over(self, alive):
        msg = "You Won!" if alive else "You Lost!"
        QMessageBox.information(self, 'Game Over', msg)
        self.status_label.setText('Status: Game Over')

if __name__ == '__main__':
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())
