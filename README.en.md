# NØME M3U8 Downloader

[简体中文](README.md) · English

A local M3U8 downloader for Mac. Paste a link, choose a filename and destination, and save the downloaded stream as an MP4.

## Install and launch

1. Download `nome-m3u8-v1.0.0-macos-arm64.zip` from GitHub Releases and extract it with macOS Archive Utility. This package is for Apple silicon Macs. The launcher is locally signed and has not been notarized by Apple.
2. Install Python 3.9 or later and FFmpeg with `ffprobe`. If you use Homebrew, run `brew install python ffmpeg`.
3. Double-click **M3U8 下载器.app** in the extracted folder, or run `./start.sh` from that folder. Keep the launcher, scripts, assets, and download engine together.

The interface opens in your browser. The service listens only on `127.0.0.1` and picks an available port if the default is already in use. Click **关闭服务** (Stop service) to release the port. The service also stops after you close its last tab normally. Downloads already in progress continue.

## Download a video

- If you already have the M3U8 URL, expand **手动输入 M3U8 链接** (Enter an M3U8 link) and enter the link and playback page ID.
- For ikanbot, paste the playback page URL or enter its ID, then click **查找线路** (Find sources). If the site blocks direct lookup, drag the link under **一键从播放页导入** (Import from the playback page) to your bookmarks bar. Click that bookmark on the playback page to import the title and available sources.
- Choose a destination and set or edit the filename, then click **开始下载 MP4** (Download MP4). Duplicate names get a numeric suffix. The page shows progress, logs, and the saved file path.
- The downloader keeps separate subtitle tracks it recognizes as Chinese by default. You can also select a local Chinese subtitle file. Subtitles burned into the video stay in the picture. Download only content you have permission to save.

The interface is in Simplified Chinese and offers System, Dark, and Light themes.

## Run from source

Install the dependencies above. Download the build of [N_m3u8DL-RE v0.5.1-beta](https://github.com/nilaoda/N_m3u8DL-RE/releases/tag/v0.5.1-beta) that matches your Mac architecture, then extract the `N_m3u8DL-RE` executable into the project root. Run these commands from the project root.

```sh
chmod +x N_m3u8DL-RE start.sh
./start.sh
```

`downloader.py` runs the local service, `index.html` provides the browser interface, and `assets/` holds theme and brand files. The Finder launcher source and configuration are in `launcher.m` and `macos/Info.plist`. Use Xcode Command Line Tools to rebuild it.

```sh
app='M3U8 下载器.app'
mkdir -p "$app/Contents/MacOS"
cp macos/Info.plist "$app/Contents/Info.plist"
clang -fobjc-arc -framework Cocoa -arch arm64 -arch x86_64 \
  -mmacosx-version-min=11.0 launcher.m -o "$app/Contents/MacOS/launch"
codesign --force --sign - "$app"
```

## Third-party components

The macOS package includes the upstream [N_m3u8DL-RE](https://github.com/nilaoda/N_m3u8DL-RE) binary under its [MIT license](licenses/N_m3u8DL-RE-MIT.txt). Install Python and FFmpeg separately. The download engine's MIT license applies independently of the NØME interface and brand assets.
