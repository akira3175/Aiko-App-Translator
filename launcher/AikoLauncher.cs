using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Management;
using System.Net;
using System.Reflection;
using System.Threading;
using System.Windows.Forms;

internal sealed class AikoLauncher : ApplicationContext
{
    private const string AppUrl = "http://127.0.0.1:8765";
    private readonly string root;
    private readonly NotifyIcon tray;
    private readonly Form optionsWindow;
    private readonly RegisteredWaitHandle showRequestRegistration;
    private Label serverStatus;
    private Process server;

    private AikoLauncher(EventWaitHandle showRequest, bool optionsOnly)
    {
        root = AppDomain.CurrentDomain.BaseDirectory;
        tray = new NotifyIcon();
        tray.Text = "Aiko App Translator";
        tray.Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath);
        tray.Visible = true;
        tray.DoubleClick += delegate { OpenApp(); };

        ContextMenuStrip menu = new ContextMenuStrip();
        menu.Items.Add("Mở Aiko", null, delegate { OpenApp(); });
        menu.Items.Add("Khởi động lại", null, delegate { RestartApp(); });
        menu.Items.Add(new ToolStripSeparator());
        menu.Items.Add("Tạo shortcut Desktop", null, delegate { CreateShortcut(false, true); });
        menu.Items.Add("Tạo shortcut Start Menu", null, delegate { CreateShortcut(true, true); });
        menu.Items.Add(new ToolStripSeparator());
        menu.Items.Add("Tắt server", null, delegate { StopServerAndExit(); });
        tray.ContextMenuStrip = menu;

        optionsWindow = CreateOptionsWindow();
        showRequestRegistration = ThreadPool.RegisterWaitForSingleObject(showRequest, delegate(object state, bool timedOut)
        {
            if (!optionsWindow.IsDisposed) optionsWindow.BeginInvoke((MethodInvoker)ShowOptions);
        }, null, Timeout.Infinite, false);

