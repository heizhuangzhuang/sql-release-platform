"""不连接 SSH、不执行 SQL 的核心回归测试。"""

import json
import os
import stat
import tempfile
import unittest
from dataclasses import asdict

import main
from config import ConnectionProfile
from config import ProfileStore
from storage_utils import read_json_object
from storage_utils import write_json_object_atomic


def build_profile(**overrides):
    """生成测试环境，类比 Java 测试中的 Test Fixture。"""
    values = {
        "name": "test",
        "ssh_host": "127.0.0.1",
        "ssh_port": 22,
        "ssh_user": "tester",
        "ssh_password": "ssh-password",
        "remote_dir": "/opt/upload",
        "script_name": "224.sh",
        "db_host": "10.20.30.40",
        "db_port": 55432,
        "db_user": "migration_user",
        "db_password": "migration password",
    }
    values.update(overrides)
    return ConnectionProfile(**values)


class StorageTests(unittest.TestCase):
    def test_atomic_json_write_is_readable_and_private(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = os.path.join(temp_dir, "settings.json")
            write_json_object_atomic(file_path, {"name": "测试", "value": 1})

            self.assertEqual({"name": "测试", "value": 1}, read_json_object(file_path))
            file_mode = stat.S_IMODE(os.stat(file_path).st_mode)
            self.assertEqual(0o600, file_mode)

    def test_invalid_json_has_clear_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = os.path.join(temp_dir, "broken.json")
            with open(file_path, "w", encoding="utf-8") as json_file:
                json_file.write("{")

            with self.assertRaisesRegex(ValueError, "JSON 格式错误"):
                read_json_object(file_path)


class ProfileStoreTests(unittest.TestCase):
    def test_save_switch_and_delete_profile(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ProfileStore(os.path.join(temp_dir, "profiles.json"), "224.sh")
            first = build_profile(name="T2")
            second = build_profile(name="Sit1", remote_dir="/opt/sit1")

            write_json_object_atomic(
                store.file_path,
                {"active": first.name, "profiles": [asdict(first)]},
            )
            store.save_profile(second)
            store.set_active("Sit1")
            self.assertEqual("Sit1", store.get_active_profile().name)

            store.delete_profile("T2")
            self.assertEqual(["Sit1"], [profile.name for profile in store.get_profiles()])
            with self.assertRaisesRegex(ValueError, "至少保留一个配置"):
                store.delete_profile("Sit1")

    def test_old_ssh_key_field_is_ignored(self):
        profile_data = build_profile().__dict__.copy()
        profile_data["ssh_key_path"] = "/old/key"
        profile = ProfileStore._profile_from_dict(profile_data)
        self.assertEqual("test", profile.name)


class ScriptGenerationTests(unittest.TestCase):
    def test_remote_migration_uses_account_password_and_fixed_log(self):
        profile = build_profile()
        block = "\n".join(main._build_script_block("pmigrel88", profile))

        self.assertIn("PGPASSWORD='migration password'", block)
        self.assertIn("-h 10.20.30.40 -p 55432 -U migration_user", block)
        self.assertIn("-d pmighis001db -f ./db_pmigrel00ldb_88.sql", block)
        self.assertIn("./log/pmigrel00ldb88_execute_sql.txt", block)
        self.assertEqual(
            "./log/pmigrel00ldb98_execute_sql.txt",
            main.SCRIPT_BLOCKS["pmigrel98"]["log_file"],
        )

    def test_custom_sql_order_and_preview_password_masking(self):
        custom = {
            "id": "custom001",
            "sql_file": "db_custom.sql",
            "database": "customdb",
            "pg_host": "10.20.30.50",
            "pg_port": 6432,
            "db_user": "custom_user",
            "db_password": "custom password",
            "log_file": "custom_execute_sql.txt",
        }
        profile = build_profile(custom_sql_options=[custom])
        content = main._build_script_content(
            {"data", main._custom_sql_key(custom["id"]), "test"},
            profile,
            [custom],
        )

        self.assertLess(content.index("pdata001db"), content.index("db_custom.sql"))
        self.assertLess(content.index("db_custom.sql"), content.index("测试脚本"))
        self.assertIn("mkdir -p ./log ./log/history", content)

        masked = main._mask_database_password_in_script(content, profile)
        self.assertNotIn("custom password", masked)
        self.assertIn("PGPASSWORD='******'", masked)

    def test_unknown_or_duplicate_custom_files_are_rejected(self):
        item = {
            "id": "custom001",
            "sql_file": "db_custom.sql",
            "database": "customdb",
            "pg_host": "10.20.30.50",
            "pg_port": 5432,
            "db_user": "custom_user",
            "db_password": "password",
            "log_file": "custom_execute_sql.txt",
        }
        with self.assertRaisesRegex(ValueError, "SQL 文件名已经存在"):
            main._normalize_custom_sql_options([item, dict(item, id="custom002")])


class UtilityTests(unittest.TestCase):
    def test_path_suffix_and_text_normalization(self):
        self.assertEqual("etc/file.sql", main._normalize_rel_path("../../etc/file.sql"))
        self.assertEqual("child/file.sql", main._strip_top_level_dir("root/child/file.sql"))
        self.assertEqual(["/a", "/b"], main._normalize_unique_text_values([" /a ", "/a", "/b", ""]))
        self.assertEqual([".sql", ".TXT"], main._normalize_md5_suffixes("sql,*.TXT, sql"))

    def test_remote_output_summary_does_not_change_short_text(self):
        self.assertEqual("完成", main._summarize_for_log("完成", 10))
        self.assertIn("已省略 3 个字符", main._summarize_for_log("12345678", 5))

    def test_md5_settings_update_preserves_other_section(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            old_path = main.MD5_SETTINGS_FILE
            main.MD5_SETTINGS_FILE = os.path.join(temp_dir, "md5_settings.json")
            try:
                main._update_md5_settings("local", {"paths": ["/tmp/sql"]})
                with open(main.MD5_SETTINGS_FILE, encoding="utf-8") as settings_file:
                    data = json.load(settings_file)
            finally:
                main.MD5_SETTINGS_FILE = old_path

            self.assertEqual(["/tmp/sql"], data["local"]["paths"])
            self.assertEqual({}, data["remote"]["connection"])


if __name__ == "__main__":
    unittest.main()
