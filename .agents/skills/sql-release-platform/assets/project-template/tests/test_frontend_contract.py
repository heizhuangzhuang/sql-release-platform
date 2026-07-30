"""页面结构契约测试，避免重构时悄悄破坏按钮和接口绑定。"""

import unittest
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = PROJECT_ROOT / "templates"


class ElementIdParser(HTMLParser):
    def __init__(self):
        HTMLParser.__init__(self)
        self.element_ids = []

    def handle_starttag(self, tag, attrs):
        for name, value in attrs:
            if name == "id" and value:
                self.element_ids.append(value)


def read_template(name):
    return (TEMPLATE_DIR / name).read_text(encoding="utf-8")


class FrontendContractTests(unittest.TestCase):
    def test_all_pages_have_unique_ids_and_mobile_viewport(self):
        for template_path in TEMPLATE_DIR.glob("*.html"):
            content = template_path.read_text(encoding="utf-8")
            parser = ElementIdParser()
            parser.feed(content)
            duplicates = [item for item, count in Counter(parser.element_ids).items() if count > 1]

            self.assertFalse(duplicates, "%s 存在重复 ID: %s" % (template_path.name, duplicates))
            self.assertIn('name="viewport"', content, template_path.name)
            self.assertIn("980px", content, "%s 应保持受控页面宽度" % template_path.name)

    def test_release_console_keeps_critical_controls_and_routes(self):
        content = read_template("index.html")
        required_ids = [
            "file",
            "uploadBtn",
            "clearDirBtn",
            "profileSelect",
            "saveProfileBtn",
            "genBtn",
            "runBtn",
            "remoteEntryList",
            "logList",
            "scriptContent",
            "customSqlHost",
            "customSqlPassword",
        ]
        required_routes = [
            "/upload",
            "/clear-dir",
            "/generate",
            "/run",
            "/logs",
            "/script-preview",
            "/custom-sql-options",
        ]
        for element_id in required_ids:
            self.assertIn('id="%s"' % element_id, content)
        for route in required_routes:
            self.assertIn(route, content)

        self.assertIn('id="dbPassword" type="password"', content)
        self.assertIn('id="customSqlPassword" type="password"', content)
        self.assertIn(r"/\bROLLBACK\b/i", content)
        self.assertIn(r"/\bCOMMIT\b/i", content)
        self.assertIn('label: "请检查"', content)
        self.assertIn('className: "warning"', content)

    def test_md5_pages_keep_saved_paths_scan_and_sort_contracts(self):
        local_content = read_template("md5_local.html")
        remote_content = read_template("md5_remote.html")

        for route in ("/md5-local-settings", "/md5-local-scan"):
            self.assertIn(route, local_content)
        for keyword in ("sortFiles", "sortDirection", "showDirectoryPicker"):
            self.assertIn(keyword, local_content)
        for route in ("/md5-defaults", "/md5-remote-settings", "/md5-scan"):
            self.assertIn(route, remote_content)


if __name__ == "__main__":
    unittest.main()
