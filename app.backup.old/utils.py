import httpx
import tempfile
import os

async def fetch_to_tmp(file_url: str) -> str:
    # Streams large files to disk
    async with httpx.AsyncClient(timeout=None, follow_redirects=True) as client:
        async with client.stream("GET", file_url) as r:
            r.raise_for_status()
            fd, path = tempfile.mkstemp(suffix=".pdf")
            with os.fdopen(fd, "wb") as f:
                async for chunk in r.aiter_bytes():
                    f.write(chunk)
    return path
