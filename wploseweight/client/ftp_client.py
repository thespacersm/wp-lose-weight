from __future__ import annotations

from ftplib import FTP, all_errors, error_perm
from pathlib import Path
from posixpath import join as posix_join
from typing import Callable, Iterable


class FtpClient:
    def __init__(self, timeout_seconds: int = 600):
        self.timeout_seconds = timeout_seconds

    def connect(self, host: str, username: str, password: str) -> FTP:
        ftp = FTP(timeout=self.timeout_seconds)
        ftp.connect(host)
        ftp.login(user=username, passwd=password)
        ftp.set_pasv(True)
        return ftp

    def remote_exists(self, ftp: FTP, remote_path: str) -> bool:
        current = ftp.pwd()
        try:
            ftp.cwd(remote_path)
            ftp.cwd(current)
            return True
        except error_perm:
            try:
                ftp.size(remote_path)
                return True
            except error_perm:
                return False

    def is_dir(self, ftp: FTP, remote_path: str) -> bool:
        current = ftp.pwd()
        try:
            ftp.cwd(remote_path)
            ftp.cwd(current)
            return True
        except error_perm:
            return False
        except all_errors as exc:
            raise ConnectionError(f"Errore FTP durante controllo directory: {remote_path}") from exc

    def list_dir(self, ftp: FTP, remote_dir: str) -> list[str]:
        try:
            current = ftp.pwd()
            ftp.cwd(remote_dir)
            try:
                raw_entries = ftp.nlst()
            finally:
                ftp.cwd(current)
        except all_errors as exc:
            raise ConnectionError(f"Errore FTP durante listing directory: {remote_dir}") from exc

        entries: list[str] = []
        for entry in raw_entries:
            normalized = entry.rstrip("/")
            if not normalized:
                continue
            name = normalized.split("/")[-1]
            if name in {".", ".."}:
                continue
            if name not in entries:
                entries.append(name)
        return entries

    def download_tree(
        self,
        ftp: FTP,
        remote_dir: str,
        local_dir: Path,
        progress_callback: Callable[[str], None] | None = None,
    ) -> None:
        local_dir.mkdir(parents=True, exist_ok=True)
        for name in self.list_dir(ftp, remote_dir):
            remote_path = f"{remote_dir.rstrip('/')}/{name}"
            local_path = local_dir / name
            if self.is_dir(ftp, remote_path):
                self.download_tree(
                    ftp,
                    remote_path,
                    local_path,
                    progress_callback=progress_callback,
                )
                continue
            local_path.parent.mkdir(parents=True, exist_ok=True)
            with local_path.open("wb") as handle:
                ftp.retrbinary(f"RETR {remote_path}", handle.write)
            self._notify(progress_callback, f"Scaricato: {remote_path}")

    def list_files_recursive(self, ftp: FTP, remote_dir: str) -> list[str]:
        files: list[str] = []
        stack: list[str] = [remote_dir]

        while stack:
            current_dir = stack.pop()
            for name in self.list_dir(ftp, current_dir):
                remote_path = posix_join(current_dir.rstrip("/"), name)
                if self.is_dir(ftp, remote_path):
                    stack.append(remote_path)
                    continue
                files.append(remote_path)
        return files

    def download_file(self, ftp: FTP, remote_path: str, local_path: Path) -> None:
        local_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with local_path.open("wb") as handle:
                ftp.retrbinary(f"RETR {remote_path}", handle.write)
        except all_errors as exc:
            raise ConnectionError(f"Errore FTP durante download file: {remote_path}") from exc

    def ensure_remote_dir(self, ftp: FTP, remote_dir: str) -> None:
        parts = [part for part in remote_dir.split("/") if part]
        current = "/"
        for part in parts:
            next_path = f"{current.rstrip('/')}/{part}"
            if not self.is_dir(ftp, next_path):
                ftp.mkd(next_path)
            current = next_path

    def upload_tree(
        self,
        ftp: FTP,
        local_dir: Path,
        remote_dir: str,
        progress_callback: Callable[[str], None] | None = None,
    ) -> None:
        self.ensure_remote_dir(ftp, remote_dir)
        for file_path in self._iter_local_files(local_dir):
            relative = file_path.relative_to(local_dir).as_posix()
            remote_path = f"{remote_dir.rstrip('/')}/{relative}"
            self.ensure_remote_dir(ftp, remote_path.rsplit("/", 1)[0])
            try:
                with file_path.open("rb") as handle:
                    ftp.storbinary(f"STOR {remote_path}", handle)
            except all_errors as exc:
                raise ConnectionError(f"Errore FTP durante upload file: {remote_path}") from exc
            self._notify(progress_callback, f"Caricato: {remote_path}")

    @staticmethod
    def _iter_local_files(base_dir: Path) -> Iterable[Path]:
        for path in base_dir.rglob("*"):
            if path.is_file():
                yield path

    @staticmethod
    def _notify(callback: Callable[[str], None] | None, message: str) -> None:
        if callback:
            callback(message)
