using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Net;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Web.Script.Serialization;

namespace AikoLauncher
{
    internal sealed class PortableRelease
    {
        public string Version, Url, Sha256, Notes;
        public long Size;
    }

    // No shell, self-replacement, elevation, or changes to antivirus settings.
    internal static class PortableUpdater
    {
        static PortableUpdater()
        {
            AppContext.SetSwitch("Switch.System.IO.UseLegacyPathHandling", false);
            AppContext.SetSwitch("Switch.System.IO.BlockLongPaths", false);
        }
        internal const string AssetName = "NovelTranslatorStudio-Windows-x64.zip";
        private const string Repository = "akira3175/Aiko-App-Translator";
        private static readonly HashSet<string> Protected = new HashSet<string>(StringComparer.OrdinalIgnoreCase)
        { ".runtime", "truyen", "data", "apikeys.txt", "r19_words.txt", "r19_word.txt", "Aiko-Launcher.exe", "Aiko-Launcher.exe.sha256", "Aiko App Translator.exe", "Assets" };

        internal static Version ParseVersion(string value)
        {
            var match = Regex.Match(value ?? "", @"^v?(\d+\.\d+\.\d+)(?:[-+][0-9A-Za-z.-]+)?$");
            if (!match.Success) throw new InvalidDataException("Phiên bản không hợp lệ: " + value);
            return new Version(match.Groups[1].Value);
        }

        internal static PortableRelease Check()
        {
            var request = Request("https://api.github.com/repos/" + Repository + "/releases/latest");
            using (var response = request.GetResponse())
            using (var reader = new StreamReader(response.GetResponseStream(), Encoding.UTF8))
            {
                var chars = new char[1000001]; int count = 0, read;
                while (count < chars.Length && (read = reader.Read(chars, count, chars.Length - count)) > 0) count += read;
                if (count == chars.Length) throw new InvalidDataException("Dữ liệu GitHub quá lớn.");
                return ParseRelease(new string(chars, 0, count));
            }
        }

        internal static PortableRelease ParseRelease(string json)
        {
            var data = new JavaScriptSerializer().Deserialize<Dictionary<string, object>>(json);
            var release = new PortableRelease { Version = Convert.ToString(data["tag_name"]).TrimStart('v'), Notes = Convert.ToString(data["body"]) };
            ParseVersion(release.Version);
            foreach (var item in (System.Collections.IEnumerable)data["assets"])
            {
                var asset = (Dictionary<string, object>)item;
                if (Convert.ToString(asset["name"]) != AssetName) continue;
                release.Url = Convert.ToString(asset["browser_download_url"]);
                string digest = asset.ContainsKey("digest") ? Convert.ToString(asset["digest"]) : "";
                if (!Regex.IsMatch(digest, "^sha256:[0-9a-fA-F]{64}$")) throw new InvalidDataException("Release thiếu SHA-256 hợp lệ. Hãy thử kiểm tra lại sau.");
                release.Sha256 = digest.Substring(7).ToLowerInvariant();
                release.Size = Convert.ToInt64(asset["size"]);
                var uri = new Uri(release.Url);
                if (uri.Scheme != "https" || uri.Host != "github.com" || !uri.AbsolutePath.StartsWith("/" + Repository + "/releases/download/", StringComparison.Ordinal))
                    throw new InvalidDataException("Gói tải không thuộc kho phát hành Aiko.");
                if (release.Size <= 0 || release.Size > 2L * 1024 * 1024 * 1024) throw new InvalidDataException("Kích thước gói tải không hợp lệ.");
                return release;
            }
            throw new InvalidDataException("Release chưa có gói Windows portable.");
        }

        private static HttpWebRequest Request(string url)
        {
            var request = (HttpWebRequest)WebRequest.Create(url);
            request.UserAgent = "Aiko-Launcher/1.1";
            request.Timeout = 20000; request.ReadWriteTimeout = 20000;
            return request;
        }

        internal static string DownloadAndExtract(PortableRelease release, string work, CancellationToken token, Action<string, double> progress)
        {
            Directory.CreateDirectory(work);
            string zip = Path.Combine(work, "download.zip");
            var request = Request(release.Url);
            try
            {
                using (token.Register(request.Abort))
                using (var response = request.GetResponse())
                using (var source = response.GetResponseStream())
                using (var output = new FileStream(zip, FileMode.CreateNew, FileAccess.Write))
                {
                    var buffer = new byte[1024 * 1024]; long total = 0; int read;
                    while ((read = source.Read(buffer, 0, buffer.Length)) > 0)
                    {
                        token.ThrowIfCancellationRequested(); total += read;
                        if (total > release.Size) throw new InvalidDataException("Gói tải lớn hơn thông tin phát hành.");
                        output.Write(buffer, 0, read);
                        progress("Đang tải Aiko · " + (total / 1048576) + " / " + (release.Size / 1048576) + " MB · " + (int)(100.0 * total / release.Size) + "%", (double)total / release.Size);
                    }
                    if (total != release.Size) throw new InvalidDataException("Gói tải chưa đầy đủ. Hãy thử lại.");
                }
                token.ThrowIfCancellationRequested(); progress("Đang kiểm tra gói tải…", -1);
                VerifyHash(zip, release.Sha256);
                progress("Đang giải nén bản mới…", -1);
                string payload = Extract(zip, Path.Combine(work, "staging"), release.Version, token);
                File.Delete(zip);
                return payload;
            }
            catch { token.ThrowIfCancellationRequested(); throw; }
        }

