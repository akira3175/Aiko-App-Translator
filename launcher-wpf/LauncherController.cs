using System;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Text;
using System.Threading;
using System.Threading.Tasks;

namespace AikoLauncher
{
    internal sealed class LauncherState
    {
        public string InstalledVersion, Headline, Summary, Notes, Status, InstallRoot;
        public bool Busy, Installed, ServerRunning;
        public double Progress;
    }

    internal sealed class LauncherController
    {
        private const string AppUrl = "http://127.0.0.1:8765";
        private string installRoot;
        public event Action<LauncherState> Changed;
        public LauncherState State { get; private set; }

        public LauncherController(string requestedRoot)
        {
            ServicePointManager.SecurityProtocol = SecurityProtocolType.Tls12;
            installRoot = FindInstallRoot(requestedRoot);
            State = new LauncherState { InstallRoot = installRoot, Status = "Đang kiểm tra Aiko…", Headline = "Một nơi cho mọi bản dịch", Summary = "Aiko đang chuẩn bị không gian làm việc của bạn.", Busy = true };
        }

        public async Task CheckAsync()
        {
            await Task.Run(() => Thread.Sleep(50));
            RefreshState();
        }

        public async Task PrimaryAsync()
        {
            if (InstalledVersion() != "") { await OpenAsync(); return; }
            State.Busy = false; State.Status = "Không tìm thấy Aiko"; State.Summary = "Hãy đặt Launcher trong thư mục ZIP portable đã giải nén hoặc chọn thư mục Aiko hiện có."; Raise();
        }

        public async Task OpenAsync()
        {
            SetBusy("Đang mở Aiko…");
            try { await Task.Run(() => EnsureServer()); Process.Start(new ProcessStartInfo(AppUrl) { UseShellExecute = true }); State.Busy = false; State.Status = "Aiko đang chạy"; State.ServerRunning = true; Raise(); }
            catch (Exception error) { Fail("Không mở được Aiko", error); }
        }

        public async Task RestartAsync()
        {
            SetBusy("Đang khởi động lại Aiko…");
            try { await Task.Run(() => { StopServerCore(); EnsureServer(); }); Process.Start(new ProcessStartInfo(AppUrl) { UseShellExecute = true }); State.Busy = false; State.Status = "Aiko đã khởi động lại"; State.ServerRunning = true; Raise(); }
            catch (Exception error) { Fail("Không khởi động lại được Aiko", error); }
        }

        public async Task StopServerAsync()
        {
            SetBusy("Đang tắt server Aiko…");
            try { await Task.Run(() => StopServerCore()); State.Busy = false; State.Status = "Server đã tắt"; State.ServerRunning = false; Raise(); }
            catch (Exception error) { Fail("Không tắt được server Aiko", error); }
        }

        public void UseExisting(string selected)
        {
            if (!File.Exists(Path.Combine(selected, "app.py")) || !File.Exists(Path.Combine(selected, "VERSION"))) throw new InvalidDataException("Thư mục này không chứa bản Aiko hợp lệ.");
            installRoot = Path.GetFullPath(selected); RememberInstallRoot(installRoot); RefreshState();
        }

