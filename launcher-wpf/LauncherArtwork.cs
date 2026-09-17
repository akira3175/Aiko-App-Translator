using System;
using System.IO;
using System.Net;
using System.Threading.Tasks;
using System.Windows.Media.Imaging;

namespace AikoLauncher
{
    internal static class LauncherArtwork
    {
        internal const string BaseUrl = "https://raw.githubusercontent.com/akira3175/Aiko-App-Translator/main/web/assets/anime/";
        internal const int MaxBytes = 20 * 1024 * 1024;

        internal static BitmapSource Decode(byte[] bytes)
        {
            if (bytes.Length > MaxBytes) throw new InvalidDataException("Artwork too large.");
            using (var stream = new MemoryStream(bytes))
            {
                var decoder = BitmapDecoder.Create(stream, BitmapCreateOptions.PreservePixelFormat, BitmapCacheOption.OnLoad);
                if (!(decoder is PngBitmapDecoder) && !(decoder is JpegBitmapDecoder)) throw new InvalidDataException("Expected PNG or JPEG artwork.");
                var frame = decoder.Frames[0];
                if (frame.PixelWidth <= 0 || frame.PixelHeight <= 0 || (long)frame.PixelWidth * frame.PixelHeight > 24000000)
                    throw new InvalidDataException("Artwork dimensions too large.");
                frame.Freeze(); return frame;
            }
        }

        internal static BitmapSource ReadCache(string path)
        {
            try { return new FileInfo(path).Length <= MaxBytes ? Decode(File.ReadAllBytes(path)) : null; }
            catch (Exception) { return null; }
        }

        internal static BitmapSource Download(string fileName, string cache)
        {
            var request = (HttpWebRequest)WebRequest.Create(BaseUrl + fileName);
            request.UserAgent = "Aiko-Launcher/1.1";
            request.Timeout = 15000; request.ReadWriteTimeout = 15000;
            request.CachePolicy = new System.Net.Cache.RequestCachePolicy(System.Net.Cache.RequestCacheLevel.Revalidate);
            // Only trust an ETag if its cached image still decodes successfully.
            if (ReadCache(cache) != null && File.Exists(cache + ".etag"))
            {
                string etag = File.ReadAllText(cache + ".etag");
                if (etag.Length < 256 && !etag.Contains("\r") && !etag.Contains("\n")) request.Headers[HttpRequestHeader.IfNoneMatch] = etag;
            }
            try
            {
                using (var response = (HttpWebResponse)request.GetResponse())
                using (var input = response.GetResponseStream())
                using (var output = new MemoryStream())
                {
                    if (response.ContentLength > MaxBytes) throw new InvalidDataException("Artwork too large.");
                    byte[] buffer = new byte[65536]; int count;
                    while ((count = input.Read(buffer, 0, buffer.Length)) > 0)
                    {
                        if (output.Length + count > MaxBytes) throw new InvalidDataException("Artwork too large.");
                        output.Write(buffer, 0, count);
                    }
                    byte[] bytes = output.ToArray(); var image = Decode(bytes);
                    // A cache write failure must not prevent displaying a valid download.
                    try
                    {
                        Directory.CreateDirectory(Path.GetDirectoryName(cache));
                        string temporary = cache + ".tmp";
                        File.WriteAllBytes(temporary, bytes);
                        if (File.Exists(cache)) File.Replace(temporary, cache, null); else File.Move(temporary, cache);
                        File.WriteAllText(cache + ".etag", response.Headers[HttpResponseHeader.ETag] ?? "");
                    }
                    catch (IOException) { }
                    catch (UnauthorizedAccessException) { }
                    return image;
                }
            }
            catch (WebException error)
            {
                var response = error.Response as HttpWebResponse;
                if (response != null) { bool unchanged = response.StatusCode == HttpStatusCode.NotModified; response.Dispose(); if (unchanged) return null; }
                throw;
            }
        }

        internal static string CachePath(string fileName)
        {
            return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Aiko Launcher", "artwork", fileName);
        }

        internal static async Task RefreshCacheAsync(string fileName)
        {
            try { await Task.Run(() => Download(fileName, CachePath(fileName))); }
            catch (Exception) { /* Retain offline fallback; never change the displayed image mid-session. */ }
        }

        internal static async Task RefreshAsync(string fileName, Action<BitmapSource> display)
        {
            string cache = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Aiko Launcher", "artwork", fileName);
            try
            {
                var saved = await Task.Run(() => ReadCache(cache));
                if (saved != null) display(saved);
                var latest = await Task.Run(() => Download(fileName, cache));
                if (latest != null) display(latest);
            }
            catch (Exception) { /* Keep cached/embedded artwork. Network errors never block launching Aiko. */ }
        }
    }
}
