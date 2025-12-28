# picam
Small python app for capturing and displaying images from the camera


# Raspberry Pi Button Camera + Web Gallery

A simple Raspberry Pi camera appliance using **Picamera2** that:

- Takes photos via a **physical GPIO button** or **web UI**
- Serves a **LAN-only web gallery**
- Provides a **live auto-refresh view**
- Allows deleting photos from the gallery
- Runs as a single **systemd service**

Tested on Raspberry Pi 3B/3B+ with Camera v2.

---

## Hardware

### Button Wiring (BCM numbering)

| Function | BCM GPIO | Physical Pin |
|--------|----------|--------------|
| Button | GPIO17   | Pin 11       |
| GND    | —        | Pin 6        |

```

GPIO17 (Pin 11) ──[ Button ]── GND (Pin 6)

````

No resistor required (internal pull-up enabled).

---

## System Dependencies

Picamera2 must be installed via apt (not pip):

```bash
sudo apt update
sudo apt install -y \
  python3-picamera2 \
  python3-libcamera \
  libcamera-apps \
  python3-venv
````

Optional (for PNG output):

```bash
sudo apt install -y python3-opencv
```

---

## Python Setup (pip + venv)

Create a venv **with system packages enabled**:

```bash
python3 -m venv venv --system-site-packages
source venv/bin/activate
pip install flask gpiozero opencv-python-headless
```

---

## Run Manually

```bash
source venv/bin/activate
python pi_cam_web.py
```

Open from another device on the LAN:

* Gallery: `http://<pi-ip>:8080/`
* Live view: `http://<pi-ip>:8080/live`

Photos are saved to:

```
/home/<user>/pics/
```

---

## systemd Service

Create `/etc/systemd/system/pi-cam-web.service`:

```ini
[Unit]
Description=Pi Camera + Web Gallery
After=network.target

[Service]
User=<user>
WorkingDirectory=/home/<user>/picam
ExecStart=/home/<user>/picam/venv/bin/python /home/<user>/picam/pi_cam_web.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable pi-cam-web
sudo systemctl start pi-cam-web
```

Logs:

```bash
journalctl -u pi-cam-web -f
```

---

## Notes

* Only **one process** may access the camera at a time
* Picamera2 must come from `apt`
* GPIO uses **BCM numbering**
* Keep the GPIO `Button` object global (not local to a function)

---

