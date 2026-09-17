using System;
using System.IO;
using System.IO.Compression;
using System.Text;
using System.Threading;
using AikoLauncher;

internal static class LauncherUpdaterTests
{
    private static int passed;
    private static void Assert(bool value, string message) { if (!value) throw new Exception(message); }
    private static void Reject(Action action) { bool failed = false; try { action(); } catch (Exception) { failed = true; } Assert(failed, "Expected failure"); }
    private static void Write(string root, string name, string text)
    { string path = Path.Combine(root, name); Directory.CreateDirectory(Path.GetDirectoryName(path)); File.WriteAllText(path, text); }
    private static void Test(string name, Action<string> action)
    {
        string root = Path.Combine(Path.GetTempPath(), "aiko-updater-tests-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        try { action(root); passed++; Console.WriteLine("PASS " + name); }
        finally { Directory.Delete(@"\\?\" + root, true); }
    }
    private static string Archive(string root, string extra = null, string version = "1.2.3")
    {
        string zip = Path.Combine(root, Guid.NewGuid().ToString("N") + ".zip");
        using (var archive = ZipFile.Open(zip, ZipArchiveMode.Create))
        {
            foreach (string name in new[] { "VERSION", "app.py", "runtime/python.exe" })
                using (var writer = new StreamWriter(archive.CreateEntry("NovelTranslatorStudio/" + name).Open())) writer.Write(name == "VERSION" ? version : "fixture");
            if (extra != null) using (var writer = new StreamWriter(archive.CreateEntry(extra).Open())) writer.Write("bad");
        }
        return zip;
    }
    public static int Main(string[] args)
    {
        AppContext.SetSwitch("Switch.System.IO.UseLegacyPathHandling", false);
        AppContext.SetSwitch("Switch.System.IO.BlockLongPaths", false);
        try
        {
            Test("version ordering", root => { Assert(PortableUpdater.ParseVersion("v1.10.0") > PortableUpdater.ParseVersion("1.9.9"), "numeric ordering"); Reject(() => PortableUpdater.ParseVersion("../../1")); });
            string metadata = "{\"tag_name\":\"v1.2.3\",\"body\":\"release notes\",\"assets\":[{\"name\":\"NovelTranslatorStudio-Windows-x64.zip\",\"browser_download_url\":\"https://github.com/akira3175/Aiko-App-Translator/releases/download/v1.2.3/NovelTranslatorStudio-Windows-x64.zip\",\"digest\":\"sha256:" + new string('a', 64) + "\",\"size\":123}]}";
            Test("release metadata", root => { var release = PortableUpdater.ParseRelease(metadata); Assert(release.Version == "1.2.3" && release.Size == 123 && release.Sha256 == new string('a', 64), "incorrect release"); });
            Test("untrusted release URL blocked", root => Reject(() => PortableUpdater.ParseRelease(metadata.Replace("https://github.com/", "https://example.com/"))));
            Test("missing digest blocked", root => Reject(() => PortableUpdater.ParseRelease(metadata.Replace("sha256:" + new string('a', 64), ""))));
            Test("hash mismatch", root => Reject(() => PortableUpdater.VerifyHash(Archive(root), new string('0', 64))));
            Test("valid archive", root => Assert(File.Exists(Path.Combine(PortableUpdater.Extract(Archive(root), Path.Combine(root, "out"), "1.2.3", CancellationToken.None), "runtime", "python.exe")), "runtime missing"));
            Test("long runtime paths", root =>
            {
                string name = "NovelTranslatorStudio/" + new string('a', 100) + "/" + new string('b', 100) + "/file.txt";
                string result = PortableUpdater.Extract(Archive(root, name), Path.Combine(root, "out"), "1.2.3", CancellationToken.None);
                Assert(File.Exists(PortableUpdater.Child(result, Path.Combine(new string('a', 100), new string('b', 100), "file.txt"))), "long path missing");
            });
            Test("traversal blocked", root => { Reject(() => PortableUpdater.Extract(Archive(root, "NovelTranslatorStudio/../../escape.txt"), Path.Combine(root, "out"), "1.2.3", CancellationToken.None)); Assert(!File.Exists(Path.Combine(root, "escape.txt")), "escaped staging"); });
            Test("alternate data stream blocked", root => Reject(() => PortableUpdater.Extract(Archive(root, "NovelTranslatorStudio/app.py:payload"), Path.Combine(root, "out"), "1.2.3", CancellationToken.None)));
            Test("wrong version blocked", root => Reject(() => PortableUpdater.Extract(Archive(root), Path.Combine(root, "out"), "2.0.0", CancellationToken.None)));
            Test("cancel extraction", root => { var cancel = new CancellationTokenSource(); cancel.Cancel(); Reject(() => PortableUpdater.Extract(Archive(root), Path.Combine(root, "out"), "1.2.3", cancel.Token)); });
            Test("update preserves data and launcher", root =>
            {
                string app = Path.Combine(root, "app"), payload = Path.Combine(root, "payload"), backup = Path.Combine(root, "backup");
                foreach (string name in new[] { "app.py", "VERSION", "data/key.txt", "truyen/story.txt", "Aiko-Launcher.exe", "Assets/image.png", "up/config_md.json", "up/image_cache.json" }) { Write(app, name, "old"); Write(payload, name, "new"); }
                PortableUpdater.Install(payload, app, backup, () => Assert(File.ReadAllText(Path.Combine(app, "app.py")) == "new", "new app missing"), () => {});
                foreach (string name in new[] { "data/key.txt", "truyen/story.txt", "Aiko-Launcher.exe", "Assets/image.png", "up/config_md.json", "up/image_cache.json" }) Assert(File.ReadAllText(Path.Combine(app, name)) == "old", "modified " + name);
                Assert(File.ReadAllText(Path.Combine(backup, "app.py")) == "old", "backup missing");
                Assert(!File.Exists(Path.Combine(app, ".runtime", "launcher-update-pending.txt")), "journal left after success");
            });
            Test("failed startup rolls back", root =>
            {
                string app = Path.Combine(root, "app"), payload = Path.Combine(root, "payload");
                Write(app, "app.py", "old"); Write(payload, "app.py", "new"); Write(payload, "new.txt", "new"); bool stopped = false;
                Reject(() => PortableUpdater.Install(payload, app, Path.Combine(root, "backup"), () => { throw new Exception("startup failed"); }, () => stopped = true));
                Assert(stopped && File.ReadAllText(Path.Combine(app, "app.py")) == "old" && !File.Exists(Path.Combine(app, "new.txt")), "rollback failed");
            });
            Test("locked file rolls back", root =>
            {
                string app = Path.Combine(root, "app"), payload = Path.Combine(root, "payload");
                Write(app, "app.py", "old"); Write(payload, "app.py", "new");
                using (var locked = new FileStream(Path.Combine(app, "app.py"), FileMode.Open, FileAccess.Read, FileShare.None))
                    Reject(() => PortableUpdater.Install(payload, app, Path.Combine(root, "backup"), () => {}, () => {}));
                Assert(File.ReadAllText(Path.Combine(app, "app.py")) == "old", "locked app changed");
            });
            Test("fresh install retains bundled defaults", root =>
            {
                string app = Path.Combine(root, "app"), payload = Path.Combine(root, "payload");
                Write(payload, "app.py", "new"); Write(payload, "data/r19_words.txt", "defaults");
                PortableUpdater.Install(payload, app, Path.Combine(root, "backup"), () => {}, () => {});
                Assert(File.ReadAllText(Path.Combine(app, "data", "r19_words.txt")) == "defaults", "defaults missing");
            });
            Test("interrupted transaction blocks another update", root =>
            {
                string app = Path.Combine(root, "app"), payload = Path.Combine(root, "payload");
                Write(app, ".runtime/launcher-update-pending.txt", "previous backup"); Write(payload, "app.py", "new");
                Reject(() => PortableUpdater.Install(payload, app, Path.Combine(root, "backup"), () => {}, () => {}));
                Assert(!File.Exists(Path.Combine(app, "app.py")), "pending transaction changed");
            });
            Test("failed rollback retains journal and backup", root =>
            {
                string app = Path.Combine(root, "app"), payload = Path.Combine(root, "payload"), backup = Path.Combine(root, "backup");
                Write(app, "app.py", "old"); Write(payload, "app.py", "new");
                Reject(() => PortableUpdater.Install(payload, app, backup, () => { throw new Exception("startup failed"); }, () => { throw new Exception("process still locked"); }));
                Assert(File.Exists(Path.Combine(app, ".runtime", "launcher-update-pending.txt")) && File.ReadAllText(Path.Combine(backup, "app.py")) == "old", "recovery evidence lost");
            });
            Console.WriteLine("Passed " + passed + " updater tests."); return 0;
        }
        catch (Exception error) { Console.Error.WriteLine(error); return 1; }
    }
}
