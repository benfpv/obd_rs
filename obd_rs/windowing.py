import cv2


def center_window(window_name: str, width: int, height: int) -> None:
    """Best-effort centering for an OpenCV window on the primary display."""
    screen_w = 0
    screen_h = 0

    # Prefer Win32 metrics on Windows (current deployment target).
    try:
        import ctypes

        user32 = ctypes.windll.user32
        screen_w = int(user32.GetSystemMetrics(0))
        screen_h = int(user32.GetSystemMetrics(1))
    except Exception:
        pass

    # Fallback for non-Windows environments where tkinter is available.
    if screen_w <= 0 or screen_h <= 0:
        try:
            import tkinter as tk

            root = tk.Tk()
            root.withdraw()
            screen_w = int(root.winfo_screenwidth())
            screen_h = int(root.winfo_screenheight())
            root.destroy()
        except Exception:
            return

    x = max((screen_w - int(width)) // 2, 0)
    y = max((screen_h - int(height)) // 2, 0)
    try:
        cv2.moveWindow(window_name, x, y)
    except cv2.error:
        # Some backends may not support explicit window movement.
        return
