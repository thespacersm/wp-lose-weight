import click

from wploseweight.command.abstract_command import AbstractCommand
from wploseweight.model.service.ftp_project_options import FtpProjectOptions
from wploseweight.service.uploads_optimization_service import UploadsOptimizationService


class UploadProjectCommand(AbstractCommand):
    command_name = "project:upload"

    def __init__(self, uploads_optimization_service: UploadsOptimizationService):
        self.uploads_optimization_service = uploads_optimization_service

    def register_options(self, fn):
        fn = click.option("--ip", "ftp_ip", required=True, help="FTP host/IP")(fn)
        fn = click.option("--username", "ftp_username", required=True, help="FTP username")(fn)
        fn = click.option(
            "--password",
            "ftp_password",
            prompt=True,
            hide_input=True,
            required=False,
            help="FTP password",
        )(fn)
        fn = click.option("--project-name", required=True, help="Nome progetto")(fn)
        return fn

    def run(self, ftp_ip: str, ftp_username: str, ftp_password: str, project_name: str):
        def notify(message: str) -> None:
            click.echo(f"[progress] {message}")

        options = FtpProjectOptions(
            ftp_ip=ftp_ip,
            ftp_username=ftp_username,
            ftp_password=ftp_password,
            project_name=project_name,
        )
        self.uploads_optimization_service.upload_project(options, progress_callback=notify)
        click.echo("Upload completato.")
