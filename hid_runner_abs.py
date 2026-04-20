#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import os
import sys
import time

KBD_DEV = "/dev/hidg0"
MOUSE_DEV = "/dev/hidg1"
ABS_MAX = 32767

MOD_NONE = 0x00
MOD_LSHIFT = 0x02

SPECIAL_KEYS = {
    "ENTER": (MOD_NONE, 0x28),
    "ESC": (MOD_NONE, 0x29),
    "BACKSPACE": (MOD_NONE, 0x2A),
    "TAB": (MOD_NONE, 0x2B),
    "SPACE": (MOD_NONE, 0x2C),
    "RIGHT": (MOD_NONE, 0x4F),
    "LEFT": (MOD_NONE, 0x50),
    "DOWN": (MOD_NONE, 0x51),
    "UP": (MOD_NONE, 0x52),
}

BUTTON_MAP = {
    "left": 0x01,
    "right": 0x02,
    "middle": 0x04,
}


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def to_u8_signed(v):
    return v & 0xFF


def button_mask(button):
    if button not in BUTTON_MAP:
        raise ValueError(f"unsupported mouse button: {button}")
    return BUTTON_MAP[button]


def char_to_hid(ch):
    if len(ch) != 1:
        raise ValueError(f"invalid character: {ch}")

    if "a" <= ch <= "z":
        return MOD_NONE, 0x04 + (ord(ch) - ord("a"))
    if "A" <= ch <= "Z":
        return MOD_LSHIFT, 0x04 + (ord(ch) - ord("A"))
    if "1" <= ch <= "9":
        return MOD_NONE, 0x1E + (ord(ch) - ord("1"))
    if ch == "0":
        return MOD_NONE, 0x27

    simple = {
        " ": (MOD_NONE, 0x2C),
        "-": (MOD_NONE, 0x2D),
        "_": (MOD_LSHIFT, 0x2D),
        "=": (MOD_NONE, 0x2E),
        "+": (MOD_LSHIFT, 0x2E),
        "[": (MOD_NONE, 0x2F),
        "{": (MOD_LSHIFT, 0x2F),
        "]": (MOD_NONE, 0x30),
        "}": (MOD_LSHIFT, 0x30),
        "\\": (MOD_NONE, 0x31),
        "|": (MOD_LSHIFT, 0x31),
        ";": (MOD_NONE, 0x33),
        ":": (MOD_LSHIFT, 0x33),
        "'": (MOD_NONE, 0x34),
        "\"": (MOD_LSHIFT, 0x34),
        "`": (MOD_NONE, 0x35),
        "~": (MOD_LSHIFT, 0x35),
        ",": (MOD_NONE, 0x36),
        "<": (MOD_LSHIFT, 0x36),
        ".": (MOD_NONE, 0x37),
        ">": (MOD_LSHIFT, 0x37),
        "/": (MOD_NONE, 0x38),
        "?": (MOD_LSHIFT, 0x38),
        "!": (MOD_LSHIFT, 0x1E),
        "@": (MOD_LSHIFT, 0x1F),
        "#": (MOD_LSHIFT, 0x20),
        "$": (MOD_LSHIFT, 0x21),
        "%": (MOD_LSHIFT, 0x22),
        "^": (MOD_LSHIFT, 0x23),
        "&": (MOD_LSHIFT, 0x24),
        "*": (MOD_LSHIFT, 0x25),
        "(": (MOD_LSHIFT, 0x26),
        ")": (MOD_LSHIFT, 0x27),
        "\n": (MOD_NONE, 0x28),
        "\t": (MOD_NONE, 0x2B),
    }

    if ch in simple:
        return simple[ch]

    raise ValueError(f"unsupported character: {repr(ch)}")


