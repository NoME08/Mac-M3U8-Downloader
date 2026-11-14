# NØME M3U8 下载器

简体中文 · [English](README.en.md)

一个在 Mac 本地运行的 M3U8 下载界面。贴上链接、填好文件名并选择保存位置，下载完成后会合并成 MP4。

## 安装与启动

1. 从 GitHub Releases 下载 `nome-m3u8-v1.0.0-macos-arm64.zip`，用 macOS「归档实用工具」解压。此包面向 Apple 芯片 Mac，启动器使用本地签名，未经过 Apple 公证。
2. 准备 Python 3.9 或更新版本，以及带 `ffprobe` 的 FFmpeg。使用 Homebrew 时可运行 `brew install python ffmpeg`。
3. 在解压后的文件夹里双击 **M3U8 下载器.app**。也可以在该文件夹下运行 `./start.sh`。启动器、脚本、资源和下载引擎需放在同一文件夹内。

浏览器会打开本地页面。服务只监听 `127.0.0.1`，默认端口被其他程序占用时会选择可用端口。点页面上的「关闭服务」可释放端口。正常关闭最后一个标签页后，服务也会自动退出。已经开始的下载会继续处理。

## 下载影片

- 已有 M3U8 链接时，展开「手动输入 M3U8 链接」，填写链接和播放页编号。
- 对 ikanbot，可以先贴播放页链接或输入编号，点击「查找线路」。如果网站限制直接查找，把「一键从播放页导入」里的链接拖到浏览器书签栏，再到已打开的播放页点该书签。导入会带回片名和可选线路。
- 选择保存位置，填写或修改文件名，再点「开始下载 MP4」。同名文件会加序号。显示进度、日志及保存路径。
- 独立字幕默认只保留识别为中文的轨道，也可以选本地中文字幕文件。已经压进画面的字幕会随片源保留。请下载你有权保存的内容。

## 从源码运行

准备上述依赖，从 [N_m3u8DL-RE v0.5.1-beta](https://github.com/nilaoda/N_m3u8DL-RE/releases/tag/v0.5.1-beta) 下载与你的 Mac 架构匹配的构建，解压 `N_m3u8DL-RE` 并放到项目根目录。然后运行：

```sh
chmod +x N_m3u8DL-RE start.sh
./start.sh
```

`downloader.py` 提供本地服务，`index.html` 是浏览器界面，`assets/` 存放主题和品牌素材。`launcher.m` 和 `macos/Info.plist` 是 Finder 启动器的源码与配置。要用 Xcode Command Line Tools 重建启动器：

```sh
app='M3U8 下载器.app'
mkdir -p "$app/Contents/MacOS"
cp macos/Info.plist "$app/Contents/Info.plist"
clang -fobjc-arc -framework Cocoa -arch arm64 -arch x86_64 \
  -mmacosx-version-min=11.0 launcher.m -o "$app/Contents/MacOS/launch"
codesign --force --sign - "$app"
```

## 第三方组件

安装包包含上游原版 [N_m3u8DL-RE](https://github.com/nilaoda/N_m3u8DL-RE)，其许可见 [上游 MIT 许可](licenses/N_m3u8DL-RE-MIT.txt)。Python 与 FFmpeg 由使用者安装。NØME 界面与品牌素材的授权独立于下载引擎的 MIT 许可。
