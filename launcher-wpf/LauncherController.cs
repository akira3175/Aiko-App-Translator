using System;
using System.Collections;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Net;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using System.Web.Script.Serialization;

namespace AikoLauncher
{
    internal sealed class ReleaseInfo { public string Version, DownloadUrl, Sha256, Notes; }
    internal sealed class LauncherState
    {
        public string InstalledVersion, LatestVersion, Headline, Summary, Notes, Status, InstallRoot;
        public bool Busy, Installed, UpdateAvailable, ServerRunning;
        public double Progress;
    }

    internal sealed class LauncherController
    {
        private const string ReleaseApi = "https://api.github.com/repos/akira3175/Aiko-App-Translator/releases/latest";
        private const string AssetName = "NovelTranslatorStudio-Windows-x64.zip";
        private const string AppUrl = "http://127.0.0.1:8765";
        private string installRoot;
        private ReleaseInfo latest;
        public event Action<LauncherState> Changed;
        public LauncherState State { get; private set; }

        public LauncherController(string requestedRoot)
        {
            ServicePointManager.SecurityProtocol = SecurityProtocolType.Tls12;
            installRoot = FindInstallRoot(requestedRoot);
            State = new LauncherState { InstallRoot = installRoot, Status = "Đang kiểm tra bản mới nhất…", Headline = "Một nơi cho mọi bản dịch", Summary = "Aiko đang kiểm tra phiên bản mới nhất và chuẩn bị không gian làm việc của bạn.", Busy = true };
        }

        public async Task CheckAsync()
        {
            SetBusy("Đang kiểm tra bản mới nhất…");
            try
            {
                latest = await Task.Run(() => LoadLatestRelease());
                RefreshState();
            }
            catch (Exception error) { State.Busy = false; State.Status = "Không kiểm tra được bản mới"; State.Summary = error.Message; Raise(); }
        }

        public async Task PrimaryAsync()
        {
            string installed = InstalledVersion();
            if (installed != "" && (latest == null || CompareVersions(latest.Version, installed) <= 0)) { await OpenAsync(); return; }
            if (latest == null) { await CheckAsync(); return; }
            if (installed == "") await InstallAsync(); else await UpdateAsync();
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
            try { await Task.Run(() => { RequestServerShutdown(); WaitForServerToStop(); EnsureServer(); }); Process.Start(new ProcessStartInfo(AppUrl) { UseShellExecute = true }); State.Busy = false; State.Status = "Aiko đã khởi động lại"; State.ServerRunning = true; Raise(); }
            catch (Exception error) { Fail("Không khởi động lại được Aiko", error); }
        }

        public void StopServer() { RequestServerShutdown(); WaitForServerToStop(); State.Status = "Server đã tắt"; State.ServerRunning = false; Raise(); }

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
            link.TargetPath = target; link.WorkingDirectory = Path.GetDirectoryName(target); link.IconLocation = target + ",0"; link.Description = "Cài đặt, cập nhật và mở Aiko App Translator"; link.Save();
            State.Status = "Đã tạo shortcut trên Desktop"; Raise();
        }

        private async Task InstallAsync()
        {
            SetBusy("Đang chuẩn bị tải Aiko " + latest.Version + "…");
            string work = Path.Combine(Path.GetTempPath(), "AikoLauncher-" + Guid.NewGuid().ToString("N"));
            try
            {
                await Task.Run(() =>
                {
                    Directory.CreateDirectory(work); string archive = Path.Combine(work, AssetName); DownloadAndVerify(latest, archive);
                    string staging = Path.Combine(work, "staging"); ValidateArchivePaths(archive, staging); ZipFile.ExtractToDirectory(archive, staging);
                    string payload = Path.Combine(staging, "NovelTranslatorStudio"); ValidatePayload(payload, latest.Version);
                    if (Directory.Exists(installRoot)) throw new IOException("Thư mục cài đặt đã tồn tại nhưng không phải bản Aiko hợp lệ: " + installRoot);
                    Directory.CreateDirectory(Path.GetDirectoryName(installRoot)); Directory.Move(payload, installRoot); RememberInstallRoot(installRoot);
                });
                RefreshState(); await OpenAsync();
            }
            catch (Exception error) { Fail("Cài đặt không thành công", error); }
            finally { try { if (Directory.Exists(work)) Directory.Delete(work, true); } catch { } }
        }

