项目简介

本项目基于 Linux USB Gadget 框架，在 RK3568 开发板上实现一个复合 USB 设备：

* 模拟键盘输入（HID）
* 模拟鼠标操作（HID，支持绝对坐标）
* 模拟 U 盘（Mass Storage）
* 通过 HTTP 接口远程控制设备输入
* 自动检测 U 盘文件变化并上传

系统架构

PC <——USB——> RK3568

        ├── HID Keyboard  (/dev/hidg0)
        ├── HID Mouse     (/dev/hidg1)
        └── U Disk        (ums_shared.img)

HTTP 控制 → http_hid_server.py → hid_runner_abs.py → HID
U盘写入 → usb_sender_safe.py → 上传服务器 → rebuild USB

检测镜像变化
   ↓
确认写入完成（mtime稳定）
   ↓
断开USB
   ↓
只读挂载镜像
   ↓
扫描新文件
   ↓
上传服务器
   ↓
卸载
   ↓
完整重建USB设备

避免 FAT 文件系统损坏

项目结构
.
├── rebuild_hid_msc.sh        # 复合设备重建脚本
├── hid_runner_abs.py         # HID 执行引擎
├── http_hid_server.py        # HTTP 控制服务
├── usb_sender_safe.py        # U盘监听与上传
├── test_single.json          # 测试脚本
└── init.d/
    └── S99hid_stack          # 启动脚本
```

 环境要求

* RK3568 开发板
* Linux Kernel（支持 configfs）
* 必须开启：
CONFIG_USB_CONFIGFS=y
CONFIG_USB_CONFIGFS_F_HID=y
CONFIG_USB_LIBCOMPOSITE=y

 使用方法

### 1️⃣ 初始化 USB 设备

/root/rebuild_hid_msc.sh


### 2️⃣ 启动服务

/etc/init.d/S99hid_stack start

 检查设备

ls -l /dev/hidg*
ls -l /sys/kernel/config/usb_gadget/rockchip/configs/b.1

应包含：
hid.usb0
hid.usb1
mass_storage.0

 HTTP 控制示例

 Windows PowerShell：

```powershell
Invoke-RestMethod `
  -Uri "http://板子IP:8000" `
  -Method Post `
  -ContentType "application/json" `
  -Body (Get-Content "test_single.json" -Raw)
```

---

## 📄 JSON 控制示例

```json
{
  "version": "1.0",
  "type": "hid_script",
  "meta": {
    "screen": { "width": 1920, "height": 1080 }
  },
  "events": [
    {"action":"mouse_move","x":300,"y":200},
    {"action":"mouse_click","button":"left"},
    {"action":"input_text","text":"hello"},
    {"action":"keypress","key":"ENTER"}
  ]
}
```

---

 注意事项

 USB 插拔问题

* 开机时建议已连接 USB
* 若变为 ADB，可执行：

/root/rebuild_hid_msc.sh

 U盘安全

* 不直接操作镜像文件
* 使用“只读挂载”方式读取数据
* 自动处理上传与恢复

 系统限制

当前系统 USB 管理由 `S50usbdevice` 控制：

* 热插拔可能切回 ADB
* 不会自动恢复 hid.usb1

 后续优化方向

* [ ] 修改 `S50usbdevice` 实现系统级支持
* [ ] 支持多 HID 设备扩展（键盘+鼠标+自定义）
* [ ] Web UI 控制界面
* [ ] MQTT / 远程控制集成
* [ ] 文件上传队列优化

总结

本项目实现了一个完整的：
无线输入 + U盘传输”一体化 USB 仿真系统

核心能力：

* 稳定 HID 控制
* 安全 U盘读写
* 网络远程控制
