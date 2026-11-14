#import <Cocoa/Cocoa.h>

@interface Launcher : NSObject <NSApplicationDelegate>
@property(nonatomic, strong) NSTask *server;
@property(nonatomic, strong) NSMutableData *startupOutput;
@property(nonatomic, strong) NSURL *pageURL;
@end

@implementation Launcher

- (void)applicationDidFinishLaunching:(NSNotification *)notification {
    NSURL *directory = NSBundle.mainBundle.bundleURL.URLByDeletingLastPathComponent;
    NSURL *script = [directory URLByAppendingPathComponent:@"start.sh"];
    self.server = [[NSTask alloc] init];
    self.server.executableURL = [NSURL fileURLWithPath:@"/bin/sh"];
    self.server.arguments = @[script.path, @"--no-browser"];
    self.server.currentDirectoryURL = directory;
    self.startupOutput = [NSMutableData data];

    NSPipe *output = [NSPipe pipe];
    self.server.standardOutput = output;
    NSFileHandle *reader = output.fileHandleForReading;
    __weak Launcher *weakLauncher = self;
    reader.readabilityHandler = ^(NSFileHandle *handle) {
        NSData *data = handle.availableData;
        dispatch_async(dispatch_get_main_queue(), ^{
            [weakLauncher readOutput:data];
        });
        if (data.length == 0) {
            handle.readabilityHandler = nil;
            [handle closeFile];
        }
    };
    self.server.terminationHandler = ^(NSTask *task) {
        dispatch_async(dispatch_get_main_queue(), ^{
            if (task.terminationStatus != 0) {
                [weakLauncher showError:@"本地服务启动失败。请在终端运行 start.sh 查看详细信息。"];
            }
            [NSApp terminate:nil];
        });
    };

    NSError *error = nil;
    if (![self.server launchAndReturnError:&error]) {
        reader.readabilityHandler = nil;
        [self showError:error.localizedDescription];
        [NSApp terminate:nil];
    }
}

- (void)readOutput:(NSData *)data {
    if (self.pageURL || !data.length) return;
    [self.startupOutput appendData:data];
    NSString *text = [[NSString alloc] initWithData:self.startupOutput encoding:NSUTF8StringEncoding];
    if (!text) return;
    NSRange match = [text rangeOfString:@"http://127\\.0\\.0\\.1:[0-9]+(?=（)"
                                options:NSRegularExpressionSearch];
    if (match.location == NSNotFound) return;
    self.pageURL = [NSURL URLWithString:[text substringWithRange:match]];
    self.startupOutput = nil;
    if (![NSWorkspace.sharedWorkspace openURL:self.pageURL]) {
        [self showError:@"无法打开默认浏览器。请在终端运行 start.sh。"];
        [NSApp terminate:nil];
    }
}

- (BOOL)applicationShouldHandleReopen:(NSApplication *)app hasVisibleWindows:(BOOL)visible {
    if (self.server.running && self.pageURL) [NSWorkspace.sharedWorkspace openURL:self.pageURL];
    return YES;
}

- (void)applicationWillTerminate:(NSNotification *)notification {
    if (self.server.running) [self.server terminate];
}

- (void)showError:(NSString *)message {
    [NSApp activateIgnoringOtherApps:YES];
    NSAlert *alert = [[NSAlert alloc] init];
    alert.alertStyle = NSAlertStyleCritical;
    alert.messageText = @"无法启动 M3U8 下载器";
    alert.informativeText = message;
    [alert runModal];
}

@end

int main(void) {
    @autoreleasepool {
        NSApplication *app = NSApplication.sharedApplication;
        [app setActivationPolicy:NSApplicationActivationPolicyAccessory];
        Launcher *launcher = [[Launcher alloc] init];
        app.delegate = launcher;
        [app run];
        return 0;
    }
}
