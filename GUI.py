# gui_client_pyqt.py

import sys, socket, struct, threading, json
import cv2, numpy as np
from PyQt5 import QtCore, QtWidgets, QtGui
from PyQt5.QtWidgets import QVBoxLayout, QSpacerItem, QSizePolicy



with open("client_settings.json") as f:
    CFG = json.load(f)
    SERVER_HOST, SERVER_PORT = CFG["SERVER_HOST"], CFG["SERVER_PORT"]
    TARGET_FPS = CFG["TARGET_FPS"]
    WIDTH, HEIGHT = CFG["FRAME_WIDTH"], CFG["FRAME_HEIGHT"]
    JPEG_Q = CFG["JPEG_QUALITY"]

# ─── Network Thread ────────────────────────────────────────────────────────────

class NetworkThread(QtCore.QThread):
    frame_received = QtCore.pyqtSignal(np.ndarray, bool)
    finished = QtCore.pyqtSignal()

    def __init__(self, sock, role):
        super().__init__()
        self.sock = sock
        self.role = role
        self.running = True

    def recv_all(self, n):
        data = b''
        while len(data) < n:
            packet = self.sock.recv(n - len(data))
            if not packet:
                raise ConnectionError()
            data += packet
        return data

    def run(self):
        try:
            while self.running:
                # Header: 1 byte game_active (ignored here) + 1 byte alive + 4 bytes size
                header = self.recv_all(7)
                red_light, game_active, alive, size = struct.unpack(">???I", header)
                payload = self.recv_all(size)
                arr = np.frombuffer(payload, np.uint8)
                frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                if frame is not None:
                    self.frame_received.emit(frame, red_light)
                if not game_active:
                    self.msleep(20000)
                    break
                self.msleep(33)
        except Exception as e:
            print(e)
        finally:
            self.finished.emit()

    def stop(self):
        self.running = False
        self.wait()


# ─── Player Capture Thread ─────────────────────────────────────────────────────

class CaptureThread(QtCore.QThread):
    send_frame = QtCore.pyqtSignal(bytes)

    def __init__(self):
        super().__init__()
        self.cap = cv2.VideoCapture(0)
        self.running = True

    def run(self):
        while self.running:
            ret, frame = self.cap.read()
            if not ret:
                break
            # check for win flag
            success, jpg = cv2.imencode('.jpg', frame)
            if success:
                data = jpg.tobytes()
                self.send_frame.emit(data)
            self.msleep(33)  # ~30 FPS

    def stop(self):
        self.running = False
        self.cap.release()
        self.wait()


# ─── Login Dialog ───────────────────────────────────────────────────────────────

