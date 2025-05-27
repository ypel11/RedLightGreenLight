import cv2
import numpy as np
import imutils
import time
from ultralytics import YOLO
from deep_sort_realtime.deepsort_tracker import DeepSort


class Game:

    def __init__(self):
        # ML
        self.model = YOLO("yolov8n.pt")
        self.tracker = DeepSort(max_age=100)
        # Game variables
        self.red_light = False
        self.active = True
        self.winner = None
        self.frame_count = 0
        self.start_time = time.time()
        self.players_position = {}
        self.players_status = {}

    def change_light(self):
        self.red_light = not self.red_light  # Toggle game state


    def check_lost(self):
        # Conditions for game lose
        canvas = None
        if (self.frame_count > 5 and (not any(self.players_status.values()))):
            self.active = False
            message = "Game lost!"
            canvas = 255 * np.ones((200, 600, 3), dtype=np.uint8)
            cv2.putText(canvas, message, (20, 100), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 3)
        return canvas

    def get_winner(self):
        # Find the player with the largest area
        max_area = 0
        winner_id = None
        for track_id, (_, _, area) in self.players_position.items():
            if self.players_status.get(track_id, True) and area > max_area:
                max_area = area
                winner_id = track_id
        self.active = False
        self.winner = winner_id
        message = f"Winner is: {winner_id}!"
        canvas = 255 * np.ones((200, 600, 3), dtype=np.uint8)
        cv2.putText(canvas, message, (20, 100), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 3)
        return canvas

    def get_detections(self, frame):
        # Detect all human objects
        detections = []
        results = self.model(frame)
        for result in results:
            for box in result.boxes:
                cls = int(box.cls[0])
                conf = box.conf[0]
                if cls == 0 and conf > 0.5:
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    detections.append([[x1, y1, x2 - x1, y2 - y1], conf, None])
        return detections

    def update_values(self, frame, win):
        # Update frame count
        self.frame_count = self.frame_count + 1


        # Detect all human objects
        detections = self.get_detections(frame)
        tracks = self.tracker.update_tracks(detections, frame=frame)

        # Handle each player
        for track in tracks:
            if not track.is_confirmed():
                continue
            track_id = track.track_id
            x1, y1, w, h = map(int, track.to_tlwh())  # Extract bbox
            area = w*h
            x2, y2 = x1 + w, y1 + h
            cx, cy = (x1 + x2) // 2, (y1 + y2) // 2  # Center point

            # Detect movement when Red Light is on
            if track_id in self.players_position:
                prev_cx, prev_cy, _ = self.players_position[track_id]
                if not self.players_status[track_id] or (self.red_light and (abs(cx - prev_cx) > 5 or abs(cy - prev_cy) > 5)):
                    label = f"Player {track_id} - ELIMINATED!"
                    self.players_status[track_id] = False
                    color = (0, 0, 255)
                else:
                    label = f"Player {track_id}"
                    color = (0, 255, 0)

                # Update stored position
                self.players_position[track_id] = (cx, cy, area)

                # Draw bounding box and label
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                cv2.putText(frame, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

            # Store first-time detected players
            elif self.frame_count < 5:
                self.players_position[track_id] = (cx, cy, area)
                self.players_status[track_id] = True

        # Display game state (Red/Green Light)
        light_text = "RED LIGHT - STOP!" if self.red_light else "GREEN LIGHT - GO!"
        light_color = (0, 0, 255) if self.red_light else (0, 255, 0)
        cv2.putText(frame, light_text, (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.2, light_color, 3)

        # Game end conditions
        canvas = self.check_lost()
        if not self.active:
            print("lost")
            return canvas
        elif win:
            print("won")
            return self.get_winner()
        return frame


def main():
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1000)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 800)
    mygame = Game()
    game_active = True
    is_win = False
    while cap.isOpened() and game_active:
        if cv2.waitKey(1) & 0xFF == ord(" "):
            is_win = True
        ret, frame = cap.read()
        if not ret:
            break
        new_frame = mygame.update_values(frame, is_win)
        cv2.imshow("red light green light", new_frame)

if __name__ == "__main__":
    main()