using System;
using System.IO;
using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Interop;
using System.Windows.Media.Animation;

namespace AikoLauncher
{
    public partial class MainWindow : Window
    {
        private readonly LauncherController controller;
        private string renderedNotes;
        private bool wasChecking;
        private bool wasBusy;
        private string progressMode;

        public MainWindow(string requestedRoot)
        {
            InitializeComponent();
            BannerImage.Source = LauncherArtwork.ReadCache(LauncherArtwork.CachePath("aiko-launcher-background.png")) ?? BannerImage.Source;
            LogoImage.Source = LauncherArtwork.ReadCache(LauncherArtwork.CachePath("aiko-blue-logo.png")) ?? LogoImage.Source;
            NotesCard.LayoutUpdated += (s, e) => UpdateNotesGlass();
            controller = new LauncherController(requestedRoot);
            controller.Changed += state => Dispatcher.BeginInvoke(new Action(() => Render(state)));
            SizeChanged += (s, e) => ApplyWindowClip();
            ProgressTrack.SizeChanged += (s, e) => UpdateProgress(controller.State, true);
            Render(controller.State);
            Loaded += async (s, e) => { ApplyWindowClip(); await controller.CheckAsync(); };
            Loaded += async (s, e) => await System.Threading.Tasks.Task.WhenAll(
                LauncherArtwork.RefreshCacheAsync("aiko-launcher-background.png"),
                LauncherArtwork.RefreshCacheAsync("aiko-blue-logo.png"));
            Closing += (s, e) =>
            {
                if (!controller.State.Busy || controller.State.Checking) return;
                e.Cancel = true;
                if (controller.State.CanCancel) controller.CancelDownload();
            };
        }

        private void UpdateNotesGlass()
        {
            if (NotesCard.ActualWidth <= 0 || NotesSlot.ActualHeight <= 0) return;
            var origin = NotesCard.TranslatePoint(new Point(-24, -24), BannerSurface);
            var area = new Rect(origin.X, origin.Y, NotesCard.ActualWidth + 48, NotesCard.ActualHeight + 48);
            if (NotesBackdrop.Viewbox != area) NotesBackdrop.Viewbox = area;
            var bounds = new Rect(0, 0, NotesCard.ActualWidth, NotesCard.ActualHeight);
            var clip = NotesCard.Clip as System.Windows.Media.RectangleGeometry;
            if (clip == null || clip.Rect != bounds)
                NotesCard.Clip = new System.Windows.Media.RectangleGeometry(bounds, 12, 12);
        }

        private void ApplyWindowClip()
        {
            if (ActualWidth <= 0 || ActualHeight <= 0) return;
            Clip = new System.Windows.Media.RectangleGeometry(new Rect(0, 0, ActualWidth, ActualHeight), 3, 3);
        }

        private void Render(LauncherState state)
        {
            VersionText.Text = state.Installed ? "Phiên bản " + state.InstalledVersion : "AIKO";
            HeadlineText.Text = "Một nơi cho mọi bản dịch";
            SummaryText.Text = state.Installed ? "Aiko đã sẵn sàng. Tiếp tục dự án gần nhất hoặc kiểm tra công cụ server." : "Tải và cài Aiko để bắt đầu dịch truyện.";
            if (!state.Checking && (NotesView.Document == null || !string.Equals(renderedNotes, state.Notes, StringComparison.Ordinal)))
            {
                NotesView.Document = ReleaseNotesMarkdown.Render(state.Notes);
                var first = NotesView.Document.Blocks.FirstBlock as System.Windows.Documents.Paragraph;
                if (first != null && new System.Windows.Documents.TextRange(first.ContentStart, first.ContentEnd).Text.Trim().TrimEnd('?') == "Có gì mới")
                {
                    first.FontSize = 16;
                    first.Margin = new Thickness(0, 0, 0, 4);
                }
                var last = NotesView.Document.Blocks.LastBlock;
                if (last != null) last.Margin = new Thickness(last.Margin.Left, last.Margin.Top, last.Margin.Right, 0);
                renderedNotes = state.Notes;
            }
            NotesLoading.Visibility = state.Checking ? Visibility.Visible : Visibility.Collapsed;
            NotesView.Visibility = state.Checking ? Visibility.Hidden : Visibility.Visible;
            if (state.Checking != wasChecking)
            {
                for (int i = 0; i < LoadingDots.Children.Count; i++)
                {
                    var dot = (System.Windows.Shapes.Ellipse)LoadingDots.Children[i];
                    dot.BeginAnimation(OpacityProperty, state.Checking && SystemParameters.ClientAreaAnimation
                        ? new DoubleAnimation(0.25, 1, TimeSpan.FromMilliseconds(550)) { BeginTime = TimeSpan.FromMilliseconds(i * 160), AutoReverse = true, RepeatBehavior = RepeatBehavior.Forever }
                        : null);
                }
                if (!state.Checking && SystemParameters.ClientAreaAnimation)
                    NotesView.BeginAnimation(OpacityProperty, new DoubleAnimation(0, 1, TimeSpan.FromMilliseconds(180)));
            }
            wasChecking = state.Checking;
            StatusText.Text = state.Status;
            PathText.Text = state.InstallRoot;
            PrimaryButton.Content = state.Checking ? "ĐANG KIỂM TRA…" : state.CanCancel ? "HỦY TẢI" : state.Busy ? "VUI LÒNG CHỜ…" : !state.Installed ? "TẢI VÀ CÀI AIKO" : state.UpdateAvailable ? "CẬP NHẬT AIKO" : "MỞ AIKO";
            PrimaryButton.IsEnabled = !state.Busy || state.CanCancel;
            ToolsButton.IsEnabled = !state.Busy;
            UpdateProgress(state, false);
        }

