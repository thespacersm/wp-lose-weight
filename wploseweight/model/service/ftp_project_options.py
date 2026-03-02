from pydantic import BaseModel, ConfigDict


class FtpProjectOptions(BaseModel):
    model_config = ConfigDict(frozen=True)

    ftp_ip: str
    ftp_username: str
    ftp_password: str
    project_name: str
