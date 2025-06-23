
# gui_client_pyqt.py
import Utils
import sys, socket, struct, threading, json, winsound
import cv2, numpy as np
from PyQt5 import QtCore, QtWidgets, QtGui
from PyQt5.QtWidgets import QVBoxLayout, QSpacerItem, QSizePolicy
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
from PyQt5.QtCore import QUrl
from Crypto.PublicKey import RSA
from Crypto.Random import get_random_bytes



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

    def __init__(self, sock, aes, role):
        super().__init__()
        self.sock = sock
        self.aes = aes
        self.role = role
        self.running = True


    def run(self):
        try:
            while self.running:
                # Header: 1 byte game_active (ignored here) + 1 byte alive + 4 bytes size
                header = Utils.recv_encrypted(self.sock, self.aes)
                game_active, alive, red_light = struct.unpack(">???", header[:3])
                payload = header[3:]
                arr = np.frombuffer(payload, np.uint8)
                frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                if frame is not None:
                    self.frame_received.emit(frame, red_light)
                if not game_active:
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

# ─── Menu Window ────────────────────────────────────────────────────────────────

class MenuWindow(QtWidgets.QMainWindow):
    def __init__(self, sock, aes, user):
        super().__init__()
        self.sock = sock
        self.aes = aes
        self.user = user

        self.setWindowTitle("Red Light Green Light — Main Menu")
        self.resize(800, 600)
        self.setMinimumSize(800, 600)
        self.setMaximumSize(800, 600)
        palette = QtGui.QPalette()
        brush = QtGui.QBrush(QtGui.QColor(255, 255, 255))
        brush.setStyle(QtCore.Qt.SolidPattern)
        palette.setBrush(QtGui.QPalette.Active, QtGui.QPalette.Base, brush)
        palette.setBrush(QtGui.QPalette.Active, QtGui.QPalette.Window, brush)
        self.setPalette(palette)

        # Central widget
        self.centralwidget = QtWidgets.QWidget(self)
        self.setCentralWidget(self.centralwidget)
        # ─── Logo and Background ─────────────────────────────────────────────────────

        self.Background = QtWidgets.QLabel(self.centralwidget)
        self.Background.setGeometry(QtCore.QRect(0, 50, 801, 511))
        self.Background.setText("")
        self.Background.setPixmap(QtGui.QPixmap("Background.jpg"))
        self.Background.setScaledContents(True)
        self.Background.setWordWrap(False)
        self.Background.setOpenExternalLinks(False)
        self.Background.setObjectName("Background")
        self.Logo = QtWidgets.QLabel(self.centralwidget)
        self.Logo.setGeometry(QtCore.QRect(310, 0, 191, 51))
        self.Logo.setText("")
        self.Logo.setPixmap(QtGui.QPixmap("RED LIGHT GREEN LIGHT.png"))
        self.Logo.setScaledContents(False)
        self.Logo.setAlignment(QtCore.Qt.AlignCenter)
        self.Logo.setObjectName("Logo")

        # ─── Widget Group 1: “Main Menu” (Create/Join/Stats/Exit) ─────────────────

        self.main_menu_widget = QtWidgets.QWidget(self.centralwidget)
        self.main_menu_widget.setGeometry(QtCore.QRect(0, 90, 280, 260))
        self.main_menu_widget.setObjectName("verticalLayoutWidget")
        self.main_menu = QtWidgets.QVBoxLayout(self.main_menu_widget)
        self.main_menu.setContentsMargins(0, 0, 0, 0)
        self.main_menu.setObjectName("main_menu")

        self.create_button = QtWidgets.QPushButton("Create a game", self.main_menu_widget)
        self.create_button.setFont(QtGui.QFont("Bernard MT Condensed", 24))
        self.create_button.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        self.create_button.clicked.connect(self.on_create_clicked)
        self.main_menu.addWidget(self.create_button)

        self.join_button = QtWidgets.QPushButton("Join a game", self.main_menu_widget)
        self.join_button.setFont(QtGui.QFont("Bernard MT Condensed", 24))
        self.join_button.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        self.join_button.clicked.connect(self.on_join_clicked)
        self.main_menu.addWidget(self.join_button)

        self.statistics_button = QtWidgets.QPushButton("Statistics", self.main_menu_widget)
        self.statistics_button.setFont(QtGui.QFont("Bernard MT Condensed", 24))
        self.statistics_button.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        self.statistics_button.clicked.connect(self.on_statistics_clicked)

        self.main_menu.addWidget(self.statistics_button)

        self.exit_button = QtWidgets.QPushButton("Exit", self.main_menu_widget)
        self.exit_button.setFont(QtGui.QFont("Bernard MT Condensed", 24))
        self.exit_button.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        self.exit_button.clicked.connect(self.on_exit_clicked)
        self.main_menu.addWidget(self.exit_button)

        # ─── Widget Group 2: “Game Settings” form ─────────────────────────────────

        self.settings_widget = QtWidgets.QWidget(self.centralwidget)
        self.settings_widget.setGeometry(0, 90, 500, 400)

        layout2 = QtWidgets.QFormLayout(self.settings_widget)
        layout2.setContentsMargins(10, 10, 10, 10)

        # Light duration
        self.light_duration_label = QtWidgets.QLabel("Light duration:", self.settings_widget)
        self.light_duration_label.setFont(QtGui.QFont("Bernard MT Condensed", 20))
        layout2.setWidget(0, QtWidgets.QFormLayout.LabelRole, self.light_duration_label)

        self.light_duration_combo = QtWidgets.QComboBox(self.settings_widget)
        self.light_duration_combo.setFont(QtGui.QFont("Bernard MT Condensed", 20))
        self.light_duration_combo.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))

        for val in ["1", "2", "3", "5", "10", "30", "random"]:
            self.light_duration_combo.addItem(val)
        layout2.setWidget(0, QtWidgets.QFormLayout.FieldRole, self.light_duration_combo)

        # Max players
        self.max_players_label = QtWidgets.QLabel("Max players:", self.settings_widget)
        self.max_players_label.setFont(QtGui.QFont("Bernard MT Condensed", 20))

        layout2.setWidget(1, QtWidgets.QFormLayout.LabelRole, self.max_players_label)

        self.max_players_combo = QtWidgets.QComboBox(self.settings_widget)
        self.max_players_combo.setFont(QtGui.QFont("Bernard MT Condensed", 20))
        for i in range(1, 7):
            self.max_players_combo.addItem(str(i))
        layout2.setWidget(1, QtWidgets.QFormLayout.FieldRole, self.max_players_combo)

        # Role
        self.role_label = QtWidgets.QLabel("Role:", self.settings_widget)
        self.role_label.setFont(QtGui.QFont("Bernard MT Condensed", 20))
        layout2.setWidget(2, QtWidgets.QFormLayout.LabelRole, self.role_label)

        self.create_role_combo = QtWidgets.QComboBox(self.settings_widget)
        self.create_role_combo.setFont(QtGui.QFont("Bernard MT Condensed", 20))
        self.create_role_combo.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))

        for val in ["player", "spectator"]:
            self.create_role_combo.addItem(val)
        layout2.setWidget(2, QtWidgets.QFormLayout.FieldRole, self.create_role_combo)

        # “Create game” and “Back” buttons
        self.settings_create_button = QtWidgets.QPushButton("Create game", self.settings_widget)
        self.settings_create_button.setFont(QtGui.QFont("Bernard MT Condensed", 20))
        self.settings_create_button.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        self.settings_create_button.clicked.connect(self.on_create_submit)
        layout2.setWidget(3, QtWidgets.QFormLayout.FieldRole, self.settings_create_button)

        self.settings_back_button = QtWidgets.QPushButton("Back", self.settings_widget)
        self.settings_back_button.setFont(QtGui.QFont("Bernard MT Condensed", 20))
        self.settings_back_button.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        self.settings_back_button.clicked.connect(self.on_create_back)
        layout2.setWidget(4, QtWidgets.QFormLayout.FieldRole, self.settings_back_button)

        # ─── Widget Group 3: “Join a game” form ───────────────────────────────────

        self.join_widget = QtWidgets.QWidget(self.centralwidget)
        self.join_widget.setGeometry(0, 90, 500, 400)

        layout3 = QtWidgets.QFormLayout(self.join_widget)
        layout3.setContentsMargins(10, 10, 10, 10)

        # Game code
        self.join_label = QtWidgets.QLabel("Game code:", self.join_widget)
        self.join_label.setFont(QtGui.QFont("Bernard MT Condensed", 20))
        layout3.setWidget(0, QtWidgets.QFormLayout.LabelRole, self.join_label)


        self.join_lineedit = QtWidgets.QLineEdit(self.join_widget)
        self.join_lineedit.setFont(QtGui.QFont("Bernard MT Condensed", 20))
        layout3.setWidget(0, QtWidgets.QFormLayout.FieldRole, self.join_lineedit)

        # Role
        self.role_label = QtWidgets.QLabel("Role:", self.settings_widget)
        self.role_label.setFont(QtGui.QFont("Bernard MT Condensed", 20))
        layout3.setWidget(1, QtWidgets.QFormLayout.LabelRole, self.role_label)

        self.join_role_combo = QtWidgets.QComboBox(self.settings_widget)
        self.join_role_combo.setFont(QtGui.QFont("Bernard MT Condensed", 20))
        self.join_role_combo.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))

        for val in ["player", "spectator"]:
            self.join_role_combo.addItem(val)
        layout3.setWidget(1, QtWidgets.QFormLayout.FieldRole, self.join_role_combo)

        # “Create game” and “Back” buttons
        self.join_submit_button = QtWidgets.QPushButton("Join game", self.join_widget)
        self.join_submit_button.setFont(QtGui.QFont("Bernard MT Condensed", 20))
        self.join_submit_button.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        self.join_submit_button.clicked.connect(self.on_join_submit)
        layout3.setWidget(2, QtWidgets.QFormLayout.FieldRole, self.join_submit_button)

        self.join_back_button = QtWidgets.QPushButton("Back", self.join_widget)
        self.join_back_button.setFont(QtGui.QFont("Bernard MT Condensed", 20))
        self.join_back_button.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        self.join_back_button.clicked.connect(self.on_join_back)
        layout3.setWidget(3, QtWidgets.QFormLayout.FieldRole, self.join_back_button)


        # Raise the sub‐widgets above the background in the correct z‐order:
        for w in (self.main_menu_widget, self.settings_widget, self.join_widget, self.Logo):
            w.raise_()

        # Initially, show only the main menu:
        self.main_menu_widget.setVisible(True)
        self.settings_widget.setVisible(False)
        self.join_widget.setVisible(False)

    # ─── Button callbacks ─────────────────────────────────────────────────────────

    def on_create_clicked(self):
        # Hide main menu, show settings form:
        self.main_menu_widget.setVisible(False)
        self.settings_widget.setVisible(True)
        self.join_widget.setVisible(False)

    def on_create_back(self):
        # Hide settings form, show main menu again
        self.settings_widget.setVisible(False)
        self.main_menu_widget.setVisible(True)
        self.join_widget.setVisible(False)

    def on_create_submit(self):
        # User clicked “Create game” inside the settings form:
        light_dur = self.light_duration_combo.currentText()
        max_players = int(self.max_players_combo.currentText())
        role = self.create_role_combo.currentText()

        msg = json.dumps({
            "action": "create_game",
            "user": self.user,
            "role": role,
            "light_duration": int(light_dur) if light_dur.isdigit() else light_dur,
            "max_players": max_players
        }).encode()

        Utils.send_encrypted(self.sock, self.aes, msg)
        reply_buffer = Utils.recv_encrypted(self.sock, self.aes)
        reply = json.loads(reply_buffer)
        if reply.get("ok"):
            if reply.get("ok"):
                room_id = reply["room_id"]
                self.game_window = GameWindow(self.sock, self.aes, role, room_id, True, max_players)
                self.game_window.show()
                self.hide()
        else:
            QtWidgets.QMessageBox.warning(self, "Error", "Unable to create game")

    def on_join_clicked(self):
        # Hide main menu, show join form:
        self.main_menu_widget.setVisible(False)
        self.join_widget.setVisible(True)
        self.settings_widget.setVisible(False)

    def on_join_back(self):
        # Hide join form, go back to main menu:
        self.join_widget.setVisible(False)
        self.main_menu_widget.setVisible(True)
        self.settings_widget.setVisible(False)

    def on_join_submit(self):
        room_id = self.join_lineedit.text().strip()
        role = self.join_role_combo.currentText()
        if not room_id:
            QtWidgets.QMessageBox.warning(self, "Error", "Please enter a valid Game code.")
            return

        msg = json.dumps({
            "action":  "join_game",
            "user":    self.user,
            "role":    role,
            "room_id": room_id
        }).encode()
        Utils.send_encrypted(self.sock, self.aes, msg)
        reply_buffer = Utils.recv_encrypted(self.sock, self.aes)
        reply = json.loads(reply_buffer)
        if reply.get("ok"):
            max_players = reply.get("max_players", None)
            print(max_players)
            self.game_window = GameWindow(self.sock, self.aes, role, room_id, False, max_players)
            self.game_window.show()
            self.hide()
        else:
            QtWidgets.QMessageBox.warning(self, "Error", "Unable to join game")

    def on_statistics_clicked(self):
        # ask the server for stats
        msg = json.dumps({"action": "get_stats", "user": self.user}).encode()
        Utils.send_encrypted(self.sock, self.aes, msg)

        raw = Utils.recv_encrypted(self.sock, self.aes)
        resp = json.loads(raw)
        if not resp.get("ok"):
            QtWidgets.QMessageBox.warning(self, "Stats Error", "Couldn’t fetch statistics.")
            return

        games = resp["games_played"]
        wins = resp["wins"]
        losses = resp["losses"]
        rate = (wins / games * 100) if games else 0

        text = (f"Games played: {games}\n"
                f"Wins: {wins}\n"
                f"Losses: {losses}\n"
                f"Win rate: {rate:.1f}%")
        QtWidgets.QMessageBox.information(self, "Your Statistics", text)
    def on_exit_clicked(self):
        self.close()