        if (!optionsOnly) StartOrOpen();
        AskForDesktopShortcutOnce();
        ShowOptions();
    }

    private Form CreateOptionsWindow()
    {
        Form form = new Form();
        form.Text = "Aiko App Translator";
        form.Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath);
        form.StartPosition = FormStartPosition.CenterScreen;
        form.FormBorderStyle = FormBorderStyle.FixedDialog;
        form.MaximizeBox = false;
        form.MinimizeBox = false;
        form.BackColor = Color.FromArgb(246, 248, 252);
        form.Font = new Font("Segoe UI", 9F);
        form.ClientSize = new Size(440, 388);

        Panel header = new Panel();
        header.BackColor = Color.White;
        header.Location = new Point(0, 0);
        header.Size = new Size(440, 104);
        form.Controls.Add(header);

        PictureBox logo = new PictureBox();
        logo.Image = LoadBrandImage();
        logo.SizeMode = PictureBoxSizeMode.Zoom;
        logo.Location = new Point(24, 22);
        logo.Size = new Size(58, 58);
        header.Controls.Add(logo);

        Label title = new Label();
        title.Text = "Aiko App Translator";
        title.Font = new Font("Segoe UI", 16F, FontStyle.Bold);
        title.AutoSize = true;
        title.ForeColor = Color.FromArgb(24, 36, 64);
        title.Location = new Point(96, 22);
        header.Controls.Add(title);

        serverStatus = new Label();
        serverStatus.AutoSize = true;
        serverStatus.Font = new Font("Segoe UI", 9F, FontStyle.Bold);
        serverStatus.Location = new Point(99, 59);
        header.Controls.Add(serverStatus);

        Label sectionTitle = new Label();
        sectionTitle.Text = "ĐIỀU KHIỂN SERVER";
        sectionTitle.AutoSize = true;
        sectionTitle.Font = new Font("Segoe UI", 8F, FontStyle.Bold);
        sectionTitle.ForeColor = Color.FromArgb(91, 105, 135);
        sectionTitle.Location = new Point(24, 126);
        form.Controls.Add(sectionTitle);

        AddButton(form, "Mở Aiko", 24, 150, 190, true, delegate { OpenApp(); });
        AddButton(form, "Khởi động lại", 226, 150, 190, false, delegate { RestartApp(); });

        Label shortcutTitle = new Label();
        shortcutTitle.Text = "LỐI TẮT";
        shortcutTitle.AutoSize = true;
        shortcutTitle.Font = new Font("Segoe UI", 8F, FontStyle.Bold);
        shortcutTitle.ForeColor = Color.FromArgb(91, 105, 135);
        shortcutTitle.Location = new Point(24, 218);
        form.Controls.Add(shortcutTitle);

        AddButton(form, "Tạo shortcut Desktop", 24, 242, 190, false, delegate { CreateShortcut(false, true); });
        AddButton(form, "Tạo shortcut Start Menu", 226, 242, 190, false, delegate { CreateShortcut(true, true); });

        Label hint = new Label();
        hint.Text = "Đóng cửa sổ này chỉ ẩn bảng điều khiển; server vẫn tiếp tục chạy.";
        hint.AutoSize = true;
        hint.ForeColor = Color.FromArgb(91, 105, 135);
        hint.Location = new Point(25, 304);
        form.Controls.Add(hint);

        AddButton(form, "Ẩn bảng điều khiển", 24, 330, 190, false, delegate { form.Hide(); });
        AddButton(form, "Tắt server", 226, 330, 190, false, delegate { StopServerAndExit(); });
        form.FormClosing += delegate(object sender, FormClosingEventArgs args)
        {
            if (args.CloseReason == CloseReason.ApplicationExitCall) return;
            args.Cancel = true;
            form.Hide();
        };
        return form;
    }

    private static Image LoadBrandImage()
    {
        Stream stream = Assembly.GetExecutingAssembly().GetManifestResourceStream("AikoBlueLogo.png");
        if (stream == null) return Icon.ExtractAssociatedIcon(Application.ExecutablePath).ToBitmap();
        using (stream)
        using (Image image = Image.FromStream(stream))
            return new Bitmap(image);
    }

    private static void AddButton(Form form, string text, int left, int top, int width, bool primary, Action action)
    {
        Button button = new Button();
        button.Text = text;
        button.Size = new Size(width, 42);
        button.Location = new Point(left, top);
        button.FlatStyle = FlatStyle.Flat;
        button.FlatAppearance.BorderSize = primary ? 0 : 1;
        button.FlatAppearance.BorderColor = Color.FromArgb(207, 216, 235);
        button.BackColor = primary ? Color.FromArgb(38, 92, 214) : Color.White;
        button.ForeColor = primary ? Color.White : Color.FromArgb(37, 50, 79);
        button.Font = new Font("Segoe UI", 9F, FontStyle.Bold);
        button.Cursor = Cursors.Hand;
        button.Click += delegate { action(); };
        form.Controls.Add(button);
    }

    private void ShowOptions()
    {
        bool healthy = IsHealthy();
        serverStatus.Text = healthy ? "● Server đang chạy" : "● Server đang tắt";
        serverStatus.ForeColor = healthy ? Color.FromArgb(27, 142, 85) : Color.FromArgb(188, 67, 62);
        optionsWindow.Show();
        optionsWindow.WindowState = FormWindowState.Normal;
        optionsWindow.Activate();
        optionsWindow.BringToFront();
    }

    private bool IsHealthy()
    {
        try
        {
            HttpWebRequest request = (HttpWebRequest)WebRequest.Create(AppUrl + "/api/health");
            request.Timeout = 800;
            using (HttpWebResponse response = (HttpWebResponse)request.GetResponse())
                return response.StatusCode == HttpStatusCode.OK;
        }
        catch { return false; }
    }

    private void StartOrOpen()
    {
        if (!IsHealthy() && !StartServer()) return;
        OpenApp();
    }

    private bool StartServer()
    {
        string python = Path.Combine(root, "runtime", "python.exe");
        string app = Path.Combine(root, "app.py");
        if (!System.IO.File.Exists(app))
        {
            MessageBox.Show("Không tìm thấy app.py. Hãy đặt launcher trong đúng thư mục Aiko App Translator.", "Không thể mở Aiko", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return false;
        }
        if (!System.IO.File.Exists(python)) python = "python.exe";
        ProcessStartInfo info = new ProcessStartInfo(python, "\"" + app + "\"");
        info.WorkingDirectory = root;
        info.UseShellExecute = false;
        info.CreateNoWindow = true;
        info.WindowStyle = ProcessWindowStyle.Hidden;
        info.EnvironmentVariables["PYTHONUTF8"] = "1";
        info.EnvironmentVariables["AIKO_NO_BROWSER"] = "1";
        server = Process.Start(info);
        for (int i = 0; i < 40; i++)
        {
            Thread.Sleep(250);
            if (IsHealthy()) return true;
            if (server.HasExited) break;
            Application.DoEvents();
        }
        MessageBox.Show("Server Aiko không khởi động được. Hãy chạy start_app.bat để xem thông báo lỗi chi tiết.", "Không thể mở Aiko", MessageBoxButtons.OK, MessageBoxIcon.Error);
        return false;
    }

    private void OpenApp()
    {
        if (!IsHealthy())
        {
            StartOrOpen();
            return;
        }
        Process.Start(new ProcessStartInfo(AppUrl) { UseShellExecute = true });
    }

    private void RestartApp()
    {
        StopAppServers();
        Thread.Sleep(500);
        if (StartServer()) OpenApp();
    }

    private void StopAppServers()
    {
        if (server != null && !server.HasExited)
        {
            try { server.Kill(); server.WaitForExit(3000); } catch { }
        }
        try
        {
            using (ManagementObjectSearcher searcher = new ManagementObjectSearcher("SELECT ProcessId, CommandLine FROM Win32_Process WHERE Name = 'python.exe'"))
            foreach (ManagementObject item in searcher.Get())
            {
                string command = Convert.ToString(item["CommandLine"]);
                if (command.IndexOf(Path.Combine(root, "app.py"), StringComparison.OrdinalIgnoreCase) < 0) continue;
                try { Process.GetProcessById(Convert.ToInt32(item["ProcessId"])).Kill(); } catch { }
            }
        }
        catch { }
    }

    private void AskForDesktopShortcutOnce()
    {
        string runtime = Path.Combine(root, ".runtime");
        string marker = Path.Combine(runtime, "launcher-shortcut-prompted");
        if (System.IO.File.Exists(marker)) return;
        Directory.CreateDirectory(runtime);
        DialogResult answer = MessageBox.Show("Bạn có muốn tạo lối tắt Aiko App Translator trên Desktop không?\n\nNếu chọn Không, bạn vẫn có thể tạo sau trong bảng điều khiển launcher.", "Tạo lối tắt Aiko", MessageBoxButtons.YesNo, MessageBoxIcon.Question);
        System.IO.File.WriteAllText(marker, "1");
        if (answer == DialogResult.Yes) CreateShortcut(false, false);
    }

    private void CreateShortcut(bool startMenu, bool notify)
    {
        try
        {
            string folder = Environment.GetFolderPath(startMenu ? Environment.SpecialFolder.Programs : Environment.SpecialFolder.DesktopDirectory);
            string path = Path.Combine(folder, "Aiko App Translator.lnk");
            Type shellType = Type.GetTypeFromProgID("WScript.Shell");
            dynamic shell = Activator.CreateInstance(shellType);
            dynamic shortcut = shell.CreateShortcut(path);
            shortcut.TargetPath = Application.ExecutablePath;
            shortcut.WorkingDirectory = root;
            shortcut.IconLocation = Application.ExecutablePath + ",0";
            shortcut.Description = "Mở Aiko App Translator";
            shortcut.Save();
            if (notify) tray.ShowBalloonTip(2500, "Aiko App Translator", "Đã tạo shortcut.", ToolTipIcon.Info);
        }
        catch (Exception error)
        {
            MessageBox.Show("Không tạo được shortcut: " + error.Message, "Aiko App Translator", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }

    private void StopServerAndExit()
    {
        StopAppServers();
        showRequestRegistration.Unregister(null);
        tray.Visible = false;
        tray.Dispose();
        ExitThread();
    }

    [STAThread]
    private static void Main()
    {
        bool optionsOnly = Array.Exists(Environment.GetCommandLineArgs(), delegate(string value) { return value == "--options-only"; });
        bool created;
        using (Mutex mutex = new Mutex(true, "AikoAppTranslatorLauncher", out created))
        using (EventWaitHandle showRequest = new EventWaitHandle(false, EventResetMode.AutoReset, "AikoAppTranslatorShowOptions"))
        {
            if (!created)
            {
                showRequest.Set();
                return;
            }
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new AikoLauncher(showRequest, optionsOnly));
        }
    }
}