class HidRunner:
    def __init__(self, kbd_dev, mouse_dev, screen_w, screen_h):
        self.kbd = open(kbd_dev, "wb", buffering=0)
        self.mouse = open(mouse_dev, "wb", buffering=0)
        self.screen_w = screen_w
        self.screen_h = screen_h
        self.cur_x = 0
        self.cur_y = 0
        self.mouse_buttons = 0

    def close(self):
        try:
            self.kbd.close()
        except Exception:
            pass
        try:
            self.mouse.close()
        except Exception:
            pass

    def _kbd_report(self, modifier, keycode):
        self.kbd.write(bytes([modifier, 0x00, keycode, 0, 0, 0, 0, 0]))

    def key_press_release(self, modifier, keycode, press_delay=0.03):
        self._kbd_report(modifier, keycode)
        time.sleep(press_delay)
        self._kbd_report(0x00, 0x00)
        time.sleep(press_delay)

    def keypress(self, key_name):
        key_name = key_name.upper()

        if key_name in SPECIAL_KEYS:
            mod, code = SPECIAL_KEYS[key_name]
            self.key_press_release(mod, code)
            return

        if len(key_name) == 1:
            mod, code = char_to_hid(key_name)
            self.key_press_release(mod, code)
            return

        raise ValueError(f"unsupported key: {key_name}")

    def input_text(self, text):
        for ch in text:
            mod, code = char_to_hid(ch)
            self.key_press_release(mod, code)

    def _scale_abs(self, px, py):
        px = clamp(px, 0, self.screen_w - 1)
        py = clamp(py, 0, self.screen_h - 1)
        hx = 0 if self.screen_w <= 1 else int(px * ABS_MAX / (self.screen_w - 1))
        hy = 0 if self.screen_h <= 1 else int(py * ABS_MAX / (self.screen_h - 1))
        return hx, hy

    def mouse_report_abs(self, buttons, px, py, wheel=0):
        hx, hy = self._scale_abs(px, py)
        report = bytes([
            buttons & 0xFF,
            hx & 0xFF,
            (hx >> 8) & 0xFF,
            hy & 0xFF,
            (hy >> 8) & 0xFF,
            to_u8_signed(wheel),
        ])
        self.mouse.write(report)

    def mouse_move_to(self, px, py):
        self.cur_x = px
        self.cur_y = py
        self.mouse_report_abs(self.mouse_buttons, self.cur_x, self.cur_y, 0)
        time.sleep(0.02)

    def mouse_click(self, button):
        mask = button_mask(button)
        self.mouse_report_abs(mask, self.cur_x, self.cur_y, 0)
        time.sleep(0.03)
        self.mouse_report_abs(0, self.cur_x, self.cur_y, 0)
        time.sleep(0.03)

    def mouse_down(self, button):
        self.mouse_buttons |= button_mask(button)
        self.mouse_report_abs(self.mouse_buttons, self.cur_x, self.cur_y, 0)
        time.sleep(0.02)

    def mouse_up(self, button):
        self.mouse_buttons &= ~button_mask(button)
        self.mouse_report_abs(self.mouse_buttons, self.cur_x, self.cur_y, 0)
        time.sleep(0.02)

    def scroll(self, value):
        step = 1 if value > 0 else -1
        for _ in range(abs(value)):
            self.mouse_report_abs(self.mouse_buttons, self.cur_x, self.cur_y, step)
            time.sleep(0.02)


def get_window_offset(meta):
    window = meta.get("window", {})
    return int(window.get("left", 0)), int(window.get("top", 0))


def get_screen_size(meta):
    screen = meta.get("screen", {})
    return int(screen.get("width", 1920)), int(screen.get("height", 1080))


def resolve_text(event, form):
    if "field" in event:
        field_name = event["field"]
        if field_name not in form:
            raise KeyError(f"field not found in form: {field_name}")
        return str(form[field_name])

    if "text" in event:
        return str(event["text"])

    raise ValueError("input_text requires 'field' or 'text'")


def run_script(script, runner):
    if script.get("version") != "1.0":
        raise ValueError(f"unsupported version: {script.get('version')}")
    if script.get("type") != "hid_script":
        raise ValueError(f"unsupported type: {script.get('type')}")

    meta = script.get("meta", {})
    form = script.get("form", {})
    events = script.get("events", [])

    default_coord_type = meta.get("coordTypeDefault", "window")
    window_left, window_top = get_window_offset(meta)

    for event in events:
        action = event.get("action")

        if action == "mouse_move":
            x = int(event["x"])
            y = int(event["y"])
            coord_type = event.get("coordType", default_coord_type)

            if coord_type == "window":
                target_x = window_left + x
                target_y = window_top + y
            elif coord_type == "screen":
                target_x = x
                target_y = y
            else:
                raise ValueError(f"unsupported coordType: {coord_type}")

            runner.mouse_move_to(target_x, target_y)

        elif action == "mouse_click":
            runner.mouse_click(event.get("button", "left"))

        elif action == "mouse_down":
            runner.mouse_down(event.get("button", "left"))

        elif action == "mouse_up":
            runner.mouse_up(event.get("button", "left"))

        elif action == "input_text":
            runner.input_text(resolve_text(event, form))

        elif action == "keypress":
            runner.keypress(event["key"])

        elif action == "delay":
            time.sleep(int(event["ms"]) / 1000.0)

        elif action == "scroll":
            runner.scroll(int(event["value"]))

        else:
            raise ValueError(f"unsupported action: {action}")


def main():
    parser = argparse.ArgumentParser(description="Run HID JSON script with keyboard + absolute mouse")
    parser.add_argument("json_file", help="path to json script")
    parser.add_argument("--kbd", default=KBD_DEV)
    parser.add_argument("--mouse", default=MOUSE_DEV)
    args = parser.parse_args()

    if os.geteuid() != 0:
        print("please run as root", file=sys.stderr)
        sys.exit(1)

    if not os.path.exists(args.kbd):
        print(f"keyboard device not found: {args.kbd}", file=sys.stderr)
        sys.exit(1)

    if not os.path.exists(args.mouse):
        print(f"mouse device not found: {args.mouse}", file=sys.stderr)
        sys.exit(1)

    with open(args.json_file, "r", encoding="utf-8") as f:
        script = json.load(f)

    screen_w, screen_h = get_screen_size(script.get("meta", {}))

    runner = HidRunner(args.kbd, args.mouse, screen_w, screen_h)
    try:
        run_script(script, runner)
    finally:
        runner.close()


if __name__ == "__main__":
    main()