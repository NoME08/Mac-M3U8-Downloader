#!/usr/bin/env python3
import ctypes
import errno
import fcntl
import json
import os
import pty
import re
import secrets
import shutil
import signal
import struct
import subprocess
import tempfile
import termios
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, quote, urljoin, urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
DOWNLOADER = ROOT / "N_m3u8DL-RE"
DEFAULT_PORT = 8765
ANSI = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|[=>])")
SEGMENTS = re.compile(r"\b([\d,]+)/(\d[\d,]*)\s+(\d+(?:\.\d+)?)%")
CHINESE = r"(?i)^(zh([-_].*)?|zho|chi|cmn|yue|Chinese|Mandarin)$"
CHINESE_NAME = r"(?i)中文|中字|简体|繁體|繁体|簡體|Chinese|Mandarin|Cantonese"
ASSETS = {
    "nome77-theme.js": "text/javascript; charset=utf-8",
    "nome77-tokens.css": "text/css; charset=utf-8",
    "nome77-icon.svg": "image/svg+xml",
    "nome77-logo-light.svg": "image/svg+xml",
    "nome77-favicon.svg": "image/svg+xml",
}


class Downloads:
    def __init__(self):
        self.lock = threading.Lock()
        self.job = None
        self.worker = None

    def snapshot(self):
        with self.lock:
            if self.job is None:
                return None
            return {**self.job, "log": list(self.job["log"])}

    def update(self, **values):
        with self.lock:
            self.job.update(values)

    def log(self, line):
        line = ANSI.sub("", line).strip()
        if not line:
            return
        with self.lock:
            progress = SEGMENTS.search(line)
            if progress:
                self.job["progress"] = float(progress[3])
                self.job["segments"] = f"{progress[1]} / {progress[2]}"
                line = line[:progress.start()].strip()
            if re.search(r"binary merging|ffmpeg merging|muxing", line, re.I):
                self.job["phase"] = "正在合并并封装 MP4"
            if line and "━" not in line:
                self.job["log"].append(line[:600])

    def start(self, url, number, directory, filename, subtitle):
        ffmpeg = shutil.which("ffmpeg")
        ffprobe = shutil.which("ffprobe")
        if not ffmpeg or not ffprobe:
            raise ValueError("找不到 FFmpeg 或 ffprobe。")
        if not os.access(DOWNLOADER, os.X_OK):
            raise ValueError("找不到可执行的 N_m3u8DL-RE。")
        with self.lock:
            if self.job and self.job["state"] == "running":
                raise ValueError("请等当前下载完成。")
            self.job = {
                "state": "running", "phase": "正在读取播放列表", "progress": None,
                "segments": "", "number": number, "directory": str(directory),
                "file": None, "error": None, "log": deque(maxlen=60), "filename": filename,
            }
            self.worker = threading.Thread(
                target=self.run, args=(url, number, directory, filename, subtitle, ffmpeg, ffprobe),
                daemon=True,
            )
            self.worker.start()

    def run(self, url, number, directory, filename, subtitle, ffmpeg, ffprobe):
        staging = None
        try:
            try:
                staging = Path(tempfile.mkdtemp(prefix=f".m3u8-{number}-", dir=directory))
            except PermissionError as error:
                raise ValueError(
                    f"无法写入 {directory}。请检查启动脚本的终端是否拥有该文件夹的访问权限，"
                    "或选择其他保存位置。"
                ) from error
            tracks = staging / "media"
            tracks.mkdir()
            log_path = staging / "download.log"
            # Binary merge joins segments sequentially; FFmpeg then reads the joined tracks.
            command = [
                str(DOWNLOADER), url, "-H", f"Refer: https://www1.ikanbot.com/play/{number}",
                "-sv", "best", "-sa", "best", "--save-dir", str(tracks),
                "--tmp-dir", str(staging / "segments"), "--save-name", number,
                "--ffmpeg-binary-path", ffmpeg, "--binary-merge", "-M", "format=mp4:keep=true",
                "--del-after-done", "false", "--write-meta-json", "false", "--no-log",
                "--disable-update-check",
            ]
            command += ["-ss", f"lang={CHINESE}|{CHINESE_NAME[4:]}:for=all"]
            self.run_downloader(command, staging, log_path)
            self.update(phase="正在检查 MP4")
            # The downloader can print Done and exit zero after an FFmpeg failure.
            movie = tracks / f"{number}.mp4"
            if not movie.is_file():
                raise ValueError("下载器没有生成最终 MP4，请查看日志。")
            probe = subprocess.run(
                [ffprobe, "-v", "error",
                 "-show_entries", "stream=index,codec_type:stream_tags=language,title:format=duration",
                 "-of", "json", str(movie)],
                capture_output=True, text=True, check=True, timeout=30,
            )
            media = json.loads(probe.stdout)
            if not any(stream["codec_type"] == "video" for stream in media.get("streams", [])):
                raise ValueError("生成的 MP4 缺少视频轨道。")
            if not float(media.get("format", {}).get("duration", 0)) > 0:
                raise ValueError("生成的 MP4 时长无效。")
            streams = media.get("streams", [])
            subtitles = [stream for stream in streams if stream["codec_type"] == "subtitle"]
            selected = [stream for stream in subtitles if is_chinese(stream)]
            if subtitle or selected != subtitles:
                filtered = tracks / "filtered.mp4"
                inputs = ["-i", str(movie)]
                mapping = ["-map", "0:v", "-map", "0:a?"]
                if subtitle:
                    inputs += ["-i", str(subtitle)]
                    mapping += ["-map", "1:0", "-metadata:s:s:0", "language=zho",
                                "-disposition:s:0", "default"]
                else:
                    for stream in selected:
                        mapping += ["-map", f"0:{stream['index']}"]
                subprocess.run(
                    [ffmpeg, "-nostdin", "-v", "error", *inputs, *mapping, "-c", "copy",
                     "-c:s", "mov_text", "-movflags", "+faststart", str(filtered)],
                    capture_output=True, text=True, check=True,
                )
                movie = filtered
            if not (subtitle or selected):
                self.log("片源未提供可单独选择的中文字幕。画面自带的字幕会保留。")
            index = 1
            while True:
                name = filename if index == 1 else f"{filename} ({index})"
                output = directory / f"{name}.mp4"
                try:
                    os.link(movie, output)
                    break
                except FileExistsError:
                    index += 1
                except OSError as error:
                    if error.errno not in (errno.ENOTSUP, errno.EPERM):
                        raise
                    # Some external disks (for example exFAT) do not support hard links.
                    if output.exists() or output.is_symlink():
                        index += 1
                        continue
                    if not rename_exclusive(movie, output):
                        index += 1
                        continue
                    break
            shutil.rmtree(staging, ignore_errors=True)
            self.update(state="complete", phase="下载完成", progress=100, file=str(output))
        except subprocess.CalledProcessError as error:
            self.fail(error.stderr.strip() or "无法读取生成的 MP4。", staging)
        except (OSError, ValueError, subprocess.TimeoutExpired) as error:
            self.fail(str(error), staging)

    def run_downloader(self, command, staging, log_path):
        # Spectre's live progress needs a terminal with actual rows and columns.
        master, slave = pty.openpty()
        try:
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 32, 120, 0, 0))
            with os.fdopen(master, encoding="utf-8", errors="replace", closefd=False) as output, \
                    log_path.open("w", encoding="utf-8") as log, subprocess.Popen(
                        command, cwd=staging, stdin=slave, stdout=slave, stderr=slave,
                        env={**os.environ, "TERM": "xterm-256color"},
                    ) as process:
                os.close(slave)
                slave = None
                try:
                    for line in output:
                        log.write(ANSI.sub("", line))
                        self.log(line)
                        if "Start downloading" in line:
                            with self.lock:
                                if self.job["phase"] == "正在读取播放列表":
                                    self.job["phase"] = "正在下载分片"
                except OSError as error:
                    if error.errno != errno.EIO:
                        raise
                if process.wait():
                    raise ValueError(f"下载器退出，错误代码 {process.returncode}。")
        finally:
            os.close(master)
            if slave is not None:
                os.close(slave)

    def fail(self, message, staging):
        if staging:
            self.log(f"任务文件目录：{staging}")
        self.update(state="error", phase="下载失败", error=message)


