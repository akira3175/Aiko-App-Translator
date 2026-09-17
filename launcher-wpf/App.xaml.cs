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
            AppContext.SetSwitch("Switch.System.IO.UseLegacyPathHandling", false);
            AppContext.SetSwitch("Switch.System.IO.BlockLongPaths", false);
            SetProcessDPIAware();
            base.OnStartup(e);
            if (e.Args.Contains("--self-test")) Environment.Exit(LauncherController.SelfTest());
            bool created;
            mutex = new Mutex(true, "AikoUnifiedLauncher", out created);
            if (!created) { Shutdown(); return; }
            string requested = e.Args.FirstOrDefault(x => x.StartsWith("--install-root=", StringComparison.OrdinalIgnoreCase));
            requested = requested == null ? "" : requested.Substring("--install-root=".Length).Trim('"');
            if (requested == "" && File.Exists(Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "app.py"))) requested = AppDomain.CurrentDomain.BaseDirectory;
            MainWindow = new MainWindow(requested);
            MainWindow.Show();
        }

    }
}
