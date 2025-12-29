#!/usr/bin/env python3
from flask import Flask, send_from_directory, render_template_string, abort, redirect, url_for, request
from pathlib import Path
from datetime import datetime
import threading
import time
import os
import cv2

from gpiozero import Button
#from picamera2 import Picamera2

PHOTO_DIR = Path("/home/pichess/picam/pics")
PORT = 8080
REFRESH_SECONDS = 2
PNG_COMPRESSION = 3   # 0 = largest/fastest, 9 = smallest/slowest
BUTTON_GPIO = 17
JPEG_QUALITY = 95
SIZE = (3280, 2464)                 # v2 full-res; change to (1640, 1232) if desired
LOCK_EXPOSURE_AFTER_WARMUP = True   # set False if lighting changes a lot

gpio_button = None
app = Flask(__name__)

# --- Camera setup (single global instance) ---
#picam2 = Picamera2()

CAMERA_INDEX = 0
logicam = None
cam_lock = threading.Lock()

def init_camera():
    PHOTO_DIR.mkdir(parents=True, exist_ok=True)

    #picam setup
    """
    config = picam2.create_still_configuration(
        main={"size": SIZE},
        buffer_count=4
    )
    picam2.configure(config)
    picam2.start()
    time.sleep(1.0)  # warmup for AE/AWB

    if LOCK_EXPOSURE_AFTER_WARMUP:
        picam2.set_controls({"AeEnable": False, "AwbEnable": False})
    """

    #logitech setup
    global logicam
    logicam = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_V4L2)
    logicam.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
    logicam.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
    logicam.set(cv2.CAP_PROP_FPS, 30)

    if not logicam.isOpened():
        raise RuntimeError("Could not open USB camera")  

def take_photo():
    return take_photo_png_logi()

def take_photo_png_logi():
    with cam_lock:
        ret, frame = logicam.read()
        if not ret:
            raise RuntimeError("Failed to capture frame from webcam")

        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        fn = PHOTO_DIR / f"{ts}.png"

        cv2.imwrite(
            str(fn),
            frame,
            [cv2.IMWRITE_PNG_COMPRESSION, PNG_COMPRESSION]
        )

        return fn

def take_photo_jpg() -> Path:
    """Capture one JPEG while keeping camera running. Thread-safe."""
    with cam_lock:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        fn = PHOTO_DIR / f"{ts}.jpg"
        picam2.options["quality"] = JPEG_QUALITY
        picam2.capture_file(str(fn))
        return fn

def take_photo_png():
    with cam_lock:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        fn = PHOTO_DIR / f"{ts}.png"

        # Capture raw RGB frame
        frame = picam2.capture_array()

        # Convert RGB -> BGR for OpenCV
        frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

        # Write PNG (lossless)
        cv2.imwrite(
            str(fn),
            frame_bgr,
            [cv2.IMWRITE_PNG_COMPRESSION, PNG_COMPRESSION]
        )

        return fn

def init_gpio_button():
    global gpio_button
    gpio_button = Button(BUTTON_GPIO, pull_up=True, bounce_time=0.10)

    def on_press():
        print("GPIO button pressed")
        threading.Thread(target=lambda: print("Captured:", take_photo()), daemon=True).start()

    gpio_button.when_pressed = on_press

# --- Web pages ---
GALLERY_PAGE = """
<!doctype html>
<html>
<head>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Pi Photos</title>
  <style>
    body { font-family: sans-serif; margin: 16px; }
    .top { display:flex; gap:12px; align-items:center; flex-wrap:wrap; }
    .btn { padding:10px 14px; border:1px solid #ccc; border-radius:12px; background:#f7f7f7; cursor:pointer; }
    .grid { margin-top:14px; display:grid; grid-template-columns:repeat(auto-fill, minmax(220px, 1fr)); gap:10px; }
    img { width:100%; height:auto; border-radius:12px; }
    a { text-decoration:none; color:inherit; }
    form { margin:0; }
  .card { position: relative; }
  .del {
    width: 100%;
    margin-top: 6px;
    padding: 8px 12px;
    border: 1px solid #e0b4b4;
    border-radius: 10px;
    background: #fff5f5;
    cursor: pointer;
  }
  </style>

  <script>
  let lastTs = 0;

  async function checkForUpdate() {
    try {
      const r = await fetch("/latest_ts");
      const ts = await r.text();
      if (ts !== lastTs) {
        if (lastTs !== 0) location.reload();
        lastTs = ts;
      }
    } catch (e) {}
  }

  setInterval(checkForUpdate, 2000);
  </script>
</head>
<body>
  <div class="top">
    <h2 style="margin:0;">Pi Photos</h2>

    <form method="POST" action="/capture">
      <button class="btn" type="submit">Take Photo</button>
    </form>

    <a class="btn" href="/live">Live view</a>
    <a class="btn" href="/latest">Open latest</a>
    <button class="btn" onclick="location.reload()">Refresh</button>
  </div>
  <div class="grid">
  {% for f in files %}
    <div class="card">
      <a href="/photos/{{ f }}"><img src="/photos/{{ f }}" loading="lazy"></a>

      <form method="POST" action="/delete/{{ f }}" onsubmit="return confirm('Delete this photo?');">
        <button class="del" type="submit">Delete</button>
      </form>
    </div>
  {% endfor %}
  </div>
</body>
</html>
"""