downloads = Downloads()


def is_chinese(stream):
    tags = stream.get("tags", {})
    language = tags.get("language", "").strip()
    return bool(re.fullmatch(CHINESE, language) or (
        language in ("", "und") and re.search(CHINESE_NAME, tags.get("title", ""))
    ))


def rename_exclusive(source, destination):
    rename = ctypes.CDLL(None, use_errno=True).renamex_np
    rename.argtypes = (ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint)
    if rename(os.fsencode(source), os.fsencode(destination), 4) == 0:  # RENAME_EXCL
        return True
    error = ctypes.get_errno()
    if error == errno.EEXIST:
        return False
    raise OSError(error, os.strerror(error), str(destination))


def choose_folder(default, file=False):
    path = Path(default).expanduser() if default else ROOT
    if not path.is_dir():
        path = ROOT
    action = 'choose file with prompt "选择中文字幕文件"' if file else (
        'choose folder with prompt "选择视频保存位置"'
    )
    script = f"""
on run argv
    set startFolder to (POSIX file (item 1 of argv)) as alias
    activate
    return POSIX path of ({action} default location startFolder)
end run
"""
    response = subprocess.run(
        ["/usr/bin/osascript", "-e", script, str(path)], capture_output=True,
        text=True, timeout=120,
    )
    if response.returncode:
        if "(-128)" in response.stderr:
            return None
        raise ValueError("macOS 选择器无法打开，请手动填入路径。")
    return response.stdout.rstrip("\n")


