import cv2
from ultralytics import YOLO

print("Starting FighterID Vision Engine...")

# usamos el modelo que ya tienes en la carpeta principal
model = YOLO("../yolov8n-pose.pt")

cap = cv2.VideoCapture(0)

while True:

    ret, frame = cap.read()

    if not ret:
        break

    results = model(frame, imgsz=416, conf=0.45)

    try:
        display = results[0].plot()
    except:
        display = frame

    cv2.imshow("FighterID Vision Engine", display)

    if cv2.waitKey(1) == 27:  # tecla ESC
        break

cap.release()
cv2.destroyAllWindows()