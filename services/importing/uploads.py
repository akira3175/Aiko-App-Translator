"""Write uploaded bytes or streamed chunks without buffering the whole file."""


def write_upload(path, content):
    chunks = (content,) if isinstance(content, bytes) else content
    total = 0
    with path.open("wb") as output:
        for chunk in chunks:
            output.write(chunk)
            total += len(chunk)
    if not total:
        raise ValueError("File trống")