class PlayPage(HTMLParser):
    def __init__(self, url):
        super().__init__()
        self.url = url
        self.title = ""
        self.caption = ""
        self.capture = None
        self.line = ""
        self.sources = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get("id") == "video_title":
            self.capture = "title"
        elif tag == "li" and "line-name" in attrs.get("class", "").split():
            self.capture = "line"
            self.line = ""
        elif attrs.get("name") == "lineData":
            url = urljoin(self.url, attrs.get("udata", ""))
            parts = urlsplit(url)
            if parts.scheme in ("http", "https") and parts.path.lower().endswith(".m3u8"):
                self.capture = "source"
                self.caption = ""
                self.sources.append({"url": url, "line": self.line.strip(), "label": ""})

    def handle_data(self, data):
        if self.capture == "title":
            self.title += data
        elif self.capture == "line":
            self.line += data
        elif self.capture == "source":
            self.caption += data
            self.sources[-1]["label"] = self.caption.strip()

    def handle_endtag(self, tag):
        if tag in ("h1", "li", "div"):
            self.capture = None


def resolve_play_page(value):
    parts = urlsplit(value)
    number = value if re.fullmatch(r"[0-9]{1,32}", value) else None
    if parts.scheme in ("http", "https") and re.fullmatch(
        r"(?:www[0-9]*\.)?ikanbot\.com", parts.hostname or ""
    ):
        match = re.match(r"^/play/([0-9]{1,32})(?:[/.]|$)", parts.path)
        if match:
            number = match[1]
    if not number:
        raise ValueError("请输入 ikanbot 播放页链接或纯数字编号。")
    url = f"https://www1.ikanbot.com/play/{number}"
    try:
        request = Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "text/html"})
        with urlopen(request, timeout=7) as response:
            html = response.read(2 * 1024 * 1024).decode("utf-8", "replace")
        page = PlayPage(url)
        page.feed(html)
        if page.sources:
            return {"number": number, "title": page.title.strip(), "sources": page.sources}
    except (OSError, ValueError):
        pass
    return {"number": number, "page": url, "sources": []}


