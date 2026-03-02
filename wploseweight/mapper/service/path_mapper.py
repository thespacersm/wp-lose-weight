import posixpath
from pathlib import Path


class PathMapper:
    IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
    VIDEO_EXTENSIONS = {".mov", ".mp4", ".ogg", ".mkv"}

    @staticmethod
    def remote_join(*parts: str) -> str:
        cleaned = [part.strip("/") for part in parts if part]
        if not cleaned:
            return "/"
        return "/" + posixpath.join(*cleaned)

    @staticmethod
    def is_image(path: Path) -> bool:
        return path.suffix.lower() in PathMapper.IMAGE_EXTENSIONS

    @staticmethod
    def is_video(path: Path) -> bool:
        return path.suffix.lower() in PathMapper.VIDEO_EXTENSIONS
