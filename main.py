import time
import re
import cv2
import numpy as np
import mss
import pytesseract
from plyer import notification

# Tesseract Path Setup
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

last_signal = None
pending_signal = None
signal_counter = 0

# Screen Capture Area (Top-Left region)
monitor = {
    "top": 0,
    "left": 0,
    "width": 1000,
    "height": 700
}

# Strict Regex Pattern
signal_pattern = r"\b(BUY|SELL)\b[\s:\-]*(\d+(?:\.\d+)?)"

print("==================================================")
print("   Starting Real-Time Trading Signal Detector     ")
print("   Press 'q' on the preview window to exit.       ")
print("==================================================\n")

with mss.MSS() as sct:
    while True:
        screenshot = sct.grab(monitor)
        frame = np.array(screenshot)
        frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

        # Image Preprocessing: Grayscale + Thresholding to crisp numbers
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        resized = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        _, thresh = cv2.threshold(resized, 150, 255, cv2.THRESH_BINARY)

        # Config: Whitelist restricts Tesseract to digits, letters, dots, and colons
        custom_config = r'--oem 3 --psm 6 -c tessedit_char_whitelist=BUYSELL0123456789.:- '
        extracted_text = pytesseract.image_to_string(thresh, config=custom_config)

        # Match Pattern
        matches = re.findall(signal_pattern, extracted_text, re.IGNORECASE)

        if matches:
            for signal_type, price in matches:
                signal_type = signal_type.upper()
                raw_signal = f"{signal_type}: {price}"

                # Noise Filter: Signal must be stable for at least 2 consecutive frames
                if raw_signal == pending_signal:
                    signal_counter += 1
                else:
                    pending_signal = raw_signal
                    signal_counter = 1

                # Confirm signal only if it stays stable and is different from last_signal
                if signal_counter >= 2 and pending_signal != last_signal:
                    print("--------------------------------------------------")
                    print(f"  [NEW SIGNAL DETECTED]: {pending_signal}")
                    print("--------------------------------------------------")

                    notification.notify(
                        title="Trading Signal Alert",
                        message=f"Signal: {pending_signal}",
                        app_name="Signal Detector",
                        timeout=4
                    )

                    last_signal = pending_signal

        # Preview Window
        cv2.imshow("Live Screen Capture (Press 'q' to Quit)", frame)

        time.sleep(0.3)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            print("\nExiting Signal Detector...")
            break

cv2.destroyAllWindows()