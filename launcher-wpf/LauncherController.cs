using System;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Collections.Generic;
using System.Runtime.InteropServices;

namespace AikoLauncher
{
    internal sealed class LauncherState
    {
        public string InstalledVersion, Headline, Summary, Notes, Status, InstallRoot;
        public bool Busy, Installed, ServerRunning, UpdateAvailable, CanCancel, Checking, HasError;
        public double Progress;
    }

    internal sealed class LauncherController
    {
        private const string AppUrl = "http://127.0.0.1:8765";
        private string installRoot;
        private PortableRelease release;
        private CancellationTokenSource downloadCancellation;
        private Process updateProcess;
        public event Action<LauncherState> Changed;
        public LauncherState State { get; private set; }

        public LauncherController(string requestedRoot)
        {
            ServicePointManager.SecurityProtocol = SecurityProtocolType.Tls12;
            installRoot = FindInstallRoot(requestedRoot);
            string installed = InstalledVersion();
            State = new LauncherState { InstallRoot = installRoot, Installed = installed != "", InstalledVersion = installed, Status = "Đang kiểm tra cập nhật…", Busy = true, Checking = true, Progress = -1 };
        }

        public async Task CheckAsync()
        {
            if (State.Busy && downloadCancellation != null) return;
            release = null;
            State.Checking = true;
            SetBusy("Đang kiểm tra bản mới…");
            try { release = await Task.Run(() => PortableUpdater.Check()); }
            catch (Exception error) { RefreshState(); State.HasError = true; State.Status = "Không kiểm tra được bản mới · có thể thử lại trong menu ⋯"; State.Notes = error.Message; Raise(); return; }
            RefreshState();
        }

        public async Task PrimaryAsync()
        {
            if (State.Busy) return;
            if (!State.Installed || State.UpdateAvailable) { await InstallAsync(); return; }
            await OpenAsync();
        }

        public void CancelDownload() { if (State.CanCancel && downloadCancellation != null) downloadCancellation.Cancel(); }

        public async Task InstallAsync()
        {
            if (State.Busy) return;
            if (release == null) { await CheckAsync(); if (release == null) return; }
            string work = null;
            bool hadServer = false, startedInstall = false;
            SetBusy("Đang chuẩn bị tải Aiko…");
            downloadCancellation = new CancellationTokenSource(); State.CanCancel = true; Raise();
            try
            {
                if (Directory.Exists(Path.Combine(installRoot, ".git"))) throw new IOException("Đây là thư mục mã nguồn. Hãy chọn một bản portable hoặc thư mục cài mới.");
                if (File.Exists(Path.Combine(installRoot, ".runtime", "launcher-update-pending.txt"))) throw new IOException("Lần cập nhật trước bị gián đoạn. Xem .runtime/launcher-update-pending.txt trước khi tiếp tục.");
                if (State.Installed && !File.Exists(Path.Combine(installRoot, "runtime", "python.exe"))) throw new IOException("Chỉ cập nhật trực tiếp bản portable có runtime/python.exe.");
                if (!State.Installed && Directory.Exists(installRoot) && Array.Exists(Directory.GetFileSystemEntries(installRoot), p => Path.GetFileName(p) != ".runtime"))
                    throw new IOException("Thư mục cài mới phải trống. Hãy chọn thư mục khác trong menu ⋯.");
                work = Path.Combine(installRoot, ".runtime", "launcher-updates", Guid.NewGuid().ToString("N"));
                string payload = await Task.Run(() => PortableUpdater.DownloadAndExtract(release, work, downloadCancellation.Token,
                    (status, progress) => { State.Status = status; State.Progress = progress; Raise(); }));
                downloadCancellation.Token.ThrowIfCancellationRequested();
                State.CanCancel = false; State.Status = "Đang cài đặt · vui lòng giữ Launcher mở"; State.Progress = -1; Raise();
                await Task.Run(() =>
                {
                    hadServer = IsHealthy();
                    if (hadServer)
                    {
                        using (var owner = Process.GetProcessById(ServerProcessId()))
                            if (!string.Equals(owner.MainModule.FileName, Path.GetFullPath(Path.Combine(installRoot, "runtime", "python.exe")), StringComparison.OrdinalIgnoreCase))
                                throw new IOException("Một bản Aiko khác đang dùng cổng 8765. Hãy đóng bản đó trước khi cập nhật.");
                        // Never force a running translation to close for an update.
                        var jobs = ReadServerJson("/api/jobs/active");
                        if (((System.Collections.ICollection)jobs["items"]).Count != 0) throw new IOException("Hãy dừng các tác vụ trong Aiko rồi thử cập nhật lại.");
                        if (!TryRequestServerShutdown() || !WaitForServerToStop(80)) throw new IOException("Aiko chưa đóng. Hãy đóng app rồi thử lại.");
                    }
                    WaitForOwnedPythonExit();
                    startedInstall = true;
                    PortableUpdater.Install(payload, installRoot, Path.Combine(work, "backup"), () => StartUpdatedServer(release.Version), StopUpdatedServer);
                    if (updateProcess != null) { updateProcess.Dispose(); updateProcess = null; }
                });
                RememberInstallRoot(installRoot);
                RefreshState(); State.Status = "Đã cài Aiko " + release.Version; State.Progress = 1;
                State.Notes = "Bản sao lưu chương trình: " + Path.Combine(work, "backup"); Raise();
            }
            catch (OperationCanceledException) { RefreshState(); State.Status = "Đã hủy tải · chưa thay đổi ứng dụng"; Raise(); }
            catch (Exception error)
            {
                if (startedInstall && hadServer && !File.Exists(Path.Combine(installRoot, ".runtime", "launcher-update-pending.txt")))
                { try { await Task.Run(() => EnsureServer()); } catch { } }
                RefreshState(); Fail("Chưa cài được Aiko", error);
            }
            finally
            {
                // Keep backups and any interrupted transaction for recovery.
                if (work != null && Directory.Exists(work) && !Directory.Exists(Path.Combine(work, "backup")))
                { try { Directory.Delete(PortableUpdater.Child(Path.Combine(installRoot, ".runtime", "launcher-updates"), Path.GetFileName(work)), true); } catch (IOException) { } catch (UnauthorizedAccessException) { } }
                downloadCancellation.Dispose(); downloadCancellation = null; State.CanCancel = false; State.Busy = false; Raise();
            }
        }