        internal static void VerifyHash(string zip, string expected)
        {
            using (var hash = SHA256.Create())
            using (var file = File.OpenRead(zip))
                if (!string.Equals(BitConverter.ToString(hash.ComputeHash(file)).Replace("-", ""), expected, StringComparison.OrdinalIgnoreCase))
                    throw new InvalidDataException("SHA-256 không khớp. Gói tải sẽ không được cài.");
        }

        internal static string Child(string root, string name)
        {
            string parent = Path.GetFullPath(root).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
            string path = Path.GetFullPath(Path.Combine(parent, name));
            if (!path.StartsWith(parent, StringComparison.OrdinalIgnoreCase) || name.Contains(":")) throw new InvalidDataException("Đường dẫn gói cập nhật không an toàn.");
            return ExtendedPath(path);
        }

        private static string ExtendedPath(string value)
        {
            string path = Path.GetFullPath(value);
            if (!path.StartsWith(@"\\?\", StringComparison.Ordinal))
                return path.StartsWith(@"\\", StringComparison.Ordinal) ? @"\\?\UNC\" + path.Substring(2) : @"\\?\" + path;
            return path;
        }

        internal static string Extract(string zip, string staging, string version, CancellationToken token)
        {
            Directory.CreateDirectory(staging);
            long size = 0;
            using (var archive = ZipFile.OpenRead(zip))
            {
                if (archive.Entries.Count > 50000) throw new InvalidDataException("Gói cập nhật chứa quá nhiều file.");
                foreach (var entry in archive.Entries)
                {
                    token.ThrowIfCancellationRequested();
                    string name = entry.FullName.Replace('/', '\\');
                    if (!name.StartsWith("NovelTranslatorStudio\\", StringComparison.OrdinalIgnoreCase) || name.Split('\\').Any(p => p == ".." || p.EndsWith(".") || p.EndsWith(" ")))
                        throw new InvalidDataException("Cấu trúc ZIP không hợp lệ.");
                    string target = Child(staging, name);
                    size += entry.Length;
                    if (size > 4L * 1024 * 1024 * 1024) throw new InvalidDataException("Gói giải nén quá lớn.");
                    if (name.EndsWith("\\")) { Directory.CreateDirectory(target); continue; }
                    Directory.CreateDirectory(Path.GetDirectoryName(target));
                    using (var input = entry.Open())
                    using (var output = new FileStream(target, FileMode.CreateNew, FileAccess.Write)) input.CopyTo(output);
                }
            }
            string payload = Child(staging, "NovelTranslatorStudio");
            foreach (string file in new[] { "VERSION", "app.py", "runtime\\python.exe" })
                if (!File.Exists(Path.Combine(payload, file))) throw new InvalidDataException("Gói portable thiếu " + file);
            if (File.ReadAllText(Path.Combine(payload, "VERSION"), Encoding.UTF8).Trim() != version) throw new InvalidDataException("Phiên bản trong ZIP không khớp.");
            return payload;
        }

        // Keep a write-ahead journal so a power loss never looks like a completed update.
        internal static void Install(string payload, string root, string backup, Action verify, Action stopFailed)
        {
            Directory.CreateDirectory(root); Directory.CreateDirectory(backup);
            var old = new List<string>(); var added = new List<string>();
            string journal = Path.Combine(root, ".runtime", "launcher-update-pending.txt");
            Directory.CreateDirectory(Path.GetDirectoryName(journal));
            if (File.Exists(journal)) throw new IOException("Có lần cập nhật chưa hoàn tất. Xem " + journal);
            File.WriteAllText(journal, "Backup: " + backup + Environment.NewLine, Encoding.UTF8);
            try
            {
                // Publisher settings used to live beside the upload scripts.
                foreach (string name in new[] { "config_md.json", "image_cache.json" })
                {
                    string saved = Path.Combine(root, "up", name), target = Path.Combine(payload, "up", name);
                    if (File.Exists(saved)) { Directory.CreateDirectory(Path.GetDirectoryName(target)); File.Copy(saved, target, true); }
                }
                foreach (string source in Directory.GetFileSystemEntries(payload))
                {
                    string name = Path.GetFileName(source);
                    string target = Child(root, name), saved = Child(backup, name);
                    if (Protected.Contains(name) && (name == ".runtime" || name.EndsWith(".exe", StringComparison.OrdinalIgnoreCase) || File.Exists(target) || Directory.Exists(target))) continue;
                    File.AppendAllText(journal, "Replace: " + name + Environment.NewLine);
                    if (Directory.Exists(target) || File.Exists(target)) { Move(target, saved); old.Add(name); }
                    Move(source, target); added.Add(name);
                }
                verify();
                File.Delete(journal);
            }
            catch (Exception original)
            {
                try
                {
                    stopFailed();
                    foreach (string name in added.AsEnumerable().Reverse()) Move(Child(root, name), Child(payload, name));
                    foreach (string name in old.AsEnumerable().Reverse()) Move(Child(backup, name), Child(root, name));
                    File.Delete(journal);
                }
                catch (Exception rollback) { throw new IOException("Chưa khôi phục xong. Giữ nguyên thư mục sao lưu: " + backup + ". " + rollback.Message, original); }
                throw new IOException("Cài đặt thất bại; đã khôi phục phần chương trình cũ. " + original.Message, original);
            }
        }

        private static void Move(string source, string target)
        {
            source = ExtendedPath(source); target = ExtendedPath(target);
            if ((File.GetAttributes(source) & FileAttributes.ReparsePoint) != 0) throw new IOException("Không cập nhật qua liên kết thư mục: " + source);
            if (Directory.Exists(source)) Directory.Move(source, target); else File.Move(source, target);
        }
    }
}
