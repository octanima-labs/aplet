from pathlib import Path

import json
import re
import shutil
import sys


def patch_file_impl(path: str | Path, app_name: str, block_id: str, lines: list[str]) -> None:
    target_path = Path(path)
    start_tag = f"### APLET - {app_name}:{block_id} ###"
    legacy_start_tag = f"### APPLET - {app_name}:{block_id} ###"
    end_tag = f"### END - {app_name}:{block_id} ###"
    block_body = '\n'.join([start_tag, *lines, end_tag])
    block_text = f"{block_body}\n"

    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.touch(exist_ok=True)
    contents = target_path.read_text()
    pattern = re.compile(
        rf"^(?:{re.escape(start_tag)}|{re.escape(legacy_start_tag)})\n.*?\n{re.escape(end_tag)}(?:\n)?",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(contents)

    if match is not None:
        if match.group(0).rstrip('\n') == block_body:
            return
        target_path.write_text(f"{contents[:match.start()]}{block_text}{contents[match.end():]}")
        return

    if start_tag in contents or legacy_start_tag in contents or end_tag in contents:
        raise ValueError(f"[-] Malformed Aplet block for '{app_name}:{block_id}' in '{target_path}'")

    if contents and not contents.endswith('\n'):
        contents += '\n'
    target_path.write_text(f"{contents}{block_text}")


def write_text_impl(path: str | Path, content: str, create_parents: bool = False) -> None:
    target_path = Path(path)
    if create_parents:
        target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(content)


def remove_path_impl(path: str | Path, missing_ok: bool = False) -> None:
    target_path = Path(path)
    if target_path.is_dir() and not target_path.is_symlink():
        if not target_path.exists():
            if missing_ok:
                return
            raise FileNotFoundError(target_path)
        shutil.rmtree(target_path)
        return
    target_path.unlink(missing_ok=missing_ok)


def main() -> None:
    payload = json.load(sys.stdin)
    action = payload['action']
    if action == 'patch_file':
        patch_file_impl(payload['path'], payload['app_name'], payload['block_id'], payload['lines'])
        return
    if action == 'write_text':
        write_text_impl(payload['path'], payload['content'], create_parents=payload.get('create_parents', False))
        return
    if action == 'remove_path':
        remove_path_impl(payload['path'], missing_ok=payload.get('missing_ok', False))
        return
    raise ValueError(f"[-] Unknown file helper action '{action}'")


if __name__ == '__main__':
    main()