        public void UseDestination(string selected)
        {
            if (State.Busy) return;
            if (Directory.Exists(selected) && Directory.GetFileSystemEntries(selected).Length != 0) throw new IOException("Hãy chọn thư mục trống để cài mới.");
            installRoot = Path.GetFullPath(selected); RefreshState();
        }

        private static Dictionary<string, object> ReadServerJson(string path)
        {
            var request = (HttpWebRequest)WebRequest.Create(AppUrl + path); request.Timeout = 2500;
            using (var response = request.GetResponse())
            using (var reader = new StreamReader(response.GetResponseStream())) return new JavaScriptSerializer().Deserialize<Dictionary<string, object>>(reader.ReadToEnd());
        }

        private void WaitForOwnedPythonExit()
        {
            string expected = Path.GetFullPath(Path.Combine(installRoot, "runtime", "python.exe"));
            foreach (var process in Process.GetProcessesByName("python"))
            using (process)
            {
                string executable;
                try { executable = process.MainModule.FileName; } catch { continue; }
                if (string.Equals(executable, expected, StringComparison.OrdinalIgnoreCase) && !process.WaitForExit(15000))
                    throw new IOException("Python của Aiko vẫn đang chạy. Hãy đóng các tác vụ rồi thử lại.");
            }
        }

        private void StartUpdatedServer(string expectedVersion)
        {
            if (IsHealthy()) throw new IOException("Cổng 8765 đang được dùng; chưa thể kiểm tra bản mới.");
            var info = new ProcessStartInfo(Path.Combine(installRoot, "runtime", "python.exe"), "\"" + Path.Combine(installRoot, "app.py") + "\"")
                { WorkingDirectory = installRoot, UseShellExecute = false, CreateNoWindow = true, WindowStyle = ProcessWindowStyle.Hidden };
            info.EnvironmentVariables["PYTHONUTF8"] = "1"; info.EnvironmentVariables["AIKO_NO_BROWSER"] = "1";
            updateProcess = Process.Start(info);
            for (int i = 0; i < 120; i++)
            {
                if (updateProcess.HasExited) break;
                try { var health = ReadServerJson("/api/health"); if (Convert.ToString(health["version"]) == expectedVersion && Convert.ToBoolean(health["ok"]) && ServerProcessId() == updateProcess.Id) return; } catch (WebException) { }
                Thread.Sleep(250);
            }
            throw new IOException("Bản mới không khởi động được hoặc trả về sai phiên bản.");
        }

        private void StopUpdatedServer()
        {
            if (updateProcess == null) return;
            // Only stop the new process created by this update, never unrelated Python.
            if (!updateProcess.HasExited) { updateProcess.Kill(); if (!updateProcess.WaitForExit(10000)) throw new IOException("Không dừng được bản mới để khôi phục."); }
            updateProcess.Dispose(); updateProcess = null;
        }

        [DllImport("iphlpapi.dll", SetLastError = true)]
        private static extern uint GetExtendedTcpTable(IntPtr table, ref int size, bool order, int family, int tableClass, uint reserved);

