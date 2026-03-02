from pathlib import Path

from pydantic import BaseModel, ConfigDict


class OptimizationResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    local_uploads_dir: Path
    backup_zip_path: Path | None
    previous_size_bytes: int
    new_size_bytes: int
    reduced_bytes: int
    reduced_percent: float
    optimized_images: int
    optimized_videos: int
    converted_png_images: int
    skipped_images: int
    skipped_videos: int