        private async Task UpdateAsync()
        {
            SetBusy("Đang chuẩn bị tải bản cập nhật " + latest.Version + "…");
            try
            {
                await Task.Run(() =>
                {
                    string work = Path.Combine(Path.GetTempPath(), "AikoUpdate-" + Guid.NewGuid().ToString("N"));
                    Directory.CreateDirectory(work);
                    try
                    {
                        string archive = Path.Combine(work, AssetName); DownloadAndVerify(latest, archive);
                        string staging = Path.Combine(work, "staging"); ValidateArchivePaths(archive, staging); ZipFile.ExtractToDirectory(archive, staging);
                        string payload = Path.Combine(staging, "NovelTranslatorStudio"); ValidatePayload(payload, latest.Version);
                        if (IsHealthy()) { RequestServerShutdown(); WaitForServerToStop(); }
                        ReplaceApplicationFiles(payload);
                    }
                    finally { try { Directory.Delete(work, true); } catch { } }
                });
                RefreshState(); await OpenAsync();
            }
            catch (Exception error) { Fail("Cập nhật chưa hoàn tất", error); }
        }

        private void DownloadAndVerify(ReleaseInfo release, string destination)
        {
            HttpWebRequest request = (HttpWebRequest)WebRequest.Create(release.DownloadUrl); request.UserAgent = "AikoLauncher/2.0"; request.Timeout = 60000; request.ReadWriteTimeout = 60000;
            using (HttpWebResponse response = (HttpWebResponse)request.GetResponse()) using (Stream input = response.GetResponseStream()) using (FileStream output = File.Create(destination))
            {
                long total = response.ContentLength, downloaded = 0; byte[] buffer = new byte[1024 * 1024];
                while (true) { int count = input.Read(buffer, 0, buffer.Length); if (count <= 0) break; output.Write(buffer, 0, count); downloaded += count; ReportProgress(downloaded, total); }
            }
            using (SHA256 sha = SHA256.Create()) using (FileStream input = File.OpenRead(destination))
            {
                string actual = BitConverter.ToString(sha.ComputeHash(input)).Replace("-", "").ToLowerInvariant();
                if (actual != release.Sha256) { File.Delete(destination); throw new InvalidDataException("Checksum SHA-256 không khớp. Gói tải về đã bị xóa."); }
            }
        }

        private void ReportProgress(long downloaded, long total)
        {
            double current = downloaded / 1024d / 1024d;
            State.Progress = total > 0 ? Math.Min(1, (double)downloaded / total) : 0;
            State.Status = total > 0 ? string.Format("Đang tải {0:0.0} MB / {1:0.0} MB · {2:0}%", current, total / 1024d / 1024d, State.Progress * 100) : string.Format("Đã tải {0:0.0} MB…", current);
            Raise();
        }

        private void RefreshState()
        {
            string installed = InstalledVersion(); bool present = installed != ""; bool update = present && latest != null && CompareVersions(latest.Version, installed) > 0;
            State = new LauncherState { InstallRoot = installRoot, InstalledVersion = installed, LatestVersion = latest == null ? "" : latest.Version, Installed = present, UpdateAvailable = update, ServerRunning = IsHealthy(), Busy = false, Progress = 0, Notes = latest == null ? "" : FormatNotes(latest.Notes) };
            if (!present) { State.Headline = "Bắt đầu cùng Aiko"; State.Summary = "Cài đặt trọn bộ ứng dụng, Python và Chrome chỉ với một lần tải."; State.Status = "Aiko chưa được cài trên máy này"; }
            else if (update) { State.Headline = "Bản mới đã sẵn sàng"; State.Summary = "Cập nhật an toàn, giữ nguyên truyện và cài đặt của bạn."; State.Status = "Có bản cập nhật " + latest.Version; }
            else { State.Headline = "Một nơi cho mọi bản dịch"; State.Summary = "Aiko đã sẵn sàng. Tiếp tục dự án gần nhất hoặc kiểm tra công cụ server."; State.Status = State.ServerRunning ? "Aiko đang chạy" : "Aiko đã là phiên bản mới nhất"; }
            Raise();
        }