# ─── Game Window ────────────────────────────────────────────────────────────────

class GameWindow(QtWidgets.QMainWindow):
    def __init__(self, sock, aes, role, room_id, host, max_players):
        super().__init__()
        self.sock = sock
        self.aes = aes
        self.last_red = False
        self.media_player = QMediaPlayer(self)
        self.last_red = None
        self.WIDTH = 1200
        self.HEIGHT = 900
        super().resize(self.WIDTH, self.HEIGHT)
        self.setWindowTitle(f"Red Light Green Light — {role.title()}")
        self.role = role
        self.host = host
        self.max_players = max_players
        self.room_id = room_id
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
        self.room_id_label = QtWidgets.QLabel(f"Room ID: {room_id}", self.centralwidget)
        self.room_id_label.setFont(QtGui.QFont("Bernard MT Condensed", 20))
        self.room_id_label.setGeometry(20, 5, 300, 100)

        self.setCentralWidget(self.centralwidget)
        self.menubar = QtWidgets.QMenuBar(self)
        self.menubar.setGeometry(QtCore.QRect(0, 0, 1134, 21))
        self.menubar.setObjectName("menubar")
        self.setMenuBar(self.menubar)
        self.statusbar = QtWidgets.QStatusBar(self)
        self.statusbar.setObjectName("statusbar")
        self.setStatusBar(self.statusbar)

        self.waiting_for_start = False
        if self.host:
            if self.role == 'player':
                # Host is a player; waiting if max_players > 1
                if self.max_players and self.max_players > 1:
                    self.waiting_for_start = True
            else:
                # Host is a spectator; always waiting initially (game starts when host triggers or room fills)
                self.waiting_for_start = True

        if self.host and self.waiting_for_start:
            self.start_button = QtWidgets.QPushButton("Start Game", self.centralwidget)
            self.start_button.setFont(QtGui.QFont("Bernard MT Condensed", 18))
            self.start_button.setGeometry(self.WIDTH - 180, 20, 160, 50)  # position it at top-right
            self.start_button.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
            self.start_button.clicked.connect(self.on_start_game_clicked)

        if role == 'player':
            # Create "Win" button as before
            self.win_button = QtWidgets.QPushButton(self.frame)
            self.win_button.setText("Win!")
            self.win_button.setGeometry((self.frame.width() // 2) - 50, self.frame.height() - 100, 100, 40)
            self.win_button.clicked.connect(self.win_pressed)

            if not (self.host and self.waiting_for_start):
                # Not waiting: start capturing immediately
                self.cap_thread = CaptureThread()
                self.cap_thread.send_frame.connect(self.on_send_frame)
                self.cap_thread.start()
            else:
                # Waiting for start: do not start capture yet
                self.cap_thread = None

        # Threads
        self.net_thread = NetworkThread(self.sock, self.aes, role)
        self.net_thread.frame_received.connect(self.update_frame)
        self.net_thread.finished.connect(self.on_finished)
        self.net_thread.start()


    def win_pressed(self):
        self.win_flag = True

    def on_start_game_clicked(self):
        # Construct start_game request
        room_id = self.room_id  # stored earlier
        msg = json.dumps({"action": "start_game", "room_id": room_id}).encode()
        Utils.send_encrypted(self.sock, self.aes, msg)

        self.start_button.setEnabled(False)

        # if host is also a player, kick off the camera now
        if self.role == 'player' and self.cap_thread is None:
            self.cap_thread = CaptureThread()
            self.cap_thread.send_frame.connect(self.on_send_frame)
            self.cap_thread.start()

        # Disable the Start button to prevent multiple clicks
        if hasattr(self, 'start_button'):
            self.start_button.setEnabled(False)

        # If host is a player and capture was not started, start it now
        if self.role == 'player' and self.cap_thread is None:
            self.cap_thread = CaptureThread()
            self.cap_thread.send_frame.connect(self.on_send_frame)
            self.cap_thread.start()
    def on_send_frame(self, buffer):
        # header: 1 byte win + 4 byte size
        plaintext = struct.pack(">?",  self.win_flag) + buffer
        Utils.send_encrypted(self.sock, self.aes, plaintext)

    def light_changed(self, red: bool):
        if red == self.last_red:
            return
        self.last_red = red

        fn = "redlight.mp3" if red else "greenlight.mp3"
        url = QUrl.fromLocalFile(fn)
        self.media_player.setMedia(QMediaContent(url))
        self.media_player.play()


    def update_background(self, red_light : bool):
        palette = QtGui.QPalette()
        if red_light:
            brush = QtGui.QBrush(QtGui.QColor(255, 49, 49))
        else:
            brush = QtGui.QBrush(QtGui.QColor(0, 191, 99))
        brush.setStyle(QtCore.Qt.SolidPattern)
        palette.setBrush(QtGui.QPalette.Active, QtGui.QPalette.Window, brush)
        palette.setBrush(QtGui.QPalette.Inactive, QtGui.QPalette.Window, brush)
        self.frame.setPalette(palette)


    def update_frame(self, frame: np.ndarray, red_light : bool):
        # convert BGR→RGB→QImage
        self.light_changed(red_light)
        self.update_background(red_light)
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        bytes_per_line = ch * w
        qt_img = QtGui.QImage(rgb.data, w, h, bytes_per_line, QtGui.QImage.Format_RGB888)
        pix = QtGui.QPixmap.fromImage(qt_img).scaled(self.video_label.size(), QtCore.Qt.KeepAspectRatio)
        self.video_label.setPixmap(pix)
        self.video_label.updateGeometry()

    def on_finished(self):
        #QtWidgets.QMessageBox.information(self, "Game Over", "The game has ended.")
        if self.role == 'player':
            self.cap_thread.stop()
        self.net_thread.stop()
        try: self.sock.close()
        except Exception as ex: print(ex)


# ─── Entry Point ────────────────────────────────────────────────────────────────

def main():
    app = QtWidgets.QApplication(sys.argv)

    # 1) Create raw TCP socket and connect
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((SERVER_HOST, SERVER_PORT))

    # 2) Immediately receive the RSA public key length + bytes
    raw_len = Utils.recv_all(sock, 4)
    pub_len = int.from_bytes(raw_len, "big")
    pub_der = Utils.recv_all(sock, pub_len)
    server_rsa_pub = RSA.import_key(pub_der)

    # 3) Generate a new AES key, encrypt it under RSA, send to server
    aes_key = get_random_bytes(16)  # 128 bits
    enc_aes = Utils.rsa_encrypt(server_rsa_pub, aes_key)
    sock.send(len(enc_aes).to_bytes(4, "big") + enc_aes)

    # 4) Now loop over login/signup: everything is under AES
    login_success = False
    user = None
    for i in range(0,3):
        dialog = LoginDialog()
        if dialog.exec_() != QtWidgets.QDialog.Accepted:
            sys.exit(0)
        action, user, pw = dialog.get_result()
        # Send auth JSON
        msg = json.dumps({"action": action, "user": user, "pass": pw}).encode()
        Utils.send_encrypted(sock, aes_key, msg)

        # Validate auth
        raw = Utils.recv_encrypted(sock, aes_key)
        reply = json.loads(raw)
        if reply.get("ok"):
            login_success = True
            break
        else:
            QtWidgets.QMessageBox.critical(None, "Auth Failed", reply.get("error", "", )+"\n Try again")

    if not login_success:
        QtWidgets.QMessageBox.critical(None, "Auth Failed", "Too many attempts, login failed.")
        sys.exit(1)

    win = MenuWindow(sock, aes_key, user)
    win.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()