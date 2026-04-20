#!/bin/sh
set -e

G=/sys/kernel/config/usb_gadget/rockchip
F=$G/functions
C=$G/configs/b.1
UDC=$G/UDC
UDC_DEV="fcc00000.dwc3"
IMG="/userdata/ums_shared.img"

echo "[0] quiet log"
dmesg -n 1

echo "[1] set usb mode"
printf 'usb_hid_en\nusb_ums_en\n' > /tmp/.usb_config

echo "[2] unbind usb"
echo "" > "$UDC" 2>/dev/null || true
sleep 1

echo "[3] umount local ums mount"
umount /mnt/ums 2>/dev/null || true
sleep 1

echo "[4] cleanup old config links"
rm -f "$C/f1" 2>/dev/null || true
rm -f "$C/f2" 2>/dev/null || true
rm -f "$C/f3" 2>/dev/null || true
sleep 1

echo "[5] ensure functions exist"
mkdir -p "$F/hid.usb0"
mkdir -p "$F/hid.usb1"
mkdir -p "$F/mass_storage.0"

echo "[6] clear old mass storage binding"
echo "" > "$F/mass_storage.0/lun.0/file" 2>/dev/null || true
sleep 1

echo "[7] ensure ums image exists"
if [ ! -f "$IMG" ]; then
    dd if=/dev/zero of="$IMG" bs=1M count=64
    mkfs.vfat "$IMG"
    sync
fi

echo "[8] setup keyboard hid.usb0"
echo 1 > "$F/hid.usb0/protocol"
echo 1 > "$F/hid.usb0/subclass"
echo 8 > "$F/hid.usb0/report_length"
printf '\x05\x01\x09\x06\xa1\x01\x05\x07\x19\xe0\x29\xe7\x15\x00\x25\x01\x75\x01\x95\x08\x81\x02\x95\x01\x75\x08\x81\x01\x95\x05\x75\x01\x05\x08\x19\x01\x29\x05\x91\x02\x95\x01\x75\x03\x91\x01\x95\x06\x75\x08\x15\x00\x25\x65\x05\x07\x19\x00\x29\x65\x81\x00\xc0' > "$F/hid.usb0/report_desc"

echo "[9] setup mouse hid.usb1"
echo 2 > "$F/hid.usb1/protocol"
echo 1 > "$F/hid.usb1/subclass"
echo 6 > "$F/hid.usb1/report_length"
printf '\x05\x01\x09\x02\xa1\x01\x09\x01\xa1\x00\x05\x09\x19\x01\x29\x03\x15\x00\x25\x01\x95\x03\x75\x01\x81\x02\x95\x01\x75\x05\x81\x01\x05\x01\x09\x30\x09\x31\x15\x00\x26\xff\x7f\x75\x10\x95\x02\x81\x02\x09\x38\x15\x81\x25\x7f\x75\x08\x95\x01\x81\x06\xc0\xc0' > "$F/hid.usb1/report_desc"

echo "[10] setup mass storage"
echo 0 > "$F/mass_storage.0/stall"
echo 1 > "$F/mass_storage.0/lun.0/removable"
echo 0 > "$F/mass_storage.0/lun.0/ro"
echo "$IMG" > "$F/mass_storage.0/lun.0/file"

echo "[11] relink config"
ln -s "$F/hid.usb0" "$C/f1"
ln -s "$F/hid.usb1" "$C/f2"
ln -s "$F/mass_storage.0" "$C/f3"

echo "[12] bind usb"
echo "$UDC_DEV" > "$UDC"
sleep 1

echo "[13] create device nodes"
mdev -s
sleep 1

echo "==== /sys/class/hidg ===="
ls -l /sys/class/hidg || true
echo "==== /dev/hidg* ===="
ls -l /dev/hidg* || true
echo "==== config ===="
ls -l "$C"
echo "==== ums file ===="
cat "$F/mass_storage.0/lun.0/file"