LIVE_PAGE = """
<!doctype html>
<html>
<head>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Latest Photo</title>
  <meta http-equiv="refresh" content="{{ refresh }}">
  <style>
    body { font-family: sans-serif; margin: 12px; text-align: center; }
    img { max-width: 100%; height: auto; border-radius: 12px; }
    .bar { display:flex; justify-content:space-between; align-items:center; margin-bottom:10px; gap:8px; flex-wrap:wrap; }
    .btn { padding:10px 14px; border:1px solid #ccc; border-radius:12px; background:#f7f7f7; cursor:pointer; }
    form { margin:0; }
  </style>
</head>
<body>
  <div class="bar">
    <a class="btn" href="/">Gallery</a>

    <form method="POST" action="/capture">
      <button class="btn" type="submit">Take Photo</button>
    </form>

    <div>Auto refresh: {{ refresh }}s</div>
    <a class="btn" href="/latest">Open file</a>
  </div>

  {% if filename %}
    <img src="/photos/{{ filename }}?t={{ ts }}">
  {% else %}
    <p>No photos yet.</p>
  {% endif %}
</body>
</html>
"""

@app.route("/")
def index():
    files = sorted(PHOTO_DIR.glob("*.[pj][np]g"), key=lambda p: p.stat().st_mtime, reverse=True)
    return render_template_string(GALLERY_PAGE, files=[p.name for p in files])

@app.route("/live")
def live():
    files = sorted(PHOTO_DIR.glob("*.[pj][np]g"), key=lambda p: p.stat().st_mtime, reverse=True)
    if files:
        p = files[0]
        return render_template_string(LIVE_PAGE, filename=p.name, ts=p.stat().st_mtime, refresh=REFRESH_SECONDS)
    return render_template_string(LIVE_PAGE, filename=None, ts=0, refresh=REFRESH_SECONDS)

@app.route("/latest")
def latest():
    files = sorted(PHOTO_DIR.glob("*.[pj][np]g"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return "No photos yet.", 404
    return send_from_directory(PHOTO_DIR, files[0].name)

@app.route("/photos/<path:filename>")
def photos(filename):
    if ".." in filename or not filename.lower().endswith((".jpg", ".png")):
        abort(400)
    return send_from_directory(PHOTO_DIR, filename)

@app.route("/capture", methods=["POST"])
def capture_route():
    # Basic LAN-only UX guard: allow only POST (no GET)
    take_photo()
    # If the request came from /live, send them back there; else back to gallery
    ref = request.headers.get("Referer", "")
    return redirect(ref or url_for("index"))

@app.route("/delete/<path:filename>", methods=["POST"])
def delete_photo(filename):
    # basic safety checks
    if ".." in filename or not filename.lower().endswith((".jpg", ".png")):
        abort(400)

    target = PHOTO_DIR / filename
    try:
        # Resolve to prevent path tricks
        target_resolved = target.resolve()
        if PHOTO_DIR.resolve() not in target_resolved.parents:
            abort(400)

        if target.exists():
            target.unlink()
    except Exception as e:
        return f"Delete failed: {e}", 500

    # send user back where they came from
    ref = request.headers.get("Referer", "")
    return redirect(ref or url_for("index"))

@app.route("/latest_ts")
def latest_ts():
    files = list(PHOTO_DIR.glob("*.jpg")) + list(PHOTO_DIR.glob("*.png"))
    if not files:
        return "0"

    newest = max(files, key=lambda p: p.stat().st_mtime_ns)
    return str(newest.stat().st_mtime_ns)

if __name__ == "__main__":
    init_camera()
    init_gpio_button()
    app.run(host="0.0.0.0", port=PORT)


