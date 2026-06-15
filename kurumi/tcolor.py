import cv2
import numpy as np
import tkinter as tk
from tkinter import ttk

img = cv2.imread("./logs/20260614_194554/0009.jpg")

hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
# mask = cv2.inRange(hsv, (20, 100, 220), (35, 255, 255))
# result = cv2.bitwise_and(img, img, mask=mask)
# cv2.imwrite('hora.png', result)

root = tk.Tk()
root.title("HSV Tuner")
root.geometry("600x250+0+400")

params = {
    "H_min": (tk.IntVar(value=0),   180),
    "H_max": (tk.IntVar(value=180), 180),
    "S_min": (tk.IntVar(value=0),   255),
    "S_max": (tk.IntVar(value=255), 255),
    "V_min": (tk.IntVar(value=0),   255),
    "V_max": (tk.IntVar(value=255), 255),
}
_windows_positioned = False
def show(*_):
    global _windows_positioned
    vals = {k: v.get() for k, (v, _) in params.items()}
    lower = np.array([vals["H_min"], vals["S_min"], vals["V_min"]])
    upper = np.array([vals["H_max"], vals["S_max"], vals["V_max"]])
    mask = cv2.inRange(hsv, lower, upper)
    result = cv2.bitwise_and(img, img, mask=mask)
    cv2.imshow("Mask", mask)
    cv2.imshow("Result", result)
    cv2.imshow("Original", img)

    if not _windows_positioned:
        cv2.moveWindow("Original", 0, 0)
        cv2.moveWindow("Mask", 400, 0)
        cv2.moveWindow("Result", 800, 0)
        _windows_positioned = True
    print(f"\rlower={list(lower)} upper={list(upper)}", end="")

entries = {}
for name, (var, max_val) in params.items():
    frame = tk.Frame(root)
    frame.pack(fill="x", padx=10, pady=3)

    tk.Label(frame, text=name, width=8, anchor="w").pack(side="left")

    s = ttk.Scale(frame, from_=0, to=max_val, variable=var,
                  orient="horizontal", length=400, command=show)
    s.pack(side="left")

    e = tk.Entry(frame, textvariable=var, width=5)
    e.pack(side="left", padx=5)
    e.bind("<Return>", show)
    entries[name] = e

tk.Button(root, text="打印当前值", command=show).pack(pady=5)

show()
root.mainloop()
cv2.destroyAllWindows()