        private void SetBusy(string status) { State.Busy = true; State.Status = status; State.Progress = 0; Raise(); }
        private void Fail(string status, Exception error) { State.Busy = false; State.Status = status; State.Summary = error.Message; Raise(); }
        private void Raise() { var handler = Changed; if (handler != null) handler(State); }

        private static ReleaseInfo LoadLatestRelease()
        {
            HttpWebRequest request = (HttpWebRequest)WebRequest.Create(ReleaseApi); request.UserAgent = "AikoLauncher/2.0"; request.Accept = "application/vnd.github+json"; request.Timeout = 20000;
            using (HttpWebResponse response = (HttpWebResponse)request.GetResponse()) using (StreamReader reader = new StreamReader(response.GetResponseStream(), Encoding.UTF8))
            {
                IDictionary release = new JavaScriptSerializer { MaxJsonLength = 1024 * 1024 }.DeserializeObject(reader.ReadToEnd()) as IDictionary;
                if (release == null) throw new InvalidDataException("GitHub trả về dữ liệu không hợp lệ.");
                string tag = Convert.ToString(release["tag_name"]).Trim().TrimStart('v'); CompareVersions(tag, "0.0.0"); IDictionary selected = null;
                foreach (object item in (object[])release["assets"]) { IDictionary asset = item as IDictionary; if (asset != null && Convert.ToString(asset["name"]) == AssetName) { selected = asset; break; } }
                if (selected == null) throw new InvalidDataException("Bản phát hành thiếu gói Windows.");
                string digest = Convert.ToString(selected["digest"]); if (!digest.StartsWith("sha256:", StringComparison.OrdinalIgnoreCase) || digest.Length != 71) throw new InvalidDataException("Bản phát hành thiếu SHA-256 hợp lệ.");
                string url = Convert.ToString(selected["browser_download_url"]); Uri parsed; if (!Uri.TryCreate(url, UriKind.Absolute, out parsed) || parsed.Scheme != Uri.UriSchemeHttps) throw new InvalidDataException("Đường dẫn tải bản Windows không an toàn.");
                return new ReleaseInfo { Version = tag, DownloadUrl = url, Sha256 = digest.Substring(7).ToLowerInvariant(), Notes = Convert.ToString(release["body"]) };
            }
        }

