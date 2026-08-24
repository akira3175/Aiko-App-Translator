using System;
using System.Diagnostics;
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
            bool created;
            mutex = new Mutex(true, "AikoUnifiedLauncher", out created);
            if (!created) { Shutdown(); return; }
            string requested = e.Args.FirstOrDefault(x => x.StartsWith("--install-root=", StringComparison.OrdinalIgnoreCase));
            requested = requested == null ? "" : requested.Substring("--install-root=".Length).Trim('"');
            MainWindow = new MainWindow(requested);
            MainWindow.Show();
        }

    }
}