        private void UpdateProgress(LauncherState state, bool resized)
        {
            StatusDot.Fill = new System.Windows.Media.SolidColorBrush((System.Windows.Media.Color)System.Windows.Media.ColorConverter.ConvertFromString(
                state.HasError ? "#FF9F9F" : state.Busy ? "#72C7FF" : state.UpdateAvailable ? "#F5CD78" : state.Installed ? "#80D9AF" : "#A9C5E1"));
            string mode = state.Busy ? (state.Progress < 0 ? "working" : "download")
                : !state.HasError && (state.Progress >= 1 || wasBusy && state.Progress < 0) ? "complete" : "idle";
            if (!state.Busy && !wasBusy && progressMode == "complete" && !state.HasError && state.Progress != 0) mode = "complete";
            wasBusy = state.Busy;
            bool changed = mode != progressMode;
            if (!changed && !resized && mode != "download") return;
            progressMode = mode;
            if (changed)
            {
                ProgressTrack.BeginAnimation(OpacityProperty, null);
                ProgressTrack.Opacity = 1;
                ProgressMotion.BeginAnimation(System.Windows.Media.TranslateTransform.XProperty, null);
                ProgressMotion.X = 0;
            }
            ProgressTrack.Visibility = mode == "idle" ? Visibility.Hidden : Visibility.Visible;
            double width = ProgressTrack.ActualWidth;
            ProgressFill.Width = mode == "working" ? width * 0.28 : mode == "complete" ? width : width * Math.Max(0, Math.Min(1, state.Progress));
            if (mode == "working" && (changed || resized))
            {
                if (SystemParameters.ClientAreaAnimation)
                    ProgressMotion.BeginAnimation(System.Windows.Media.TranslateTransform.XProperty,
                        new DoubleAnimation(-ProgressFill.Width, width, TimeSpan.FromSeconds(1.35)) { RepeatBehavior = RepeatBehavior.Forever });
                else ProgressMotion.X = width * 0.36;
            }
            if (mode == "complete" && changed)
            {
                var fade = new DoubleAnimation(1, 0, TimeSpan.FromMilliseconds(SystemParameters.ClientAreaAnimation ? 180 : 1))
                    { BeginTime = TimeSpan.FromMilliseconds(500) };
                fade.Completed += (s, e) => { if (progressMode == "complete") ProgressTrack.Visibility = Visibility.Hidden; };
                ProgressTrack.BeginAnimation(OpacityProperty, fade);
            }
        }

        private async void PrimaryAction(object sender, RoutedEventArgs e) { if (controller.State.CanCancel) { controller.CancelDownload(); return; } await controller.PrimaryAsync(); }
        private void DragWindow(object sender, MouseButtonEventArgs e) { if (e.LeftButton == MouseButtonState.Pressed) DragMove(); }
        private void MinimizeWindow(object sender, RoutedEventArgs e) { WindowState = WindowState.Minimized; }
        private void CloseWindow(object sender, RoutedEventArgs e) { Close(); }