        private static int ServerProcessId()
        {
            int size = 0;
            GetExtendedTcpTable(IntPtr.Zero, ref size, false, 2, 3, 0); // IPv4, TCP_TABLE_OWNER_PID_LISTENER
            IntPtr table = Marshal.AllocHGlobal(size);
            try
            {
                if (GetExtendedTcpTable(table, ref size, false, 2, 3, 0) != 0) throw new IOException("Không xác định được tiến trình server.");
                int rows = Marshal.ReadInt32(table);
                for (int i = 0; i < rows; i++)
                {
                    int offset = 4 + i * 24;
                    int port = (Marshal.ReadByte(table, offset + 8) << 8) | Marshal.ReadByte(table, offset + 9);
                    if (port == 8765) return Marshal.ReadInt32(table, offset + 20);
                }
                throw new IOException("Không tìm thấy tiến trình server Aiko.");
            }
            finally { Marshal.FreeHGlobal(table); }
        }

        public async Task OpenAsync()
        {
            if (State.Busy) return;
            if (File.Exists(Path.Combine(installRoot, ".runtime", "launcher-update-pending.txt"))) { Fail("Cập nhật bị gián đoạn", new IOException("Hãy khôi phục theo .runtime/launcher-update-pending.txt trước khi mở Aiko.")); return; }
            SetBusy("Đang mở ứng dụng…");
            try { await Task.Run(() => EnsureServer()); Process.Start(new ProcessStartInfo(AppUrl) { UseShellExecute = true }); State.Busy = false; State.Status = "Server đang chạy"; State.ServerRunning = true; Raise(); }
            catch (Exception error) { Fail("Không mở được ứng dụng", error); }
        }

        public async Task RestartAsync()
        {
            if (State.Busy) return;
            if (File.Exists(Path.Combine(installRoot, ".runtime", "launcher-update-pending.txt"))) { Fail("Cập nhật bị gián đoạn", new IOException("Hãy khôi phục theo .runtime/launcher-update-pending.txt trước khi mở Aiko.")); return; }
            SetBusy("Đang khởi động lại server…");
            try { await Task.Run(() => { StopServerCore(); EnsureServer(); }); Process.Start(new ProcessStartInfo(AppUrl) { UseShellExecute = true }); State.Busy = false; State.Status = "Server đang chạy"; State.ServerRunning = true; Raise(); }
            catch (Exception error) { Fail("Không khởi động lại được server", error); }
        }

        public async Task StopServerAsync()
        {
            if (State.Busy) return;
            SetBusy("Đang dừng server…");
            try { await Task.Run(() => StopServerCore()); State.Busy = false; State.Status = "Server chưa chạy"; State.ServerRunning = false; Raise(); }
            catch (Exception error) { Fail("Không tắt được server Aiko", error); }
        }

        public void UseExisting(string selected)
        {
            if (State.Busy) return;
            if (!File.Exists(Path.Combine(selected, "app.py")) || !File.Exists(Path.Combine(selected, "VERSION"))) throw new InvalidDataException("Thư mục này không chứa bản Aiko hợp lệ.");
            PortableUpdater.ParseVersion(File.ReadAllText(Path.Combine(selected, "VERSION"), Encoding.UTF8).Trim());
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
            bool available = release != null && (!present || PortableUpdater.ParseVersion(release.Version) > PortableUpdater.ParseVersion(installed));
            State = new LauncherState { InstallRoot = installRoot, InstalledVersion = installed, Installed = present, UpdateAvailable = available, ServerRunning = IsHealthy(), Busy = false, Progress = 0, Notes = release == null ? "Mở menu ⋯ để kiểm tra bản mới hoặc chọn thư mục." : release.Notes };
            if (!present) { State.Headline = "Cài đặt Aiko"; State.Summary = "Tải bản portable vào thư mục bên dưới. Bạn có thể đổi thư mục trong menu ⋯."; State.Status = "Sẵn sàng tải Aiko"; }
            else { State.Headline = "Một nơi cho mọi bản dịch"; State.Summary = "Aiko đã sẵn sàng. Tiếp tục dự án gần nhất hoặc kiểm tra công cụ server."; State.Status = State.ServerRunning ? "Server đang chạy" : "Server chưa chạy"; }
            if (available && present) { State.Headline = "Có Aiko " + release.Version; State.Summary = "Lưu công việc và dừng các tác vụ trước khi cập nhật. Truyện và cấu hình hiện tại được giữ lại."; State.Status = "Sẵn sàng cập nhật"; }
            Raise();
        }

        private void SetBusy(string status) { State.Busy = true; State.HasError = false; State.Status = status; State.Progress = -1; Raise(); }
        private void Fail(string status, Exception error) { State.Busy = false; State.Checking = false; State.HasError = true; State.Status = status; State.Summary = error.Message; State.Notes = error.Message; Raise(); }
        private void Raise() { var handler = Changed; if (handler != null) handler(State); }

        private string InstalledVersion() { string file = Path.Combine(installRoot, "VERSION"); return File.Exists(file) && File.Exists(Path.Combine(installRoot, "app.py")) ? File.ReadAllText(file, Encoding.UTF8).Trim() : ""; }
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