def validated_download(data):
    url = str(data.get("url", "")).strip()
    number = str(data.get("number", "")).strip()
    directory = str(data.get("directory", "")).strip()
    parts = urlsplit(url)
    if (parts.scheme not in ("https", "http") or not parts.hostname
            or any(char.isspace() or ord(char) < 32 for char in url)):
        raise ValueError("请粘贴完整的 HTTP 或 HTTPS 播放列表链接。")
    if not re.fullmatch(r"[0-9]{1,32}", number):
        raise ValueError("请输入 1 至 32 位数字编号。")
    path = Path(directory).expanduser()
    if not path.is_absolute() or not path.is_dir():
        raise ValueError("请选择一个已存在的保存目录。")
    filename = re.sub(r"\.mp4$", "", str(data.get("filename", "")).strip(), flags=re.I).strip()
    filename = filename or number
    if (filename in (".", "..") or re.search(r"[/:\x00-\x1f\x7f]", filename)
            or len(os.fsencode(filename)) > 230):
        raise ValueError("文件名过长，或含有斜杠、冒号等不可用字符。")
    value = str(data.get("subtitle", "")).strip()
    subtitle = Path(value).expanduser() if value else None
    if subtitle and (not subtitle.is_absolute() or not subtitle.is_file()
                     or subtitle.suffix.lower() not in (".srt", ".vtt", ".ass", ".ssa")):
        raise ValueError("请选择本地 SRT、VTT、ASS 或 SSA 中文字幕文件。")
    return quote(url, safe=":/?&=@%+#[]!$'()*;,~-._"), number, path.resolve(), filename, subtitle


def browse_directory(default):
    path = Path(default).expanduser() if default else ROOT
    if not path.is_dir():
        path = ROOT
    path = path.resolve()
    inaccessible = False
    try:
        folders = sorted(
            ({"name": child.name, "path": str(child)} for child in path.iterdir()
             if not child.name.startswith(".") and child.is_dir()),
            key=lambda child: child["name"].casefold(),
        )
    except PermissionError:
        folders = []
        inaccessible = True
    home = Path.home()
    shortcuts = [{"name": name, "path": str(folder)} for name, folder in (
        ("个人文件夹", home), ("桌面", home / "Desktop"), ("下载", home / "Downloads"),
        ("影片", home / "Movies"), ("磁盘", Path("/Volumes")),
    ) if folder.is_dir()]
    return {"directory": str(path), "parent": str(path.parent),
            "shortcuts": shortcuts, "folders": folders, "inaccessible": inaccessible}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    @property
    def local_host(self):
        return f"127.0.0.1:{self.server.server_port}"

    def is_local_host(self):
        return self.headers.get("Host") in (
            self.local_host, f"localhost:{self.server.server_port}",
        )

    def reply(self, status, body, content_type="application/json; charset=utf-8"):
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlsplit(self.path)
        if not self.is_local_host():
            self.reply(403, {"error": "请使用启动器提供的本地地址。"})
        elif path.path == "/":
            self.server.page_opened()
            html = (ROOT / "index.html").read_bytes().replace(
                b"__M3U8_SESSION_TOKEN__", self.server.session_token.encode("ascii"),
            )
            self.reply(200, html, "text/html; charset=utf-8")
        elif path.path == "/api/status":
            tab = parse_qs(path.query).get("tab", [""])[0]
            if tab:
                self.server.activity(tab)
            self.reply(200, {"job": downloads.snapshot(), "directory": str(ROOT), "app": "nome77-m3u8"})
        elif path.path.startswith("/assets/") and path.path[8:] in ASSETS:
            name = path.path[8:]
            self.reply(200, (ROOT / "assets" / name).read_bytes(), ASSETS[name])
        else:
            self.reply(404, {"error": "页面不存在。"})

    def do_POST(self):
        if not self.is_local_host():
            self.reply(403, {"error": "请从本地下载页面操作。"})
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            if self.headers.get_content_type() != "application/json" or not 0 < length <= 16384:
                raise ValueError("请求格式无效。")
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError("请求格式无效。")
            token = str(data.get("sessionToken", "")).encode()
            if not (self.headers.get("Origin") == f"http://{self.headers.get('Host')}"
                    or secrets.compare_digest(token, self.server.session_token.encode("ascii"))):
                self.reply(403, {"error": "下载页面已失效，请重新打开下载器后再试。"})
                return
            if self.path == "/api/download":
                downloads.start(*validated_download(data))
                self.reply(202, {"ok": True})
            elif self.path == "/api/pick":
                directory = str(data.get("directory", ""))
                if data.get("native") or data.get("file"):
                    self.reply(200, {"selected": choose_folder(directory, bool(data.get("file")))})
                else:
                    self.reply(200, browse_directory(directory))
            elif self.path == "/api/resolve":
                self.reply(200, resolve_play_page(str(data.get("page", "")).strip()))
            elif self.path == "/api/leave":
                self.reply(200, {"ok": True})
                if data.get("close"):
                    self.server.stopping.set()
                else:
                    self.server.page_closed(str(data.get("tab", "")))
            elif self.path == "/api/reveal":
                job = downloads.snapshot()
                if not job or not job["file"] or not Path(job["file"]).is_file():
                    raise ValueError("找不到这个下载文件。")
                subprocess.run(["/usr/bin/open", "-R", job["file"]], check=True)
                self.reply(200, {"ok": True})
            else:
                self.reply(404, {"error": "操作不存在。"})
        except (ValueError, OSError, subprocess.SubprocessError) as error:
            self.reply(400, {"error": str(error)})


