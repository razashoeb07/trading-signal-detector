import time
import re
import cv2
import numpy as np
import mss
import pytesseract
import MetaTrader5 as mt5
from plyer import notification


# ============================================================
# Config Parameters
# ============================================================

TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
SYMBOL = "EURUSD"
LOT_SIZE = 0.01

pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH


# ============================================================
# 1. MT5 Initialization with Safety Check
# ============================================================

try:
    if not mt5.initialize():
        print(
            "\n[ERROR] MT5 Initialization failed. "
            "Check if MT5 terminal is open.\n"
        )

        mt5.shutdown()
        exit()

    print(
        "\n[INFO] Connected to MetaTrader 5 Successfully.\n"
    )

except Exception as e:
    print(
        f"\n[CRITICAL ERROR] Failed to initialize MT5: {e}\n"
    )
    exit()


# ============================================================
# Global Variables
# ============================================================

last_signal = None
pending_signal = None
signal_counter = 0


# ============================================================
# Screen Monitor Configuration
# ============================================================

monitor = {
    "top": 0,
    "left": 0,
    "width": 1000,
    "height": 700
}


# ============================================================
# OCR Signal Pattern
# ============================================================

signal_pattern = (
    r"(BUY|SELL)[\s:\-=]*"
    r"(\d+(?:\.\d+)?).*?"
    r"T[\s:\-=]*(\d+(?:\.\d+)?).*?"
    r"SL[\s:\-=]*(\d+(?:\.\d+)?)"
)


# ============================================================
# Get MT5 Filling Mode
# ============================================================

def get_filling_mode(symbol):

    try:
        symbol_info = mt5.symbol_info(symbol)

        if symbol_info is None:
            return mt5.ORDER_FILLING_FOK

        filling_modes = symbol_info.filling_mode

        if filling_modes & mt5.ORDER_FILLING_FOK:
            return mt5.ORDER_FILLING_FOK

        elif filling_modes & mt5.ORDER_FILLING_IOC:
            return mt5.ORDER_FILLING_IOC

        elif filling_modes & mt5.ORDER_FILLING_RETURN:
            return mt5.ORDER_FILLING_RETURN

        else:
            return mt5.ORDER_FILLING_FOK

    except Exception as e:

        print(
            f"\n[WARNING] Error detecting filling mode: "
            f"{e}. Defaulting to FOK.\n"
        )

        return mt5.ORDER_FILLING_FOK


# ============================================================
# Execute MT5 Order
# ============================================================

def execute_mt5_order(order_type, price, tp, sl):

    try:

        action_type = (
            mt5.ORDER_TYPE_BUY
            if order_type == "BUY"
            else mt5.ORDER_TYPE_SELL
        )

        tick = mt5.symbol_info_tick(SYMBOL)

        if tick is None:

            print(
                f"\n[ERROR] Failed to get market price tick "
                f"for {SYMBOL}\n"
            )

            return

        execution_price = (
            tick.ask
            if order_type == "BUY"
            else tick.bid
        )

        filling_mode = get_filling_mode(SYMBOL)

        parsed_sl = float(sl)
        parsed_tp = float(tp)

        # ----------------------------------------------------
        # Dynamic SL/TP Boundary Check
        # ----------------------------------------------------

        if order_type == "BUY":

            if (
                parsed_sl >= execution_price
                or parsed_tp <= execution_price
            ):

                print(
                    f"\n[WARNING] SL/TP out of range for BUY "
                    f"(Ask: {execution_price}). "
                    f"Adjusting dynamically.\n"
                )

                parsed_sl = round(
                    execution_price - 0.0030,
                    5
                )

                parsed_tp = round(
                    execution_price + 0.0030,
                    5
                )

        else:

            if (
                parsed_sl <= execution_price
                or parsed_tp >= execution_price
            ):

                print(
                    f"\n[WARNING] SL/TP out of range for SELL "
                    f"(Bid: {execution_price}). "
                    f"Adjusting dynamically.\n"
                )

                parsed_sl = round(
                    execution_price + 0.0030,
                    5
                )

                parsed_tp = round(
                    execution_price - 0.0030,
                    5
                )

        # ----------------------------------------------------
        # MT5 Order Request
        # ----------------------------------------------------

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": SYMBOL,
            "volume": LOT_SIZE,
            "type": action_type,
            "price": execution_price,
            "sl": parsed_sl,
            "tp": parsed_tp,
            "deviation": 20,
            "magic": 100100,
            "comment": "Python OCR Signal Auto-Trade",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": filling_mode,
        }

        # ----------------------------------------------------
        # Attempt 1
        # ----------------------------------------------------

        result = mt5.order_send(request)

        # ----------------------------------------------------
        # Fallback Attempt 2
        # Retry without filling_mode if rejected
        # ----------------------------------------------------

        if (
            result is None
            or result.retcode == 10030
            or result.retcode != mt5.TRADE_RETCODE_DONE
        ):

            if "type_filling" in request:
                del request["type_filling"]

            result = mt5.order_send(request)

        # ----------------------------------------------------
        # Final Result
        # ----------------------------------------------------

        if (
            result is None
            or result.retcode != mt5.TRADE_RETCODE_DONE
        ):

            comment = (
                result.comment
                if result
                else "No response from MT5 server"
            )

            code = (
                result.retcode
                if result
                else "N/A"
            )

            print(
                f"\n[FAILURE] Order Execution Failed: "
                f"{comment} (Code: {code})\n"
            )

        else:

            print(
                f"\n[SUCCESS] Trade Executed on MT5! "
                f"Order Ticket: {result.order}\n"
            )

    except Exception as e:

        print(
            f"\n[CRITICAL ERROR] Execution Exception: {e}\n"
        )


