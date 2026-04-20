#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import http.client
import json
import mimetypes
import os
import subprocess
import time
import uuid

IMG = "/userdata/ums_shared.img"
MNT = "/mnt/ums"

STATE_DIR = "/userdata/usb_sender_state"
SEEN_DB = os.path.join(STATE_DIR, "seen.db")
LAST_MTIME = os.path.join(STATE_DIR, "last_mtime")
LOG_FILE = os.path.join(STATE_DIR, "usb_sender.log")

BUSY_FLAG = "/tmp/ums_busy"

UDC = "/sys/kernel/config/usb_gadget/rockchip/UDC"
REBUILD = "/root/rebuild_hid_msc.sh"

UPLOAD_HOST = "8.148.73.190"
UPLOAD_PORT = 5000
UPLOAD_PATH = "/upload"
UPLOAD_TARGET_PATH = "/from_board"
UPLOAD_SERIAL = "RK3568BOARD"
UPLOAD_APP_KEY = ""
UPLOAD_APP_SECRET = ""


def log(msg: str) -> None:
    os.makedirs(STATE_DIR, exist_ok=True)
    line = f"{time.strftime('%F %T')} {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def image_mtime():
    try:
        return str(int(os.stat(IMG).st_mtime))
    except Exception:
        return ""


def read_last_mtime():
    try:
        with open(LAST_MTIME, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return ""


def write_last_mtime(v: str):
    with open(LAST_MTIME, "w", encoding="utf-8") as f:
        f.write(v)


def wait_image_stable():
    first = image_mtime()
    if not first:
        return "", False
    time.sleep(3)
    second = image_mtime()
    if not second:
        return "", False
    return second, first == second


def mount_image_ro():
    os.makedirs(MNT, exist_ok=True)

    with open("/proc/mounts", "r", encoding="utf-8", errors="ignore") as f:
        mounts = f.read()
    if f" {MNT} " in mounts:
        return True

    result = subprocess.run(
        ["mount", "-o", "loop,ro", IMG, MNT],
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        log(f"[ums] mount failed: {result.stderr.strip()}")
        return False
    return True


def umount_image():
    with open("/proc/mounts", "r", encoding="utf-8", errors="ignore") as f:
        mounts = f.read()
    if f" {MNT} " in mounts:
        subprocess.run(["umount", MNT], capture_output=True, text=True)


def detach_udc():
    try:
        with open(UDC, "w", encoding="utf-8") as f:
            f.write("")
    except Exception as e:
        log(f"[ums] detach UDC failed: {e}")


def upload_file(file_path, target_path, serial):
    if not os.path.isfile(file_path):
        log(f"[upload] file not found: {file_path}")
        return False

    boundary = "----WebKitFormBoundary" + uuid.uuid4().hex
    filename = os.path.basename(file_path)

    with open(file_path, "rb") as f:
        file_data = f.read()

    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

    parts = []
    parts.append(f"--{boundary}\r\n".encode())
    parts.append(f'Content-Disposition: form-data; name="target_path"\r\n\r\n{target_path}\r\n'.encode())
    parts.append(f"--{boundary}\r\n".encode())
    parts.append(f'Content-Disposition: form-data; name="serial"\r\n\r\n{serial}\r\n'.encode())
    parts.append(f"--{boundary}\r\n".encode())
    parts.append(f'Content-Disposition: form-data; name="target_file"; filename="{filename}"\r\n'.encode())
    parts.append(f"Content-Type: {content_type}\r\n\r\n".encode())
    parts.append(file_data)
    parts.append(b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())

    body = b"".join(parts)
    headers = {
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Content-Length": str(len(body)),
    }

    if UPLOAD_APP_KEY:
        headers["app_key"] = UPLOAD_APP_KEY
    if UPLOAD_APP_SECRET:
        headers["app_secret"] = UPLOAD_APP_SECRET

    try:
        conn = http.client.HTTPConnection(UPLOAD_HOST, UPLOAD_PORT, timeout=30)
        conn.request("POST", UPLOAD_PATH, body=body, headers=headers)
        resp = conn.getresponse()
        data = resp.read().decode(errors="ignore")
        conn.close()

        log(f"[upload] status={resp.status} file={filename}")

        if resp.status != 200:
            return False

        try:
            obj = json.loads(data)
            return obj.get("error_code") == 0
        except Exception:
            return False
    except Exception as e:
        log(f"[upload] exception: {e}")
        return False


def read_seen():
    if not os.path.exists(SEEN_DB):
        return set()
    with open(SEEN_DB, "r", encoding="utf-8", errors="ignore") as f:
        return {line.strip() for line in f if line.strip()}


def append_seen(sig):
    with open(SEEN_DB, "a", encoding="utf-8") as f:
        f.write(sig + "\n")


def iter_files(root):
    for base, _, files in os.walk(root):
        for name in files:
            yield os.path.join(base, name)


def file_sig(path):
    st = os.stat(path)
    rel = os.path.relpath(path, MNT)
    return f"{rel}|{st.st_size}|{int(st.st_mtime)}"


def rebuild_full_stack():
    log("[ums] rebuild full HID+MSC stack")
    result = subprocess.run(
        [REBUILD],
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        log(f"[ums] rebuild failed: {result.stderr.strip()}")
        return False
    return True


def process_image_safely(old_mtime, stable_mtime):
    write_last_mtime(stable_mtime)
    log(f"[ums] record img mtime={stable_mtime}")

    os.makedirs(STATE_DIR, exist_ok=True)
    open(SEEN_DB, "a").close()

    success_all = True
    open(BUSY_FLAG, "w").close()

    try:
        log("[ums] detach UDC")
        detach_udc()
        time.sleep(1)

        log("[ums] mount image ro")
        if not mount_image_ro():
            return False

        try:
            seen = read_seen()
            found_new = False

            for path in iter_files(MNT):
                sig = file_sig(path)
                rel = os.path.relpath(path, MNT)

                if sig in seen:
                    log(f"[ums] skip old: {rel}")
                    continue

                found_new = True
                log(f"[ums] new file: {rel}")

                ok = upload_file(path, UPLOAD_TARGET_PATH, UPLOAD_SERIAL)
                if ok:
                    append_seen(sig)
                    log(f"[ums] uploaded: {rel}")
                else:
                    success_all = False
                    log(f"[ums] upload failed: {rel}")

            if not found_new:
                log("[ums] no new files")
        finally:
            log("[ums] umount image")
            umount_image()
    finally:
        try:
            os.remove(BUSY_FLAG)
        except FileNotFoundError:
            pass

    # 关键点：这里不再简单 rebind，而是完整重建
    if not rebuild_full_stack():
        success_all = False

    if not success_all:
        write_last_mtime(old_mtime)
        log("[ums] rollback last_mtime for retry")

    return success_all


def main():
    os.makedirs(STATE_DIR, exist_ok=True)
    open(SEEN_DB, "a").close()

    while True:
        cur = image_mtime()
        old = read_last_mtime()

        # 首次建立基线，不处理历史文件
        if cur and not old:
            write_last_mtime(cur)
            log(f"[ums] init baseline mtime={cur}")
            time.sleep(5)
            continue

        if not cur or cur == old:
            time.sleep(5)
            continue

        log(f"[ums] mtime changed old={old} new={cur}")

        stable_mtime, stable = wait_image_stable()
        if not stable:
            log("[ums] host still writing, back to loop")
            time.sleep(5)
            continue

        log(f"[ums] stable mtime={stable_mtime}, host write done")
        process_image_safely(old, stable_mtime)
        time.sleep(5)


if __name__ == "__main__":
    main()