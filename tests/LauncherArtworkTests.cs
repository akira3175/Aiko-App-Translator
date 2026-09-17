using System;
using System.IO;
using System.Net;
using AikoLauncher;

internal static class LauncherArtworkTests
{
    private static void Assert(bool value, string message) { if (!value) throw new Exception(message); Console.WriteLine("PASS " + message); }
    [STAThread] public static int Main(string[] args)
    {
        string root = Path.Combine(Path.GetTempPath(), "aiko-artwork-test-" + Guid.NewGuid().ToString("N")); Directory.CreateDirectory(root);
        try
        {
            var image = LauncherArtwork.Decode(File.ReadAllBytes(args[0]));
            Assert(image.IsFrozen && image.PixelWidth > 0, "valid PNG decodes and freezes for UI thread");
            Assert(LauncherArtwork.ReadCache(Path.Combine(root, "missing.png")) == null, "missing cache falls back");
            string cache = Path.Combine(root, "image.png"); File.WriteAllText(cache, "not an image");
            Assert(LauncherArtwork.ReadCache(cache) == null, "corrupt cache falls back");
            bool rejected = false; try { LauncherArtwork.Decode(new byte[LauncherArtwork.MaxBytes + 1]); } catch (InvalidDataException) { rejected = true; }
            Assert(rejected, "oversized image rejected");
            File.Copy(args[0], cache, true);
            Assert(LauncherArtwork.ReadCache(cache) != null, "valid cache loads offline");
            if (args.Length > 1)
            {
                ServicePointManager.SecurityProtocol = SecurityProtocolType.Tls12;
                foreach (string file in new[] { "aiko-blue-logo.png", "aiko-launcher-background.png" })
                {
                    string path = Path.Combine(root, file);
                    Assert(LauncherArtwork.Download(file, path) != null, "live GitHub download " + file);
                    Assert(LauncherArtwork.ReadCache(path) != null, "saved cache " + file);
                    Assert(File.ReadAllText(path + ".etag").Length > 0, "ETag saved " + file);
                    Assert(LauncherArtwork.Download(file, path) == null, "unchanged image returns HTTP 304 " + file);
                    string etag = File.ReadAllText(path + ".etag");
                    File.WriteAllText(path + ".etag", "\"outdated-test\"");
                    Assert(LauncherArtwork.Download(file, path) != null && File.ReadAllText(path + ".etag") == etag,
                        "stale cache is replaced and ETag refreshed " + file);
                }
                string retained = Path.Combine(root, "aiko-blue-logo.png"); byte[] before = File.ReadAllBytes(retained);
                try { LauncherArtwork.Download("missing-artwork-test.png", retained); } catch (WebException) { }
                Assert(Convert.ToBase64String(before) == Convert.ToBase64String(File.ReadAllBytes(retained)), "HTTP failure preserves cached image");
            }
            return 0;
        }
        catch (Exception error) { Console.Error.WriteLine(error); return 1; }
        finally { Directory.Delete(root, true); }
    }
}