        private void OpenTools(object sender, RoutedEventArgs e)
        {
            if (controller.State.Busy) return;
            var menu = new ContextMenu
            {
                PlacementTarget = ToolsButton,
                Placement = System.Windows.Controls.Primitives.PlacementMode.Top,
                HorizontalOffset = -150,
                VerticalOffset = -4
            };
            AddItem(menu, "Chọn thư mục Aiko hiện có", SelectExisting);
            AddItem(menu, "Chọn thư mục trống để cài mới", SelectDestination);
            AddItem(menu, "Kiểm tra bản cập nhật", async () => await controller.CheckAsync());
            if (controller.State.Installed) AddItem(menu, "Mở ứng dụng hiện tại", async () => await controller.OpenAsync());
            AddItem(menu, "Khởi động lại server", async () => await controller.RestartAsync());
            AddItem(menu, "Dừng server", async () => await controller.StopServerAsync());
            AddItem(menu, "Tạo shortcut Desktop", controller.CreateShortcut);
            menu.IsOpen = true;
        }

        private static void AddItem(ContextMenu menu, string text, Action action)
        {
            var item = new MenuItem { Header = text, Padding = new Thickness(12, 8, 22, 8) };
            item.Click += (s, e) => action();
            menu.Items.Add(item);
        }

        private void SelectExisting()
        {
            string selected = NativeFolderPicker.Show(new WindowInteropHelper(this).Handle);
            if (string.IsNullOrWhiteSpace(selected)) return;
            try { controller.UseExisting(selected); }
            catch (Exception error) { MessageBox.Show(this, error.Message, "Aiko Launcher", MessageBoxButton.OK, MessageBoxImage.Warning); }
        }

        private void SelectDestination()
        {
            string selected = NativeFolderPicker.Show(new WindowInteropHelper(this).Handle);
            if (string.IsNullOrWhiteSpace(selected)) return;
            try { controller.UseDestination(selected); }
            catch (Exception error) { MessageBox.Show(this, error.Message, "Aiko Launcher", MessageBoxButton.OK, MessageBoxImage.Warning); }
        }
    }

    internal static class NativeFolderPicker
    {
        private const uint Options = 0x20 | 0x40 | 0x800;
        private const uint FileSystemPath = 0x80058000;
        private const int Cancelled = unchecked((int)0x800704C7);
        [ComImport, Guid("DC1C5A9C-E88A-4DDE-A5A1-60F82A20AEF7")] private class FileOpenDialog { }
        [ComImport, InterfaceType(ComInterfaceType.InterfaceIsIUnknown), Guid("43826D1E-E718-42EE-BC55-A1E261C37BFE")]
        private interface IShellItem { void BindToHandler(IntPtr a, ref Guid b, ref Guid c, out IntPtr d); void GetParent(out IShellItem p); void GetDisplayName(uint n, out IntPtr v); void GetAttributes(uint m, out uint a); void Compare(IShellItem o, uint h, out int r); }
        [ComImport, InterfaceType(ComInterfaceType.InterfaceIsIUnknown), Guid("42F85136-DB7E-439C-85F1-E4075D135FC8")]
        private interface IFileDialog
        {
            [PreserveSig] int Show(IntPtr owner); void SetFileTypes(uint c, IntPtr f); void SetFileTypeIndex(uint i); void GetFileTypeIndex(out uint i); void Advise(IntPtr e, out uint c); void Unadvise(uint c); void SetOptions(uint o); void GetOptions(out uint o); void SetDefaultFolder(IShellItem f); void SetFolder(IShellItem f); void GetFolder(out IShellItem f); void GetCurrentSelection(out IShellItem i); void SetFileName([MarshalAs(UnmanagedType.LPWStr)] string n); void GetFileName([MarshalAs(UnmanagedType.LPWStr)] out string n); void SetTitle([MarshalAs(UnmanagedType.LPWStr)] string t); void SetOkButtonLabel([MarshalAs(UnmanagedType.LPWStr)] string t); void SetFileNameLabel([MarshalAs(UnmanagedType.LPWStr)] string l); void GetResult(out IShellItem i); void AddPlace(IShellItem i, int a); void SetDefaultExtension([MarshalAs(UnmanagedType.LPWStr)] string e); void Close(int e); void SetClientGuid(ref Guid g); void ClearClientData(); void SetFilter(IntPtr f);
        }
        internal static string Show(IntPtr owner)
        {
            IFileDialog dialog = (IFileDialog)new FileOpenDialog();
            try
            {
                dialog.SetOptions(Options); dialog.SetTitle("Chọn thư mục Aiko portable"); dialog.SetOkButtonLabel("Chọn thư mục"); int result = dialog.Show(owner); if (result == Cancelled) return null; Marshal.ThrowExceptionForHR(result);
                IShellItem item; dialog.GetResult(out item); try { IntPtr value; item.GetDisplayName(FileSystemPath, out value); try { return Marshal.PtrToStringUni(value); } finally { Marshal.FreeCoTaskMem(value); } } finally { Marshal.ReleaseComObject(item); }
            }
            finally { Marshal.ReleaseComObject(dialog); }
        }
    }
}
