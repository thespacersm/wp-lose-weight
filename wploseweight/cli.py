import click

from wploseweight.command.download_project_command import DownloadProjectCommand
from wploseweight.command.optimize_project_command import OptimizeProjectCommand
from wploseweight.command.upload_project_command import UploadProjectCommand
from wploseweight.container.default_container import DefaultContainer


@click.group()
def cli():
    """CLI entrypoint for wp-lose-weight."""
    pass


default_container = DefaultContainer.getInstance()
download_project_command: DownloadProjectCommand = default_container.get(DownloadProjectCommand)
optimize_project_command: OptimizeProjectCommand = default_container.get(OptimizeProjectCommand)
upload_project_command: UploadProjectCommand = default_container.get(UploadProjectCommand)
cli.add_command(download_project_command.to_click_command())
cli.add_command(optimize_project_command.to_click_command())
cli.add_command(upload_project_command.to_click_command())


if __name__ == "__main__":
    cli()
