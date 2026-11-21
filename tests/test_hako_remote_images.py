import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image
from up import remote_images, up_md


class HakoRemoteImageTests(unittest.TestCase):
    def response(self, data):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = data
        return response

    def test_download_unescapes_url_validates_image_and_caches(self):
        data = io.BytesIO()
        Image.new('RGB', (2, 2)).save(data, format='JPEG')
        with tempfile.TemporaryDirectory() as folder, patch.object(remote_images, 'urlopen', return_value=self.response(data.getvalue())) as fetch:
            path = remote_images.download_image(r'https\://rss.sfacg.com/web/image.jpg', folder)
            self.assertEqual(data.getvalue(), Path(path).read_bytes())
            self.assertEqual(path, remote_images.download_image('https://rss.sfacg.com/web/image.jpg', folder))
            fetch.assert_called_once()
            self.assertEqual('https://rss.sfacg.com/web/image.jpg', fetch.call_args.args[0].full_url)

    def test_inline_images_keep_text_order_and_use_r2(self):
        with tempfile.TemporaryDirectory() as folder:
            local = str(Path(folder, 'picture.jpg'))
            with patch.object(remote_images, 'download_image', return_value=local) as download, patch.object(up_md, 'upload_image_file', return_value='https://cdn.example/image.jpg') as upload:
                parts, count = up_md.elements_to_html_parts([{'type':'text', 'content':r'Trước[img=536,887]https\://rss.sfacg.com/a.jpg[/img]Sau[img]https://rss.sfacg.com/b.jpg[/img]Cuối'}], 'Title')
            self.assertEqual(2, count)
            self.assertEqual(2, download.call_count)
            self.assertEqual(2, upload.call_count)
            self.assertEqual(['<p>Trước</p>', '<p>Sau</p>', '<p>Cuối</p>'], parts[::2])
            self.assertIn('https://cdn.example/image.jpg', parts[1])
            self.assertNotIn('[img', ''.join(parts))

    def test_invalid_download_stops_before_r2(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(up_md, 'IMAGE_DIR', folder), patch.object(remote_images, 'urlopen', return_value=self.response(b'<html>denied</html>')), patch.object(up_md, 'upload_image_file') as upload:
            with self.assertRaisesRegex(RuntimeError, 'Không tải được ảnh'):
                up_md.elements_to_html_parts([{'type':'text','content':'[img=1,2]https://rss.sfacg.com/error.jpg[/img]'}], 'Title')
            upload.assert_not_called()
            self.assertEqual([], list(Path(folder).iterdir()))

    def test_plain_text_and_existing_markdown_are_preserved(self):
        elements = [{'type':'text','content':'Normal'}, {'type':'image','content':'![image](../image/a.jpg)'}]
        with patch.object(remote_images, 'download_image') as download:
            self.assertEqual(elements, remote_images.localize_bbcode_images(elements, 'unused'))
            download.assert_not_called()
