import os
from pathlib import Path

from dotenv import load_dotenv
from injector import Injector

from wploseweight.client.ftp_client import FtpClient
from wploseweight.command.download_project_command import DownloadProjectCommand
from wploseweight.command.optimize_project_command import OptimizeProjectCommand
from wploseweight.command.upload_project_command import UploadProjectCommand
from wploseweight.mapper.service.path_mapper import PathMapper
from wploseweight.service.uploads_optimization_service import UploadsOptimizationService


class DefaultContainer:
    injector = None
    instance = None

    @staticmethod
    def getInstance():
        if DefaultContainer.instance is None:
            DefaultContainer.instance = DefaultContainer()
        return DefaultContainer.instance

    def __init__(self):
        self.injector = Injector()

        load_dotenv()
        self._init_directories()
        self._init_bindings()

    def _init_directories(self):
        self.root_dir = Path(__file__).resolve().parents[2]
        self.var_dir = self.root_dir / "var"
        os.makedirs(self.var_dir, exist_ok=True)

    def _init_bindings(self):
        path_mapper = PathMapper()
        ftp_client = FtpClient()
        uploads_optimization_service = UploadsOptimizationService(
            ftp_client=ftp_client,
            path_mapper=path_mapper,
            var_dir=self.var_dir,
        )

        self.injector.binder.bind(PathMapper, to=path_mapper)
        self.injector.binder.bind(FtpClient, to=ftp_client)
        self.injector.binder.bind(UploadsOptimizationService, to=uploads_optimization_service)
        self.injector.binder.bind(
            DownloadProjectCommand,
            to=DownloadProjectCommand(uploads_optimization_service=uploads_optimization_service),
        )
        self.injector.binder.bind(
            OptimizeProjectCommand,
            to=OptimizeProjectCommand(uploads_optimization_service=uploads_optimization_service),
        )
        self.injector.binder.bind(
            UploadProjectCommand,
            to=UploadProjectCommand(uploads_optimization_service=uploads_optimization_service),
        )

    def get(self, key):
        return self.injector.get(key)
