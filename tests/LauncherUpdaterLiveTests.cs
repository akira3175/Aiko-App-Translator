// Opt-in integration test. Run through test_launcher_updater.ps1 -Live.
// Only the test copy of the controller/app uses port 18765.
using System;
using System.IO;
using System.Reflection;
using System.Threading;
using AikoLauncher;

internal static class LauncherUpdaterLiveTests
{
    private static void Invoke(LauncherController controller, string method, params object[] args)
    { typeof(LauncherController).GetMethod(method, BindingFlags.NonPublic | BindingFlags.Instance).Invoke(controller, args); }
    public static int Main(string[] args)
    {
        AppContext.SetSwitch("Switch.System.IO.UseLegacyPathHandling", false);
        AppContext.SetSwitch("Switch.System.IO.BlockLongPaths", false);
        string root = Path.GetFullPath(args[0]);
        Directory.CreateDirectory(root);
        // Never use the real browser profile or launcher preferences in the test.
        Environment.SetEnvironmentVariable("LOCALAPPDATA", Path.Combine(root, "local"));
        LauncherController controller = null;
        try
        {
            System.Net.ServicePointManager.SecurityProtocol = System.Net.SecurityProtocolType.Tls12;
            var release = PortableUpdater.Check();
            Console.WriteLine("GitHub release: " + release.Version + " / " + release.Size + " bytes / " + release.Sha256);
            int last = -1;
            string existingZip = Path.Combine(root, "download", "download.zip");
            string payload;
            if (File.Exists(existingZip))
            {
                PortableUpdater.VerifyHash(existingZip, release.Sha256);
                payload = PortableUpdater.Extract(existingZip, Path.Combine(root, "retry-" + Guid.NewGuid().ToString("N")), release.Version, CancellationToken.None);
            }
            else payload = PortableUpdater.DownloadAndExtract(release, Path.Combine(root, "download"), CancellationToken.None,
                (status, value) => { int step = (int)(value * 10); if (step != last) { Console.WriteLine(status); last = step; } });
            Console.WriteLine("PASS real download, SHA-256 and extraction");
            string appFile = Path.Combine(payload, "app.py");
            string appCode = File.ReadAllText(appFile);
            if (!appCode.Contains("PORT = 8765")) throw new Exception("Cannot isolate server port");
            File.WriteAllText(appFile, appCode.Replace("PORT = 8765", "PORT = 18765"));
            string app = Path.Combine(root, "installed");
            // Construct against the valid staging root, then point at the test destination.
            controller = new LauncherController(payload);
            typeof(LauncherController).GetField("installRoot", BindingFlags.NonPublic | BindingFlags.Instance).SetValue(controller, app);
            PortableUpdater.Install(payload, app, Path.Combine(root, "fresh-backup"), () => Invoke(controller, "StartUpdatedServer", release.Version), () => Invoke(controller, "StopUpdatedServer"));
            Console.WriteLine("PASS fresh install, real Python startup, version and TCP owner check");
            Invoke(controller, "StopUpdatedServer");
            string data = Path.Combine(app, "data", "launcher-test.txt");
            File.WriteAllText(data, "keep me");
            // Reuse the verified installed payload for a real file replacement transaction.
            string second = Path.Combine(root, "second-payload");
            Directory.CreateDirectory(second);
            File.Copy(Path.Combine(app, "app.py"), Path.Combine(second, "app.py"));
            File.Copy(Path.Combine(app, "VERSION"), Path.Combine(second, "VERSION"));
            File.WriteAllText(Path.Combine(app, "VERSION"), "0.0.0");
            PortableUpdater.Install(second, app, Path.Combine(root, "update-backup"), () => Invoke(controller, "StartUpdatedServer", release.Version), () => Invoke(controller, "StopUpdatedServer"));
            if (File.ReadAllText(data) != "keep me") throw new Exception("Data changed");
            Console.WriteLine("PASS update, real Python restart and preserved user data");
            Invoke(controller, "StopUpdatedServer");
            string broken = Path.Combine(root, "broken-payload"); Directory.CreateDirectory(broken);
            File.WriteAllText(Path.Combine(broken, "app.py"), "raise RuntimeError('intentional startup failure')");
            bool rolledBack = false;
            try { PortableUpdater.Install(broken, app, Path.Combine(root, "failed-backup"), () => Invoke(controller, "StartUpdatedServer", release.Version), () => Invoke(controller, "StopUpdatedServer")); }
            catch (IOException) { rolledBack = true; }
            if (!rolledBack) throw new Exception("Broken startup did not roll back");
            Invoke(controller, "StartUpdatedServer", release.Version);
            Console.WriteLine("PASS real failed startup, rollback and recovered server startup");
            return 0;
        }
        catch (Exception error) { Console.Error.WriteLine(error); return 1; }
        finally { if (controller != null) Invoke(controller, "StopUpdatedServer"); }
    }
}
