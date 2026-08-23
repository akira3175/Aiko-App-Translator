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

        public MainWindow(string requestedRoot)
        {
            InitializeComponent();
            controller = new LauncherController(requestedRoot);
            controller.Changed += state => Dispatcher.BeginInvoke(new Action(() => Render(state)));
            SizeChanged += (s, e) => ApplyWindowClip();
            Loaded += async (s, e) => { ApplyWindowClip(); AnimateIn(); await controller.CheckAsync(); };
        }

        private void ApplyWindowClip()
        {
            if (ActualWidth <= 0 || ActualHeight <= 0) return;
            Clip = new System.Windows.Media.RectangleGeometry(new Rect(0, 0, ActualWidth, ActualHeight), 3, 3);
        }

        private void Render(LauncherState state)
        {
            VersionText.Text = state.Installed ? "AIKO " + state.InstalledVersion + (state.UpdateAvailable ? "  ·  CÓ BẢN " + state.LatestVersion : "  ·  MỚI NHẤT") : "BẢN MỚI NHẤT  " + (state.LatestVersion ?? "");
            HeadlineText.Text = state.Headline;
            SummaryText.Text = state.Summary;
            NotesText.Text = state.Notes;
            StatusText.Text = state.Status;
            PathText.Text = state.InstallRoot;
            PrimaryButton.Content = state.Busy ? "VUI LÒNG CHỜ…" : !state.Installed ? "CÀI ĐẶT AIKO" : state.UpdateAvailable ? "CẬP NHẬT NGAY" : "MỞ AIKO";
            PrimaryButton.IsEnabled = !state.Busy;
            double available = Math.Max(0, ActualWidth - 420 - 72 - 260 - 24);
            ProgressFill.Width = available * Math.Max(0, Math.Min(1, state.Progress));
        }

        private void AnimateIn()
        {
            var fade = new DoubleAnimation(0, 1, TimeSpan.FromMilliseconds(420)) { EasingFunction = new CubicEase { EasingMode = EasingMode.EaseOut } };
            var slide = new ThicknessAnimation(new Thickness(36, 52, 42, 2), new Thickness(36, 34, 42, 20), TimeSpan.FromMilliseconds(480)) { EasingFunction = new CubicEase { EasingMode = EasingMode.EaseOut } };
            ContentPanel.BeginAnimation(OpacityProperty, fade);
            ContentPanel.BeginAnimation(MarginProperty, slide);
        }

        private async void PrimaryAction(object sender, RoutedEventArgs e) { await controller.PrimaryAsync(); }
        private void DragWindow(object sender, MouseButtonEventArgs e) { if (e.LeftButton == MouseButtonState.Pressed) DragMove(); }
        private void MinimizeWindow(object sender, RoutedEventArgs e) { WindowState = WindowState.Minimized; }
        private void CloseWindow(object sender, RoutedEventArgs e) { Close(); }

        private void OpenTools(object sender, RoutedEventArgs e)
        {
            var menu = new ContextMenu
            {
                PlacementTarget = ToolsButton,
                Placement = System.Windows.Controls.Primitives.PlacementMode.Top,
                HorizontalOffset = -150,
                VerticalOffset = -4
            };
            AddItem(menu, "Chọn thư mục Aiko hiện có", SelectExisting);
            AddItem(menu, "Kiểm tra cập nhật", async () => await controller.CheckAsync());
            AddItem(menu, "Khởi động lại Aiko", async () => await controller.RestartAsync());
            AddItem(menu, "Tắt server", controller.StopServer);
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
