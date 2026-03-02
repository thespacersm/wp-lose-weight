from __future__ import annotations

import shutil
import subprocess
import time
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Callable

from PIL import Image, ImageOps, ImageSequence, UnidentifiedImageError

from wploseweight.client.ftp_client import FtpClient
from wploseweight.mapper.service.path_mapper import PathMapper
from wploseweight.model.service.ftp_project_options import FtpProjectOptions
from wploseweight.model.service.local_optimization_options import LocalOptimizationOptions
from wploseweight.model.service.optimization_result import OptimizationResult


class UploadsOptimizationService:
    FTP_TRANSFER_MAX_RETRIES = 3
    FTP_TRANSFER_RETRY_DELAY_SECONDS = 3

    def __init__(self, ftp_client: FtpClient, path_mapper: PathMapper, var_dir: Path):
        self.ftp_client = ftp_client
        self.path_mapper = path_mapper
        self.var_dir = var_dir

    def download_project(
        self,
        options: FtpProjectOptions,
        progress_callback: Callable[[str], None] | None = None,
    ) -> Path:
        self._notify(progress_callback, "Preparazione cartelle locali...")
        local_uploads_dir = self._local_uploads_dir(options.project_name)
        if local_uploads_dir.exists():
            shutil.rmtree(local_uploads_dir)
        local_uploads_dir.parent.mkdir(parents=True, exist_ok=True)

        self._download_with_retries(options, local_uploads_dir, progress_callback)
        return local_uploads_dir

    def optimize_project(
        self,
        options: LocalOptimizationOptions,
        progress_callback: Callable[[str], None] | None = None,
    ) -> OptimizationResult:
        local_project_dir = self._local_project_dir(options.project_name)
        source_uploads_dir = self._local_uploads_dir(options.project_name)
        optimized_uploads_dir = self._local_optimized_uploads_dir(options.project_name)
        if not source_uploads_dir.exists():
            raise RuntimeError(
                f"Cartella locale non trovata: {source_uploads_dir}. Esegui prima `project:download`."
            )

        self._notify(progress_callback, "Preparazione cartella ottimizzata parallela...")
        if optimized_uploads_dir.exists():
            shutil.rmtree(optimized_uploads_dir)
        optimized_uploads_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source_uploads_dir, optimized_uploads_dir)

        previous_size = self._directory_size(optimized_uploads_dir)
        backup_zip_path = None
        if options.do_backup:
            self._notify(progress_callback, "Creazione backup zip...")
            backup_zip_path = self._create_backup_zip(
                local_project_dir,
                source_uploads_dir,
                progress_callback=progress_callback,
            )
        else:
            self._notify(progress_callback, "Backup zip disattivato (--no-backup).")
        self._notify(progress_callback, "Ottimizzazione immagini in corso...")
        optimized_images, optimized_videos, converted_png, skipped_images, skipped_videos = (
            self._optimize_images_and_videos(
            optimized_uploads_dir,
            options,
            progress_callback=progress_callback,
            )
        )
        self._notify(progress_callback, "Ottimizzazione completata.")
        new_size = self._directory_size(optimized_uploads_dir)
        reduced_bytes = max(previous_size - new_size, 0)
        reduced_percent = (reduced_bytes / previous_size * 100) if previous_size else 0.0

        return OptimizationResult(
            local_uploads_dir=optimized_uploads_dir,
            backup_zip_path=backup_zip_path,
            previous_size_bytes=previous_size,
            new_size_bytes=new_size,
            reduced_bytes=reduced_bytes,
            reduced_percent=reduced_percent,
            optimized_images=optimized_images,
            optimized_videos=optimized_videos,
            converted_png_images=converted_png,
            skipped_images=skipped_images,
            skipped_videos=skipped_videos,
        )

    def upload_project(
        self,
        options: FtpProjectOptions,
        progress_callback: Callable[[str], None] | None = None,
    ) -> None:
        local_uploads_dir = self._local_optimized_uploads_dir(options.project_name)
        if not local_uploads_dir.exists():
            raise RuntimeError(
                f"Cartella locale non trovata: {local_uploads_dir}. Esegui prima `project:optimize`."
            )
        self._upload_with_retries(options, local_uploads_dir, progress_callback)

    def _local_project_dir(self, project_name: str) -> Path:
        return self.var_dir / "projects" / project_name

    def _local_uploads_dir(self, project_name: str) -> Path:
        return self._local_project_dir(project_name) / "wp-content" / "uploads"

    def _local_optimized_uploads_dir(self, project_name: str) -> Path:
        return self._local_project_dir(project_name) / "wp-content-optimized" / "uploads"

    @staticmethod
    def _directory_size(directory: Path) -> int:
        total = 0
        for path in directory.rglob("*"):
            if path.is_file():
                total += path.stat().st_size
        return total

    def _create_backup_zip(
        self,
        local_project_dir: Path,
        local_uploads_dir: Path,
        progress_callback: Callable[[str], None] | None = None,
    ) -> Path:
        day = datetime.now().strftime("%Y%m%d")
        backup_path = local_project_dir / f"wp-content/uploads.bckwploseweight{day}.zip"
        backup_path.parent.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(backup_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in local_uploads_dir.rglob("*"):
                if path.is_file():
                    archive.write(path, path.relative_to(local_project_dir))
        self._notify(progress_callback, f"Backup creato: {backup_path}")

        return backup_path

    def _optimize_images_and_videos(
        self,
        uploads_dir: Path,
        options: LocalOptimizationOptions,
        progress_callback: Callable[[str], None] | None = None,
    ) -> tuple[int, int, int, int, int]:
        optimized_images = 0
        optimized_videos = 0
        converted_png_images = 0
        skipped_images = 0
        skipped_videos = 0
        target_image_name = options.image_name.strip() if options.image_name else None
        matched_files = 0

        for path in uploads_dir.rglob("*"):
            if not path.is_file():
                continue
            if target_image_name and path.name != target_image_name:
                continue

            is_image = self.path_mapper.is_image(path)
            is_video = self.path_mapper.is_video(path)
            if not is_image and not is_video:
                continue

            matched_files += 1

            try:
                if is_image:
                    converted = self._optimize_single_image(path, options)
                    optimized_images += 1
                    if converted:
                        converted_png_images += 1
                    if optimized_images % 100 == 0:
                        self._notify(progress_callback, f"Immagini ottimizzate: {optimized_images}")
                else:
                    self._optimize_single_video(path)
                    optimized_videos += 1
                    self._notify(progress_callback, f"Video ottimizzato: {path}")
            except (OSError, UnidentifiedImageError, ValueError) as exc:
                if is_image:
                    skipped_images += 1
                    self._notify(progress_callback, f"Immagine saltata ({path}): {exc}")
                else:
                    skipped_videos += 1
                    self._notify(progress_callback, f"Video saltato ({path}): {exc}")
            except RuntimeError as exc:
                if is_image:
                    skipped_images += 1
                    self._notify(progress_callback, f"Immagine saltata ({path}): {exc}")
                else:
                    skipped_videos += 1
                    self._notify(progress_callback, f"Video saltato ({path}): {exc}")

        if target_image_name and matched_files == 0:
            raise RuntimeError(
                f"Nessun media trovato con nome `{target_image_name}` in `{uploads_dir}`."
            )

        return (
            optimized_images,
            optimized_videos,
            converted_png_images,
            skipped_images,
            skipped_videos,
        )

    @staticmethod
    def _optimize_single_image(path: Path, options: LocalOptimizationOptions) -> bool:
        ext = path.suffix.lower()
        convert_to_jpeg = options.convert_png_to_jpeg and ext in {".png", ".gif"}
        converted_png = False

        with Image.open(path) as source:
            if ext == ".gif" and getattr(source, "is_animated", False) and source.n_frames > 1:
                UploadsOptimizationService._optimize_animated_gif(path, source, options)
                return False

            image = ImageOps.exif_transpose(source)
            image.thumbnail((options.max_width, options.max_height), Image.Resampling.LANCZOS)
            save_kwargs = {}
            save_format = source.format

            if ext in {".jpg", ".jpeg"} or convert_to_jpeg:
                # For alpha formats converted to JPEG, force white background.
                if convert_to_jpeg:
                    rgba_image = image.convert("RGBA")
                    white_background = Image.new("RGB", rgba_image.size, (255, 255, 255))
                    white_background.paste(rgba_image, mask=rgba_image.getchannel("A"))
                    image = white_background
                elif image.mode not in {"RGB", "L"}:
                    image = image.convert("RGB")

                save_format = "JPEG"
                save_kwargs = {
                    "quality": options.max_quality,
                    "optimize": True,
                    "progressive": True,
                }
                converted_png = ext == ".png" and convert_to_jpeg
            elif ext == ".webp":
                save_format = "WEBP"
                save_kwargs = {"quality": options.max_quality, "method": 6}
            elif ext == ".png":
                if image.mode == "P":
                    image = image.convert("RGBA")
                save_format = "PNG"
                save_kwargs = {"optimize": True}
            elif ext == ".gif":
                save_format = "GIF"
                save_kwargs = {"optimize": True}
            else:
                return False

            temp_path = path.with_suffix(path.suffix + ".tmp")
            image.save(temp_path, format=save_format, **save_kwargs)
            temp_path.replace(path)

        return converted_png

    @staticmethod
    def _optimize_animated_gif(
        path: Path, source: Image.Image, options: LocalOptimizationOptions
    ) -> None:
        frames: list[Image.Image] = []
        durations: list[int] = []
        colors = max(16, min(256, int((options.max_quality / 100) * 256)))

        for frame in ImageSequence.Iterator(source):
            frame_rgba = frame.convert("RGBA")
            frame_rgba.thumbnail((options.max_width, options.max_height), Image.Resampling.LANCZOS)
            frame_palette = frame_rgba.quantize(colors=colors, method=Image.Quantize.FASTOCTREE)
            frames.append(frame_palette)
            durations.append(frame.info.get("duration", source.info.get("duration", 100)))

        if not frames:
            raise RuntimeError(f"Nessun frame GIF disponibile in `{path}`.")

        temp_path = path.with_suffix(path.suffix + ".tmp")
        frames[0].save(
            temp_path,
            format="GIF",
            save_all=True,
            append_images=frames[1:],
            optimize=True,
            loop=source.info.get("loop", 0),
            duration=durations,
            disposal=2,
        )
        temp_path.replace(path)

    @staticmethod
    def _optimize_single_video(path: Path) -> None:
        temp_path = path.with_suffix(path.suffix + ".tmp")
        command = [
            "ffmpeg",
            "-y",
            "-i",
            str(path),
            "-vf",
            "scale=-2:720:force_original_aspect_ratio=decrease",
            "-c:v",
            "libx264",
            "-crf",
            "28",
            "-preset",
            "veryslow",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
            "-f",
            "mp4",
            str(temp_path),
        ]
        try:
            subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        except FileNotFoundError as exc:
            raise RuntimeError("Comando `ffmpeg` non trovato.") from exc
        except subprocess.CalledProcessError as exc:
            details = (exc.stderr or exc.stdout or "").strip()
            raise RuntimeError(f"ffmpeg fallito: {details}") from exc

        temp_path.replace(path)

    @staticmethod
    def _notify(callback: Callable[[str], None] | None, message: str) -> None:
        if callback:
            callback(message)

    def _download_with_retries(
        self,
        options: FtpProjectOptions,
        local_uploads_dir: Path,
        progress_callback: Callable[[str], None] | None,
    ) -> None:
        self._notify(progress_callback, "Risoluzione root FTP...")
        with self.ftp_client.connect(options.ftp_ip, options.ftp_username, options.ftp_password) as ftp:
            root_dir = ftp.pwd()
            self._notify(progress_callback, f"Root FTP rilevata: {root_dir}")
            wp_content_remote = self.path_mapper.remote_join(root_dir, "wp-content")
            if not self.ftp_client.is_dir(ftp, wp_content_remote):
                raise RuntimeError("`wp-content` non trovato nella root FTP.")
            uploads_remote = self.path_mapper.remote_join(wp_content_remote, "uploads")
            if not self.ftp_client.is_dir(ftp, uploads_remote):
                raise RuntimeError("`wp-content/uploads` non trovato sulla root FTP.")

        wget_url = f"ftp://{options.ftp_ip}{uploads_remote}/"
        self._notify(progress_callback, f"Download con wget da: {wget_url}")
        for attempt in range(1, self.FTP_TRANSFER_MAX_RETRIES + 1):
            try:
                self._notify(
                    progress_callback,
                    f"Esecuzione wget (tentativo {attempt}/{self.FTP_TRANSFER_MAX_RETRIES})...",
                )
                if local_uploads_dir.exists():
                    shutil.rmtree(local_uploads_dir)
                local_uploads_dir.mkdir(parents=True, exist_ok=True)

                command = [
                    "wget",
                    "-r",
                    "-nH",
                    "--cut-dirs=2",
                    "--ftp-user",
                    options.ftp_username,
                    "--ftp-password",
                    options.ftp_password,
                    "--directory-prefix",
                    str(local_uploads_dir),
                    "--no-verbose",
                    "--timeout=60",
                    "--tries=1",
                    wget_url,
                ]
                process = subprocess.Popen(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
                assert process.stdout is not None
                for line in process.stdout:
                    stripped = line.strip()
                    if stripped:
                        self._notify(progress_callback, f"wget: {stripped}")

                return_code = process.wait()
                if return_code != 0:
                    raise RuntimeError(f"wget terminato con codice {return_code}")
                self._notify(progress_callback, "Download completato.")
                return
            except Exception as exc:
                if attempt >= self.FTP_TRANSFER_MAX_RETRIES:
                    raise RuntimeError("Download FTP con wget fallito.") from exc
                self._notify(
                    progress_callback,
                    f"Errore download wget: {exc}. Nuovo tentativo tra "
                    f"{self.FTP_TRANSFER_RETRY_DELAY_SECONDS}s...",
                )
                time.sleep(self.FTP_TRANSFER_RETRY_DELAY_SECONDS)

    def _upload_with_retries(
        self,
        options: FtpProjectOptions,
        local_uploads_dir: Path,
        progress_callback: Callable[[str], None] | None,
    ) -> None:
        for attempt in range(1, self.FTP_TRANSFER_MAX_RETRIES + 1):
            try:
                self._notify(
                    progress_callback,
                    f"Connessione FTP per reupload (tentativo "
                    f"{attempt}/{self.FTP_TRANSFER_MAX_RETRIES})...",
                )
                with self.ftp_client.connect(
                    options.ftp_ip, options.ftp_username, options.ftp_password
                ) as ftp:
                    root_dir = ftp.pwd()
                    uploads_remote = self.path_mapper.remote_join(root_dir, "wp-content", "uploads")
                    self._notify(progress_callback, "Reupload dei file ottimizzati in corso...")
                    self.ftp_client.upload_tree(
                        ftp,
                        local_uploads_dir,
                        uploads_remote,
                        progress_callback=progress_callback,
                    )
                    self._notify(progress_callback, "Reupload completato.")
                    return
            except Exception as exc:
                if attempt >= self.FTP_TRANSFER_MAX_RETRIES:
                    raise RuntimeError(
                        f"Reupload FTP fallito dopo {self.FTP_TRANSFER_MAX_RETRIES} tentativi."
                    ) from exc
                self._notify(
                    progress_callback,
                    f"Errore reupload FTP: {exc}. Nuovo tentativo tra "
                    f"{self.FTP_TRANSFER_RETRY_DELAY_SECONDS}s...",
                )
                time.sleep(self.FTP_TRANSFER_RETRY_DELAY_SECONDS)
