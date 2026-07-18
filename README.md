# 抖音批量视频下载器 (douyin_dl)

用抖音分享链接批量下载视频（普通视频 + 日常/Story 类型）。

## 安装

```
pip install -e .
playwright install chromium
```

## 用法

多条链接作位置参数：

```
python -m douyin_dl "https://v.douyin.com/abc/" "https://v.douyin.com/def/"
```

文本文件：

```
python -m douyin_dl -f links.txt -o ./downloads
```

标准输入：

```
cat links.txt | python -m douyin_dl
```

## GUI 使用

```bash
python -m douyin_dl.gui
# 或安装后
douyin-dl-gui
```

启动后：
1. 在链接输入区粘贴抖音分享链接（每行一条，支持 `#` 注释）
2. 点击「浏览...」选择输出目录
3. 选择画质（default / 720p / 1080p / 原画）
4. 点击「开始下载」，任务表格会实时显示每条链接的状态、进度与失败原因
5. 点击「取消」可中止后续下载（当前正在下载的文件会跑完）

首次或 Cookie 失效时会弹出 Playwright 可见浏览器扫码登录窗口。

> Linux 部分发行版需 `apt install python3-tk` 安装 Tkinter。

## 故障排查

### Cookie 失效
症状：下载报 HTTP 401/403，或解析返回空 detail。
解决：
- 删除 `~/.douyin_dl/cookies.json` 后重跑，会自动弹出浏览器要求重新扫码：
  ```bash
  rm ~/.douyin_dl/cookies.json
  python -m douyin_dl --reauth -f links.txt
  ```
- Cookie 默认 24 小时过期，可编辑 `Config.cookie_path` 指向其他位置。

### 风控 412
症状：分享页/移动端接口返回 412 或空响应。
解决：
- 增大 `Config.sleep_range`（默认 1-2 秒），改为 `(3.0, 5.0)` 降低请求频率。
- 避免短时间批量下载超过 50 条。
- 必要时切换网络/代理。

### CDN 403
症状：流式下载时返回 403。
解决：
- Downloader 已强制 `Referer: https://www.douyin.com/` 头；如果仍 403，说明视频链接已过期（CDN 链接通常 24h 有效）。
- 重新运行程序获取新的视频地址。
- 若频繁过期，缩短从分享到下载的间隔时间。