        public void CreateShortcut()
        {
            string target = Process.GetCurrentProcess().MainModule.FileName;
            string path = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory), "Aiko Launcher.lnk");
            Type shellType = Type.GetTypeFromProgID("WScript.Shell"); dynamic shell = Activator.CreateInstance(shellType); dynamic link = shell.CreateShortcut(path);
            link.TargetPath = target; link.WorkingDirectory = Path.GetDirectoryName(target); link.IconLocation = target + ",0"; link.Description = "Mở và quản lý Aiko App Translator"; link.Save();
            State.Status = "Đã tạo shortcut trên Desktop"; Raise();
        }

        private void RefreshState()
        {
            string installed = InstalledVersion(); bool present = installed != "";
            State = new LauncherState { InstallRoot = installRoot, InstalledVersion = installed, Installed = present, ServerRunning = IsHealthy(), Busy = false, Progress = 0, Notes = "Launcher portable · Không tải xuống hoặc tự cập nhật qua Internet." };
            if (!present) { State.Headline = "Không tìm thấy Aiko"; State.Summary = "Hãy chạy Launcher trong thư mục ZIP portable đã giải nén hoặc chọn thư mục Aiko hiện có."; State.Status = "Chưa chọn đúng thư mục Aiko"; }
            else { State.Headline = "Một nơi cho mọi bản dịch"; State.Summary = "Aiko đã sẵn sàng. Tiếp tục dự án gần nhất hoặc kiểm tra công cụ server."; State.Status = State.ServerRunning ? "Aiko đang chạy" : "Aiko đã sẵn sàng"; }
            Raise();
        }

        private void SetBusy(string status) { State.Busy = true; State.Status = status; State.Progress = 0; Raise(); }
        private void Fail(string status, Exception error) { State.Busy = false; State.Status = status; State.Summary = error.Message; Raise(); }
        private void Raise() { var handler = Changed; if (handler != null) handler(State); }

        private string InstalledVersion() { string file = Path.Combine(installRoot, "VERSION"); return File.Exists(file) ? File.ReadAllText(file, Encoding.UTF8).Trim() : ""; }
        private static string InstallFile() => Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Aiko Launcher", "install.txt");
        private static string FindInstallRoot(string requested) { if (!string.IsNullOrWhiteSpace(requested) && File.Exists(Path.Combine(requested, "app.py"))) return Path.GetFullPath(requested); string remembered = InstallFile(); if (File.Exists(remembered)) { string selected = File.ReadAllText(remembered, Encoding.UTF8).Trim(); if (File.Exists(Path.Combine(selected, "app.py"))) return selected; } return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Aiko App Translator"); }
        private static void RememberInstallRoot(string value) { string file = InstallFile(); Directory.CreateDirectory(Path.GetDirectoryName(file)); File.WriteAllText(file, Path.GetFullPath(value), Encoding.UTF8); }
        private static void ValidatePayload(string payload, string expected) { foreach (string item in new[] { "app.py", "VERSION", "runtime\\python.exe" }) if (!File.Exists(Path.Combine(payload, item))) throw new InvalidDataException("Bản portable thiếu file: " + item); if (File.ReadAllText(Path.Combine(payload, "VERSION"), Encoding.UTF8).Trim() != expected) throw new InvalidDataException("Phiên bản portable không khớp."); }
        private static bool IsHealthy() { try { var request = (HttpWebRequest)WebRequest.Create(AppUrl + "/api/health"); request.Timeout = 900; using (var response = (HttpWebResponse)request.GetResponse()) return response.StatusCode == HttpStatusCode.OK; } catch { return false; } }
        private void EnsureServer() { if (IsHealthy()) return; string python = Path.Combine(installRoot, "runtime", "python.exe"), app = Path.Combine(installRoot, "app.py"); ValidatePayload(installRoot, InstalledVersion()); var info = new ProcessStartInfo(python, "\"" + app + "\"") { WorkingDirectory = installRoot, UseShellExecute = false, CreateNoWindow = true, WindowStyle = ProcessWindowStyle.Hidden }; info.EnvironmentVariables["PYTHONUTF8"] = "1"; info.EnvironmentVariables["AIKO_NO_BROWSER"] = "1"; Process.Start(info); for (int i = 0; i < 60; i++) { Thread.Sleep(250); if (IsHealthy()) return; } throw new InvalidOperationException("Không khởi động được server Aiko."); }
        private void StopServerCore()
        {
            if (!IsHealthy()) { ClearRuntimeLocks(); return; }
            TryRequestServerShutdown();
            if (WaitForServerToStop(12)) { ClearRuntimeLocks(); return; }
            ForceStopOwnedProcesses();
            if (!WaitForServerToStop(20)) throw new TimeoutException("Tiến trình Aiko vẫn chiếm cổng 8765 sau khi cưỡng chế tắt.");
            ClearRuntimeLocks();
        }

        private static bool TryRequestServerShutdown()
        {
            try { var request = (HttpWebRequest)WebRequest.Create(AppUrl + "/api/server/shutdown"); request.Method = "POST"; request.ContentLength = 0; request.Timeout = 2500; using (var response = (HttpWebResponse)request.GetResponse()) return response.StatusCode == HttpStatusCode.OK; }
            catch (WebException) { return false; }
        }

        private static bool WaitForServerToStop(int attempts) { for (int i = 0; i < attempts; i++) { if (!IsHealthy()) return true; Thread.Sleep(250); } return !IsHealthy(); }

        private void ForceStopOwnedProcesses()
        {
            string expectedPython = Path.GetFullPath(Path.Combine(installRoot, "runtime", "python.exe"));
            foreach (Process process in Process.GetProcessesByName("python"))
            {
                try
                {
                    string executable = Path.GetFullPath(process.MainModule.FileName);
                    if (string.Equals(executable, expectedPython, StringComparison.OrdinalIgnoreCase)) process.Kill();
                }
                catch (InvalidOperationException) { }
                catch (System.ComponentModel.Win32Exception) { }
                catch (NotSupportedException) { }
            }
        }

        private void ClearRuntimeLocks()
        {
            string runtime = Path.Combine(installRoot, ".runtime");
            if (!Directory.Exists(runtime)) return;
            foreach (string file in Directory.GetFiles(runtime, "*.stop")) { try { File.Delete(file); } catch (IOException) { } catch (UnauthorizedAccessException) { } }
            string translationLock = Path.Combine(runtime, "translation.lock");
            try { if (File.Exists(translationLock)) File.Delete(translationLock); } catch (IOException) { } catch (UnauthorizedAccessException) { }
        }

        public static int SelfTest() { return Uri.IsWellFormedUriString(AppUrl, UriKind.Absolute) ? 0 : 1; }
    }
}