class LoginDialog(QtWidgets.QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Login / Signup")

        tabs = QtWidgets.QTabWidget(self)
        login_tab = QtWidgets.QWidget()
        signup_tab = QtWidgets.QWidget()
        tabs.addTab(login_tab, "Login")
        tabs.addTab(signup_tab, "Signup")

        # Shared fields
        self.user1 = QtWidgets.QLineEdit()
        self.pass1 = QtWidgets.QLineEdit()
        self.pass1.setEchoMode(QtWidgets.QLineEdit.Password)
        self.user2 = QtWidgets.QLineEdit()
        self.pass2 = QtWidgets.QLineEdit()
        self.pass2.setEchoMode(QtWidgets.QLineEdit.Password)

        # Buttons
        login_btn = QtWidgets.QPushButton("Login")
        signup_btn = QtWidgets.QPushButton("Signup")
        login_btn.clicked.connect(self.do_login)
        signup_btn.clicked.connect(self.do_signup)

        # Layout login
        L1 = QtWidgets.QFormLayout(login_tab)
        L1.addRow("Username:", self.user1)
        L1.addRow("Password:", self.pass1)
        L1.addWidget(login_btn)
        # Layout signup
        L2 = QtWidgets.QFormLayout(signup_tab)
        L2.addRow("Username:", self.user2)
        L2.addRow("Password:", self.pass2)
        L2.addWidget(signup_btn)

        main = QtWidgets.QVBoxLayout(self)
        main.addWidget(tabs)

        self.result = None  # ("login"/"signup", user, pass)

    def do_login(self):
        self.result = ("login", self.user1.text(), self.pass1.text())
        self.accept()

    def do_signup(self):
        self.result = ("signup", self.user2.text(), self.pass2.text())
        self.accept()

    def get_result(self):
        return self.result


# ─── Main Window ────────────────────────────────────────────────────────────────

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, sock, role):
        super().__init__()
        self.sock = sock
        self.WIDTH = 1200
        self.HEIGHT = 900
        super().resize(self.WIDTH, self.HEIGHT)
        self.setWindowTitle(f"Red Light Green Light — {role.title()}")
        self.role = role
        self.win_flag = False

        # Central widget: a QLabel to display video
        self.centralwidget = QtWidgets.QWidget(self)
        self.setCentralWidget(self.centralwidget)

        self.frame = QtWidgets.QFrame(self.centralwidget)
        self.frame.setGeometry(0, 90, self.WIDTH, self.HEIGHT - 90)
        self.frame.setAutoFillBackground(True)
        pal = self.frame.palette()
        pal.setColor(self.frame.backgroundRole(), QtGui.QColor(0, 191, 99))
        self.frame.setPalette(pal)
        self.frame.setMouseTracking(False)
        self.frame.setAutoFillBackground(True)
        self.frame.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.frame.setFrameShadow(QtWidgets.QFrame.Raised)
        self.frame.setObjectName("frame")
        self.video_label = QtWidgets.QLabel(self.frame)
        self.video_label.setStyleSheet("background: black;")  # optional border
        self.video_label.setAlignment(QtCore.Qt.AlignCenter)
        layout = QVBoxLayout(self.frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addSpacerItem(QSpacerItem(0, 0, QSizePolicy.Expanding, QSizePolicy.Expanding))
        layout.addWidget(self.video_label, alignment=QtCore.Qt.AlignCenter)
        layout.addSpacerItem(QSpacerItem(0, 0, QSizePolicy.Expanding, QSizePolicy.Expanding))
        fw = self.frame.width()
        fh = self.frame.height()
        videoW = int(fw * 0.75)
        videoH = int(fh * 0.75)
        self.video_label.setFixedSize(videoW, videoH)
        self.logo = QtWidgets.QLabel(self.centralwidget)
        self.logo.setGeometry(QtCore.QRect(0, -10, self.WIDTH, 101))
        palette = QtGui.QPalette()
        brush = QtGui.QBrush(QtGui.QColor(255, 255, 255))
        brush.setStyle(QtCore.Qt.SolidPattern)
        palette.setBrush(QtGui.QPalette.Active, QtGui.QPalette.Base, brush)
        brush = QtGui.QBrush(QtGui.QColor(255, 255, 255))
        brush.setStyle(QtCore.Qt.SolidPattern)
        palette.setBrush(QtGui.QPalette.Active, QtGui.QPalette.Window, brush)
        brush = QtGui.QBrush(QtGui.QColor(255, 255, 255))
        brush.setStyle(QtCore.Qt.SolidPattern)
        palette.setBrush(QtGui.QPalette.Inactive, QtGui.QPalette.Base, brush)
        brush = QtGui.QBrush(QtGui.QColor(255, 255, 255))
        brush.setStyle(QtCore.Qt.SolidPattern)
        palette.setBrush(QtGui.QPalette.Inactive, QtGui.QPalette.Window, brush)
        brush = QtGui.QBrush(QtGui.QColor(255, 255, 255))
        brush.setStyle(QtCore.Qt.SolidPattern)
        palette.setBrush(QtGui.QPalette.Disabled, QtGui.QPalette.Base, brush)
        brush = QtGui.QBrush(QtGui.QColor(255, 255, 255))
        brush.setStyle(QtCore.Qt.SolidPattern)
        palette.setBrush(QtGui.QPalette.Disabled, QtGui.QPalette.Window, brush)
        self.logo.setPalette(palette)
        self.logo.setAutoFillBackground(True)
        self.logo.setText("")
        self.logo.setPixmap(QtGui.QPixmap("RED LIGHT GREEN LIGHT.png"))
        self.logo.setAlignment(QtCore.Qt.AlignCenter)
        self.logo.setObjectName("logo")
        self.setCentralWidget(self.centralwidget)
        self.menubar = QtWidgets.QMenuBar(self)
        self.menubar.setGeometry(QtCore.QRect(0, 0, 1134, 21))
        self.menubar.setObjectName("menubar")
        self.setMenuBar(self.menubar)
        self.statusbar = QtWidgets.QStatusBar(self)
        self.statusbar.setObjectName("statusbar")
        self.setStatusBar(self.statusbar)


        # Handshake: send role byte
        self.sock.send(b'P' if role == 'player' else b'S')

        if role == 'player':
            # 1) Create the Win button as a child of the same frame that holds your video
            self.win_button = QtWidgets.QPushButton(self.frame)
            # 2) Set its label
            self.win_button.setText("Win!")
            # 3) Position it somewhere—e.g. bottom‐left corner of the frame
            #    Here x=50, y=frame.height()-50, width=100, height=30
            button_width = 100
            button_height = 40
            self.win_button.setGeometry((self.frame.width()//2)-button_width//2,(self.frame.height()-100), button_width, button_height)
            # 4) Wire it up
            self.win_button.setText("Win!")
            self.win_button.clicked.connect(self.button_pressed)
            self.cap_thread = CaptureThread()
            self.cap_thread.send_frame.connect(self.on_send_frame)
            self.cap_thread.start()

        # Threads
        self.net_thread = NetworkThread(self.sock, role)
        self.net_thread.frame_received.connect(self.update_frame)
        self.net_thread.finished.connect(self.on_finished)
        self.net_thread.start()


    def button_pressed(self):
        self.win_flag = True
    def on_send_frame(self, data):
        # header: 1 byte win + 4 byte size
        header = struct.pack(">?I",  self.win_flag, len(data))
        try:
            self.sock.sendall(header + data)
        except Exception as e:
            print(e)

    def update_background(self, red_light : bool):
        palette = QtGui.QPalette()
        if red_light:
            brush = QtGui.QBrush(QtGui.QColor(255, 49, 49))
        else:
            brush = QtGui.QBrush(QtGui.QColor(0, 191, 99))
        brush.setStyle(QtCore.Qt.SolidPattern)
        palette.setBrush(QtGui.QPalette.Active, QtGui.QPalette.Window, brush)
        self.frame.setPalette(palette)


    def update_frame(self, frame: np.ndarray, red_light : bool):
        # convert BGR→RGB→QImage
        self.update_background(red_light)
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        bytes_per_line = ch * w
        qt_img = QtGui.QImage(rgb.data, w, h, bytes_per_line, QtGui.QImage.Format_RGB888)
        pix = QtGui.QPixmap.fromImage(qt_img).scaled(self.video_label.size(), QtCore.Qt.KeepAspectRatio)
        self.video_label.setPixmap(pix)
        self.video_label.updateGeometry()

    def on_finished(self):
        self.msleep(20000)
        #QtWidgets.QMessageBox.information(self, "Game Over", "The game has ended.")
        self.close()

    def closeEvent(self, e):
        # shutdown threads & socket
        if self.role == 'player':
            self.cap_thread.stop()
        self.net_thread.stop()
        try: self.sock.close()
        except Exception as ex: print(ex)
        super().closeEvent(e)


# ─── Entry Point ────────────────────────────────────────────────────────────────

def main():
    app = QtWidgets.QApplication(sys.argv)
    dialog = LoginDialog()
    if dialog.exec_() != QtWidgets.QDialog.Accepted:
        sys.exit(0)

    action, user, pw = dialog.get_result()

    # Connect socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((SERVER_HOST, SERVER_PORT))

    # Send auth JSON
    msg = json.dumps({"action": action, "user": user, "pass": pw}).encode()
    sock.send(len(msg).to_bytes(4, "big") + msg)

    # Validate auth
    raw = sock.recv(4)
    length = int.from_bytes(raw, "big")
    reply = json.loads(sock.recv(length).decode())
    if not reply.get("ok"):
        QtWidgets.QMessageBox.critical(None, "Auth Failed", reply.geot("error", ""))
        sys.exit(1)

    win = MainWindow(sock, "player")
    win.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
