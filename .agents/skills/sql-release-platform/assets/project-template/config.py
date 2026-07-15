"""
配置模块。
现在支持“多个连接配置档案”，页面里可以新增、选择、删除。
如果本地还存在旧的 .env，会自动迁移出一个 default 档案，方便平滑过渡。
"""

import json
import os
from dataclasses import asdict
from dataclasses import dataclass
from typing import Any
from typing import Dict
from typing import List
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


@dataclass
class ConnectionProfile:
    """
    连接档案，类比 Java 里一条环境配置 VO。
    """

    name: str
    ssh_host: str
    ssh_port: int
    ssh_user: str
    ssh_password: Optional[str]
    remote_dir: str
    script_name: str
    default_local_dir: str = ""

    def validate(self) -> None:
        if not self.name.strip():
            raise ValueError("配置名称不能为空")
        if not self.ssh_host.strip():
            raise ValueError("SSH_HOST 不能为空")
        if not self.ssh_user.strip():
            raise ValueError("SSH_USER 不能为空")
        if not self.remote_dir.strip():
            raise ValueError("REMOTE_DIR 不能为空")
        if not self.ssh_password:
            raise ValueError("请填写 SSH 密码")


@dataclass(frozen=True)
class Settings:
    """
    应用级配置。
    profiles_file 是多配置档案的存储位置。
    """

    profiles_file: str = os.getenv("PROFILES_FILE", "profiles.json")
    default_script_name: str = os.getenv("SCRIPT_NAME", "224.sh")
    log_dir: str = os.getenv("LOG_DIR", "runtime_logs")
    log_max_bytes: int = int(os.getenv("LOG_MAX_BYTES", str(2 * 1024 * 1024)))
    log_backup_count: int = int(os.getenv("LOG_BACKUP_COUNT", "5"))


class ProfileStore:
    """
    档案存储。
    这里用本地 JSON 文件保存，简单直接，适合当前项目。
    """

    def __init__(self, file_path: str, default_script_name: str):
        self.file_path = file_path
        self.default_script_name = default_script_name

    def _env_default_profile(self) -> ConnectionProfile:
        """
        从旧 .env 生成一个默认档案，便于迁移。
        """
        return ConnectionProfile(
            name="default",
            ssh_host=os.getenv("SSH_HOST", "127.0.0.1"),
            ssh_port=int(os.getenv("SSH_PORT", "22")),
            ssh_user=os.getenv("SSH_USER", "shunli"),
            ssh_password=os.getenv("SSH_PASSWORD"),
            remote_dir=os.getenv("REMOTE_DIR", "/opt/upload"),
            script_name=os.getenv("SCRIPT_NAME", self.default_script_name),
            default_local_dir=os.getenv("DEFAULT_LOCAL_DIR", ""),
        )

    def _write_data(self, data: Dict[str, Any]) -> None:
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load(self) -> Dict[str, Any]:
        """
        读取档案文件。
        如果文件不存在，则用旧 .env 初始化一个 default 档案。
        """
        if not os.path.exists(self.file_path):
            default_profile = self._env_default_profile()
            data = {
                "active": default_profile.name,
                "profiles": [asdict(default_profile)],
            }
            self._write_data(data)
            return data

        with open(self.file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not data.get("profiles"):
            default_profile = self._env_default_profile()
            data = {
                "active": default_profile.name,
                "profiles": [asdict(default_profile)],
            }
            self._write_data(data)
        return data

    def list_profiles(self) -> Dict[str, Any]:
        return self.load()

    def get_profiles(self) -> List[ConnectionProfile]:
        data = self.load()
        profiles = []
        for item in data.get("profiles", []):
            item.pop("ssh_key_path", None)
            profiles.append(ConnectionProfile(**item))
        return profiles

    def get_active_name(self) -> str:
        data = self.load()
        return data.get("active", "")

    def get_active_profile(self) -> ConnectionProfile:
        data = self.load()
        active_name = data.get("active", "")
        for item in data.get("profiles", []):
            item.pop("ssh_key_path", None)
            if item.get("name") == active_name:
                return ConnectionProfile(**item)
        raise ValueError("当前没有可用的活动配置")

    def save_profile(self, profile: ConnectionProfile) -> None:
        profile.validate()
        data = self.load()
        profiles = data.get("profiles", [])

        updated = False
        for index, item in enumerate(profiles):
            if item.get("name") == profile.name:
                profiles[index] = asdict(profile)
                updated = True
                break

        if not updated:
            profiles.append(asdict(profile))

        if not data.get("active"):
            data["active"] = profile.name

        data["profiles"] = profiles
        self._write_data(data)

    def set_active(self, profile_name: str) -> None:
        data = self.load()
        exists = False
        for item in data.get("profiles", []):
            if item.get("name") == profile_name:
                exists = True
                break
        if not exists:
            raise ValueError("配置不存在")
        data["active"] = profile_name
        self._write_data(data)

    def delete_profile(self, profile_name: str) -> None:
        data = self.load()
        profiles = [item for item in data.get("profiles", []) if item.get("name") != profile_name]
        if len(profiles) == len(data.get("profiles", [])):
            raise ValueError("配置不存在")
        if not profiles:
            raise ValueError("至少保留一个配置")

        data["profiles"] = profiles
        if data.get("active") == profile_name:
            data["active"] = profiles[0]["name"]
        self._write_data(data)


settings = Settings()
profile_store = ProfileStore(settings.profiles_file, settings.default_script_name)
