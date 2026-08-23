using System;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Threading;
using System.Windows;

namespace AikoLauncher
{
    public partial class App : Application
    {
        private Mutex mutex;
        [DllImport("user32.dll")] private static extern bool SetProcessDPIAware();

        protected override void OnStartup(StartupEventArgs e)
        {
            SetProcessDPIAware();
            base.OnStartup(e);
            if (e.Args.Contains("--self-test")) Environment.Exit(LauncherController.SelfTest());
            if (!e.Args.Contains("--no-self-install") && !EnsureStable(e.Args)) { Shutdown(); return; }
            bool created;
            mutex = new Mutex(true, "AikoUnifiedLauncher", out created);
            if (!created) { Shutdown(); return; }
            string requested = e.Args.FirstOrDefault(x => x.StartsWith("--install-root=", StringComparison.OrdinalIgnoreCase));
            requested = requested == null ? "" : requested.Substring("--install-root=".Length).Trim('"');
            MainWindow = new MainWindow(requested);
            MainWindow.Show();
        }

        private static string StablePath() => Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Aiko Launcher", "Aiko-Launcher.exe");

        private static bool EnsureStable(string[] args)
        {
            string current = Path.GetFullPath(Process.GetCurrentProcess().MainModule.FileName);
            string stable = StablePath();
            if (string.Equals(current, stable, StringComparison.OrdinalIgnoreCase)) return true;
            Directory.CreateDirectory(Path.GetDirectoryName(stable));
            string temporary = stable + ".new";
            File.Copy(current, temporary, true);
            if (File.Exists(stable)) File.Replace(temporary, stable, null); else File.Move(temporary, stable);
            Process.Start(new ProcessStartInfo(stable, string.Join(" ", args.Select(x => "\"" + x.Replace("\"", "\\\"") + "\""))) { WorkingDirectory = Path.GetDirectoryName(stable), UseShellExecute = false });
            return false;
        }
    }
}