# ============================================================
# Start Real-Time Signal Scanner
# ============================================================

print(
    "\n[INFO] Starting Real-Time Signal Scanner "
    "& MT5 Auto-Executor.\n"
)


# ============================================================
# Screen Capture Loop
# ============================================================

with mss.MSS() as sct:

    while True:

        try:

            # ------------------------------------------------
            # 1. Capture Screen
            # ------------------------------------------------

            screenshot = sct.grab(monitor)

            frame = np.array(screenshot)

            frame = cv2.cvtColor(
                frame,
                cv2.COLOR_BGRA2BGR
            )

            # ------------------------------------------------
            # 2. Preprocessing
            # ------------------------------------------------

            gray = cv2.cvtColor(
                frame,
                cv2.COLOR_BGR2GRAY
            )

            resized = cv2.resize(
                gray,
                None,
                fx=2,
                fy=2,
                interpolation=cv2.INTER_CUBIC
            )

            _, thresh = cv2.threshold(
                resized,
                150,
                255,
                cv2.THRESH_BINARY
            )

            # ------------------------------------------------
            # 3. OCR Text Extraction
            # ------------------------------------------------

            custom_config = (
                r'--oem 3 --psm 6 '
                r'-c tessedit_char_whitelist='
                r'BUYSELLTSL0123456789.:-= '
            )

            extracted_text = pytesseract.image_to_string(
                thresh,
                config=custom_config
            )

            # ------------------------------------------------
            # 4. Pattern Matching
            # ------------------------------------------------

            matches = re.findall(
                signal_pattern,
                extracted_text,
                re.IGNORECASE
            )

            if matches:

                for (
                    signal_type,
                    entry_price,
                    tp_price,
                    sl_price
                ) in matches:

                    signal_type = signal_type.upper()

                    raw_signal = (
                        f"{signal_type} | "
                        f"Entry: {entry_price} | "
                        f"TP: {tp_price} | "
                        f"SL: {sl_price}"
                    )

                    # ----------------------------------------
                    # Signal Confirmation Counter
                    # ----------------------------------------

                    if raw_signal == pending_signal:
                        signal_counter += 1

                    else:
                        pending_signal = raw_signal
                        signal_counter = 1

                    # ----------------------------------------
                    # Execute Confirmed Signal
                    # ----------------------------------------

                    if (
                        signal_counter >= 2
                        and pending_signal != last_signal
                    ):

                        print(
                            f"\n[SIGNAL DETECTED] "
                            f"{pending_signal}\n"
                        )

                        # ------------------------------------
                        # Desktop Notification
                        # ------------------------------------

                        try:

                            notification.notify(
                                title="MT5 Auto-Trader Alert",
                                message=(
                                    f"Executing "
                                    f"{signal_type} @ "
                                    f"{entry_price}"
                                ),
                                app_name="Signal Executor",
                                timeout=3
                            )

                        except Exception as notif_err:

                            print(
                                "\n[WARNING] Desktop Notification "
                                f"failed: {notif_err}\n"
                            )

                        # ------------------------------------
                        # Execute MT5 Order
                        # ------------------------------------

                        execute_mt5_order(
                            signal_type,
                            entry_price,
                            tp_price,
                            sl_price
                        )

                        last_signal = pending_signal

            # ------------------------------------------------
            # Preview Window
            # ------------------------------------------------

            cv2.imshow(
                "Live Chart Scanner (Press 'q' to Quit)",
                frame
            )

        except Exception as loop_err:

            print(
                f"\n[WARNING] Main Loop Error (Recovered): "
                f"{loop_err}\n"
            )

        # ----------------------------------------------------
        # Loop Delay
        # ----------------------------------------------------

        time.sleep(0.3)

        # ----------------------------------------------------
        # Break Loop Gracefully on 'q'
        # ----------------------------------------------------

        try:

            if cv2.waitKey(1) & 0xFF == ord("q"):

                print(
                    "\n[INFO] Exiting Signal Detector...\n"
                )

                break

        except Exception:
            break


# ============================================================
# Cleanup
# ============================================================

cv2.destroyAllWindows()

try:
    mt5.shutdown()

    print(
        "\n[INFO] MetaTrader 5 connection closed.\n"
    )

except Exception:
    pass