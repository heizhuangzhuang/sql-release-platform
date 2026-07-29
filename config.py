"""
配置模块。
现在支持“多个连接配置档案”，页面里可以新增、选择、删除。
如果本地还存在旧的 .env，会自动迁移出一个 default 档案，方便平滑过渡。
"""

import os
from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import field
from threading import RLock
from typing import Any
from typing import Dict
from typing import List
from typing import Optional

from dotenv import load_dotenv

from storage_utils import read_json_object
from storage_utils import write_json_object_atomic

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
    db_host: str = ""
    db_port: int = 5432
    db_user: str = ""
    db_password: Optional[str] = None
    custom_sql_options: List[Dict[str, Any]] = field(default_factory=list)

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

    def validate_database(self) -> None:
        """
        校验迁移数据库连接，类比 Java Service 在执行特定业务前做参数校验。
        原有 SQL 仍然连接 localhost，只有远程迁移 SQL 会调用这个方法。
        """
        if not self.db_host.strip():
            raise ValueError("请选择远程迁移 SQL 时，请先配置数据库 IP")
        if self.db_port < 1 or self.db_port > 65535:
            raise ValueError("数据库端口必须在 1 到 65535 之间")
        if not self.db_user.strip():
            raise ValueError("请选择远程迁移 SQL 时，请先配置数据库用户")
        if not self.db_password:
            raise ValueError("请选择远程迁移 SQL 时，请先配置数据库密码")


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
        # FastAPI 的同步接口会在线程池中运行，锁的作用类似 Java synchronized。
        self._lock = RLock()

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
            db_host=os.getenv("DB_HOST", ""),
            db_port=int(os.getenv("DB_PORT", "5432")),
            db_user=os.getenv("DB_USER", ""),
            db_password=os.getenv("DB_PASSWORD"),
        )

    def _write_data(self, data: Dict[str, Any]) -> None:
        write_json_object_atomic(self.file_path, data)

    @staticmethod
    def _profile_from_dict(item: Dict[str, Any]) -> ConnectionProfile:
        """兼容删除 SSH_KEY_PATH 前保存的旧配置。"""
        profile_data = dict(item)
        profile_data.pop("ssh_key_path", None)
        return ConnectionProfile(**profile_data)

    def load(self) -> Dict[str, Any]:
        """
        读取档案文件。
        如果文件不存在，则用旧 .env 初始化一个 default 档案。
        """
        with self._lock:
            if not os.path.exists(self.file_path):
                default_profile = self._env_default_profile()
                data = {
                    "active": default_profile.name,
                    "profiles": [asdict(default_profile)],
                }
                self._write_data(data)
                return data

            data = read_json_object(self.file_path)
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
        return [self._profile_from_dict(item) for item in data.get("profiles", [])]

    def get_active_name(self) -> str:
        data = self.load()
        return data.get("active", "")

    def get_active_profile(self) -> ConnectionProfile:
        data = self.load()
        active_name = data.get("active", "")
        for item in data.get("profiles", []):
            if item.get("name") == active_name:
                return self._profile_from_dict(item)
        raise ValueError("当前没有可用的活动配置")

    def save_profile(self, profile: ConnectionProfile) -> None:
        profile.validate()
        with self._lock:
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
        with self._lock:
            data = self.load()
            exists = any(item.get("name") == profile_name for item in data.get("profiles", []))
            if not exists:
                raise ValueError("配置不存在")
            data["active"] = profile_name
            self._write_data(data)

    def delete_profile(self, profile_name: str) -> None:
        with self._lock:
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
