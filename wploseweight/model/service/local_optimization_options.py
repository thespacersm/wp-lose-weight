from pydantic import BaseModel, ConfigDict


class LocalOptimizationOptions(BaseModel):
    model_config = ConfigDict(frozen=True)

    project_name: str
    max_width: int = 1200
    max_height: int = 1200
    max_quality: int = 65
    convert_png_to_jpeg: bool = True
    image_name: str | None = None
    do_backup: bool = True
