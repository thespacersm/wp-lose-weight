import click

from wploseweight.command.abstract_command import AbstractCommand
from wploseweight.model.service.local_optimization_options import LocalOptimizationOptions
from wploseweight.service.uploads_optimization_service import UploadsOptimizationService


class OptimizeProjectCommand(AbstractCommand):
    command_name = "project:optimize"

    def __init__(self, uploads_optimization_service: UploadsOptimizationService):
        self.uploads_optimization_service = uploads_optimization_service

    def register_options(self, fn):
        fn = click.option("--project-name", required=True, help="Nome progetto")(fn)
        fn = click.option("--max-width", type=int, default=1200, show_default=True)(fn)
        fn = click.option("--max-height", type=int, default=1200, show_default=True)(fn)
        fn = click.option("--max-quality", type=int, default=65, show_default=True)(fn)
        fn = click.option(
            "--image-name",
            default=None,
            help="Ottimizza solo questo nome file (basename), se valorizzato",
        )(fn)
        fn = click.option("--do-backup/--no-backup", default=True, show_default=True)(fn)
        fn = click.option(
            "--convert-png-to-jpeg/--no-convert-png-to-jpeg",
            default=True,
            show_default=True,
        )(fn)
        return fn

    def run(
        self,
        project_name: str,
        max_width: int,
        max_height: int,
        max_quality: int,
        image_name: str | None,
        do_backup: bool,
        convert_png_to_jpeg: bool,
    ):
        def notify(message: str) -> None:
            click.echo(f"[progress] {message}")

        options = LocalOptimizationOptions(
            project_name=project_name,
            max_width=max_width,
            max_height=max_height,
            max_quality=max_quality,
            image_name=image_name,
            do_backup=do_backup,
            convert_png_to_jpeg=convert_png_to_jpeg,
        )
        result = self.uploads_optimization_service.optimize_project(
            options,
            progress_callback=notify,
        )

        click.echo(f"Local uploads: {result.local_uploads_dir}")
        if result.backup_zip_path:
            click.echo(f"Backup zip: {result.backup_zip_path}")
        else:
            click.echo("Backup zip: SKIPPED (--no-backup)")
        click.echo(f"Immagini ottimizzate: {result.optimized_images}")
        click.echo(f"Video ottimizzati: {result.optimized_videos}")
        click.echo(f"PNG convertite in JPEG: {result.converted_png_images}")
        click.echo(f"Immagini saltate: {result.skipped_images}")
        click.echo(f"Video saltati: {result.skipped_videos}")
        click.echo(f"Dimensione precedente: {self._format_size(result.previous_size_bytes)}")
        click.echo(f"Dimensione nuova: {self._format_size(result.new_size_bytes)}")
        click.echo(
            f"Riduzione: {self._format_size(result.reduced_bytes)} ({result.reduced_percent:.2f}%)"
        )

    @staticmethod
    def _format_size(size: int) -> str:
        if size < 1024:
            return f"{size} B"
        if size < 1024**2:
            return f"{size / 1024:.2f} KB"
        if size < 1024**3:
            return f"{size / (1024**2):.2f} MB"
        return f"{size / (1024**3):.2f} GB"
