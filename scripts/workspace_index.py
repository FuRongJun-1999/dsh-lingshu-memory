"""Generate role-based workspace index without inspecting private artifacts."""
from __future__ import annotations
import argparse
import pathlib
ROOT = pathlib.Path(__file__).resolve().parents[1]
DIR_ROLES = {"sandbox_runtime": "显式隔离合成执行，不接生产", ".github": "跨平台公开CI", "docs": "架构、恢复、安全、迁移与ADR", "spec": "结构化契约真源与冻结锁", "framework": "纯参考模型，不是运行时", "scripts": "规格、索引、合规和门禁工具", "tests": "独立预期样例与变异自证"}
ROOT_FILES = {"README.md": "项目入口与状态", "LICENSE": "MIT许可", "CONTRIBUTING.md": "贡献与验证纪律", "SECURITY.md": "漏洞报告边界", "WORKSPACE_INDEX.md": "本生成索引", ".gitignore": "本地产物排除", ".gitattributes": "文本格式"}
IGNORE = {".git", "__pycache__", ".pytest_cache", ".venv", "artifacts", ".private"}

def rendered():
    dirs = {p.name for p in ROOT.iterdir() if p.is_dir() and p.name not in IGNORE}
    files = {p.name for p in ROOT.iterdir() if p.is_file()} | {"WORKSPACE_INDEX.md"}
    if dirs != set(DIR_ROLES) or files != set(ROOT_FILES):
        raise ValueError("unregistered or missing roots: " + repr((dirs ^ set(DIR_ROLES), files ^ set(ROOT_FILES))))
    lines = ["# 工作区索引（生成）", "", "先按职责定位文件；新增根目录/文件须改本脚本登记后重生成。", "", "## 目录", ""]
    lines += ["- " + name + ": " + role for name, role in sorted(DIR_ROLES.items())]
    lines += ["", "## 根文件", ""]
    lines += ["- [" + name + "](<" + name + ">): " + role for name, role in sorted(ROOT_FILES.items())]
    lines += ["", "## 关键入口", "", "- [规格](<spec/core.json>) / [生成规范](<docs/CONTRACTS.generated.md>)", "- [模型](<framework/model.py>) / [测试](<tests/test_model.py>)", "- [架构](<docs/ARCHITECTURE.md>) / [路线](<docs/ROADMAP.md>)", "- [总门禁](<scripts/check_all.py>)", ""]
    return "\n".join(lines)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--write", action="store_true")
    args = p.parse_args()
    target = ROOT / "WORKSPACE_INDEX.md"
    text = rendered()
    if args.write:
        target.write_text(text, encoding="utf-8", newline="\n")
        print("generated workspace index")
        return 0
    if not target.exists() or target.read_text(encoding="utf-8") != text:
        raise ValueError("workspace index stale")
    print("PASS: workspace index")
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError) as e:
        print("FAIL:", str(e))
        raise SystemExit(1)