class LocalServer(ThreadingHTTPServer):
    timeout = 0.5

    def __init__(self, *args):
        self.stopping = threading.Event()
        self.session_token = secrets.token_urlsafe(32)
        self.lock = threading.Lock()
        self.tabs = {}
        self.grace_until = time.monotonic() + 35
        super().__init__(*args)

    def page_opened(self):
        with self.lock:
            self.grace_until = time.monotonic() + 10

    def activity(self, tab):
        if re.fullmatch(r"[a-f0-9-]{36}", tab):
            with self.lock:
                self.tabs[tab] = time.monotonic() + 150

    def page_closed(self, tab):
        with self.lock:
            if self.tabs.pop(tab, None) is not None:
                self.grace_until = time.monotonic() + 4

    def is_active(self):
        with self.lock:
            now = time.monotonic()
            self.tabs = {tab: expiry for tab, expiry in self.tabs.items() if expiry > now}
            return bool(self.tabs) or now < self.grace_until


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    try:
        server = LocalServer(("127.0.0.1", args.port), Handler)
    except OSError as error:
        if error.errno != errno.EADDRINUSE:
            raise
        url = f"http://127.0.0.1:{args.port}"
        if not args.no_browser:
            try:
                with urlopen(f"{url}/api/status", timeout=2) as response:
                    status = json.load(response)
                same_app = status.get("app") == "nome77-m3u8" and status.get("directory") == str(ROOT)
            except (ValueError, OSError, AttributeError):
                same_app = False
            if same_app:
                subprocess.run(["/usr/bin/open", url], check=True)
                return
        server = LocalServer(("127.0.0.1", 0), Handler)
        print(f"端口 {args.port} 已被占用，改用本机端口 {server.server_port}。", flush=True)
    def stop(*_):
        server.stopping.set()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGHUP, stop)
    signal.signal(signal.SIGINT, stop)
    with server:
        url = f"http://127.0.0.1:{server.server_port}"
        print(f"下载页面已启动：{url}（按 Control-C 关闭）", flush=True)
        if not args.no_browser:
            subprocess.run(["/usr/bin/open", url], check=True)
        while not server.stopping.is_set() and server.is_active():
            server.handle_request()
    if downloads.worker and downloads.worker.is_alive():
        print("页面已关闭，端口已释放。当前下载将在终端中继续。", flush=True)
        downloads.worker.join()
        job = downloads.snapshot()
        print(job.get("file") or job.get("error") or job["phase"], flush=True)


if __name__ == "__main__":
    main()