        private string InstalledVersion() { string file = Path.Combine(installRoot, "VERSION"); return File.Exists(file) ? File.ReadAllText(file, Encoding.UTF8).Trim() : ""; }
        private static int CompareVersions(string left, string right) { Version a, b; if (!Version.TryParse(left.TrimStart('v'), out a) || !Version.TryParse(right.TrimStart('v'), out b)) throw new InvalidDataException("Phiên bản GitHub không hợp lệ."); return a.CompareTo(b); }
        private static string FormatNotes(string value) { var result = new StringBuilder(); foreach (string raw in (value ?? "").Replace("\r", "").Split('\n')) { string line = raw.Trim(); while (line.StartsWith("#")) line = line.Substring(1).TrimStart(); if (line.StartsWith("SHA-256", StringComparison.OrdinalIgnoreCase)) continue; if (line.StartsWith("- ")) line = "• " + line.Substring(2); line = line.Replace("`", ""); if (line.Length == 0 && (result.Length == 0 || result.ToString().EndsWith("\r\n\r\n"))) continue; result.AppendLine(line); } return result.ToString().Trim(); }
        private static string InstallFile() => Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Aiko Launcher", "install.txt");
        private static string FindInstallRoot(string requested) { if (!string.IsNullOrWhiteSpace(requested) && File.Exists(Path.Combine(requested, "app.py"))) return Path.GetFullPath(requested); string remembered = InstallFile(); if (File.Exists(remembered)) { string selected = File.ReadAllText(remembered, Encoding.UTF8).Trim(); if (File.Exists(Path.Combine(selected, "app.py"))) return selected; } return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Aiko App Translator"); }
        private static void RememberInstallRoot(string value) { string file = InstallFile(); Directory.CreateDirectory(Path.GetDirectoryName(file)); File.WriteAllText(file, Path.GetFullPath(value), Encoding.UTF8); }
        private static void ValidatePayload(string payload, string expected) { foreach (string item in new[] { "app.py", "VERSION", "runtime\\python.exe", "apply_update.ps1" }) if (!File.Exists(Path.Combine(payload, item))) throw new InvalidDataException("Gói cài đặt thiếu file: " + item); if (File.ReadAllText(Path.Combine(payload, "VERSION"), Encoding.UTF8).Trim() != expected) throw new InvalidDataException("Phiên bản trong gói không khớp."); }
        private static void ValidateArchivePaths(string archivePath, string destination) { string root = Path.GetFullPath(destination).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar; using (ZipArchive archive = ZipFile.OpenRead(archivePath)) foreach (ZipArchiveEntry entry in archive.Entries) { string target = Path.GetFullPath(Path.Combine(destination, entry.FullName.Replace('/', Path.DirectorySeparatorChar))); if (!target.StartsWith(root, StringComparison.OrdinalIgnoreCase)) throw new InvalidDataException("Gói cài đặt chứa đường dẫn không an toàn."); } }
        private static void ValidateArchiveVersion(string archivePath, string expected) { using (ZipArchive archive = ZipFile.OpenRead(archivePath)) { ZipArchiveEntry version = archive.GetEntry("NovelTranslatorStudio/VERSION"); if (version == null) throw new InvalidDataException("Gói cập nhật thiếu VERSION."); using (var reader = new StreamReader(version.Open(), Encoding.UTF8)) if (reader.ReadToEnd().Trim() != expected) throw new InvalidDataException("Phiên bản trong gói cập nhật không khớp."); } }
        private static bool IsHealthy() { try { var request = (HttpWebRequest)WebRequest.Create(AppUrl + "/api/health"); request.Timeout = 900; using (var response = (HttpWebResponse)request.GetResponse()) return response.StatusCode == HttpStatusCode.OK; } catch { return false; } }
        private void EnsureServer() { if (IsHealthy()) return; string python = Path.Combine(installRoot, "runtime", "python.exe"), app = Path.Combine(installRoot, "app.py"); ValidatePayload(installRoot, InstalledVersion()); var info = new ProcessStartInfo(python, "\"" + app + "\"") { WorkingDirectory = installRoot, UseShellExecute = false, CreateNoWindow = true, WindowStyle = ProcessWindowStyle.Hidden }; info.EnvironmentVariables["PYTHONUTF8"] = "1"; info.EnvironmentVariables["AIKO_NO_BROWSER"] = "1"; Process.Start(info); for (int i = 0; i < 60; i++) { Thread.Sleep(250); if (IsHealthy()) return; } throw new InvalidOperationException("Không khởi động được server Aiko."); }
        private static void RequestServerShutdown() { var request = (HttpWebRequest)WebRequest.Create(AppUrl + "/api/server/shutdown"); request.Method = "POST"; request.ContentLength = 0; request.Timeout = 3000; using (var response = (HttpWebResponse)request.GetResponse()) { } }
        private static void WaitForServerToStop() { for (int i = 0; i < 40; i++) { if (!IsHealthy()) return; Thread.Sleep(250); } throw new TimeoutException("Server Aiko chưa tắt. Hãy dừng tác vụ đang chạy rồi thử lại."); }
        private void ReplaceApplicationFiles(string payload)
        {
            string[] protectedNames = { ".runtime", "truyen", "data", "apikeys.txt", "r19_words.txt", "r19_word.txt" };
            foreach (string source in Directory.GetFileSystemEntries(payload))
            {
                string name = Path.GetFileName(source);
                if (Array.IndexOf(protectedNames, name) >= 0) continue;
                string target = Path.Combine(installRoot, name);
                if (Directory.Exists(target)) Directory.Delete(target, true); else if (File.Exists(target)) File.Delete(target);
                if (Directory.Exists(source)) Directory.Move(source, target); else File.Move(source, target);
            }
        }

        public static int SelfTest() { try { if (CompareVersions("1.0.1", "1.0.0") <= 0) return 1; if (CompareVersions("v1.0.0", "1.0.0") != 0) return 2; if (!FormatNotes("## Mới\n- Sửa `lỗi`").Contains("• Sửa lỗi")) return 3; return 0; } catch { return 4; } }
    }
}
