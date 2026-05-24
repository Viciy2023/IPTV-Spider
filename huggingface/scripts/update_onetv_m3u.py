#!/usr/bin/env python3
import argparse
import datetime as dt
import os
import shutil
import sqlite3
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


DEFAULT_DB_PATH = "/data/iptv.db"  # 默认读取的 IPTV 数据库文件路径，用来查找最新的广东组播 ip:端口记录。
DEFAULT_M3U_PATH = "/data/onetv_api_guangdong_multicast.m3u"  # 默认要更新的 OneTV M3U 播放列表文件路径。
DEFAULT_INTERNAL_BASE_URL = "http://127.0.0.1:50085"  # IPTV-Spider 内部接口地址，用来根据 ip:端口拉取分组后的 M3U。
DEFAULT_INTERVAL_SECONDS = 3 * 60  # 测试阶段监控模式下检查数据库变化的默认间隔：3 分钟，单位是秒。
DEFAULT_SETTLE_SECONDS = 10  # 发现数据库变更后先等待 10 秒，避免数据库还没写完就开始读取。
DEFAULT_BACKUP_RETENTION_SECONDS = 1 * 60 * 60  # M3U 备份文件默认保留 1 小时，超过后会被清理。
MIGU_SOURCE_URL = "https://raw.githubusercontent.com/develop202/migu_video/refs/heads/main/interface.txt"

KEEP_GROUPS = {
    "公众号【壹来了】",
    "国际频道",
    "电竞频道",
    "体育频道",
    "香港频道",
    "澳门频道",
    "台湾频道",
}

REPLACE_GROUPS = {
    "🕘️更新时间",
    "央视频道",
    "卫视频道",
    "4K节目",
    "中数传媒",
    "广东频道",
    "地方频道",
    "其他频道组",
    "未分类节目",
}

SOURCE_GROUPS = {
    "央视频道",
    "卫视频道",
    "4K节目",
    "中数传媒",
    "广东频道",
    "地方频道",
    "未分类节目",
}

UPDATE_PLACEHOLDER_URL = "https://proshls.wns.live/hls/stream.m3u8"
MIGU_LOGO_BASE_URL = "https://raw.githubusercontent.com/fanmingming/live/main/tv/"

MIGU_REGIONAL_GROUPS = {
    "浙江地区": "浙江频道",
    "江苏地区": "江苏频道",
    "黑龙江地区": "黑龙江频道",
    "江西地区": "江西频道",
    "陕西地区": "陕西频道",
}

MIGU_SOURCE_GROUPS = {
    "央视频道",
    "卫视频道",
    "超清频道",
    *MIGU_REGIONAL_GROUPS.keys(),
}

FINAL_GROUP_ORDER = [
    "🕘️更新时间",
    "公众号【壹来了】",
    "央视频道",
    "卫视频道",
    "广东频道",
    "浙江频道",
    "江苏频道",
    "黑龙江频道",
    "江西频道",
    "陕西频道",
    "地方频道",
    "其他频道组",
    "4K节目",
    "中数传媒",
    "国际频道",
    "电竞频道",
    "体育频道",
    "香港频道",
    "澳门频道",
    "台湾频道",
]


@dataclass
class Entry:
    extinf: str
    url: str
    group: str


def log(message: str) -> None:
    print(f"[{dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}", flush=True)


def extract_group(extinf: str) -> str:
    marker = 'group-title="'
    start = extinf.find(marker)
    if start == -1:
        return ""
    start += len(marker)
    end = extinf.find('"', start)
    if end == -1:
        return ""
    return extinf[start:end]


def parse_m3u(text: str) -> tuple[str, list[Entry]]:
    lines = text.splitlines()
    header = lines[0] if lines and lines[0].startswith("#EXTM3U") else "#EXTM3U"
    entries: list[Entry] = []
    i = 1 if lines and lines[0].startswith("#EXTM3U") else 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("#EXTINF") and i + 1 < len(lines):
            entries.append(Entry(line, lines[i + 1], extract_group(line)))
            i += 2
        else:
            i += 1
    return header, entries


def rename_source_group(extinf: str, group: str) -> str:
    if group == "未分类节目":
        return extinf.replace('group-title="未分类节目"', 'group-title="其他频道组"')
    return extinf


def entry_name(extinf: str) -> str:
    return extinf.rsplit(",", 1)[-1].strip() if "," in extinf else ""


def replace_entry_metadata(extinf: str, group: str, name: str, logo_name: Optional[str] = None) -> str:
    logo = logo_name or name
    return f'#EXTINF:-1 group-title="{group}" tvg-logo="{MIGU_LOGO_BASE_URL}/{logo}.png",{name}'


def normalize_migu_channel(name: str) -> str:
    normalized = name.strip()
    if normalized.startswith("CCTV"):
        digits = ""
        for char in normalized[4:]:
            if char.isdigit():
                digits += char
            else:
                break
        if digits:
            return f"CCTV{digits}"
    if normalized.endswith("4K"):
        normalized = normalized[:-2].strip()
    return normalized


def map_migu_group(source_group: str, normalized_name: str) -> str:
    if source_group in MIGU_REGIONAL_GROUPS:
        return MIGU_REGIONAL_GROUPS[source_group]
    if source_group == "超清频道":
        return "央视频道" if normalized_name.startswith("CCTV") else "卫视频道"
    return source_group


def is_onetv_update_entry(entry: Entry) -> bool:
    name = entry_name(entry.extinf)
    return entry.group == "公众号【壹来了】" and (name.startswith("ONETV更新日期:") or name.startswith("MIGU更新日期:"))


def merge_migu_playlist(base_text: str, migu_text: str) -> str:
    header, base_entries = parse_m3u(base_text)
    _, migu_entries = parse_m3u(migu_text)
    migu_by_key: dict[tuple[str, str], list[Entry]] = {}
    seen: set[tuple[str, str, str]] = set()
    update_date = ""
    cctv13_url = ""

    for entry in migu_entries:
        if entry.group not in MIGU_SOURCE_GROUPS:
            continue
        raw_name = entry_name(entry.extinf)
        if raw_name.startswith("更新日期:"):
            update_date = raw_name.removeprefix("更新日期:").strip()
            continue
        normalized_name = normalize_migu_channel(raw_name)
        target_group = map_migu_group(entry.group, normalized_name)
        normalized_entry = Entry(replace_entry_metadata(entry.extinf, target_group, normalized_name), entry.url, target_group)
        dedupe_key = (target_group, normalized_name, entry.url)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        migu_by_key.setdefault((target_group, normalized_name), []).append(normalized_entry)
        if normalized_name == "CCTV13" and not cctv13_url:
            cctv13_url = entry.url

    output_entries: list[Entry] = []
    if update_date and cctv13_url:
        output_entries.append(
            Entry(
                replace_entry_metadata("", "公众号【壹来了】", f"ONETV更新日期: {update_date}", "CCTV13"),
                cctv13_url,
                "公众号【壹来了】",
            )
        )

    for entry in base_entries:
        if is_onetv_update_entry(entry):
            continue
        key = (entry.group, normalize_migu_channel(entry_name(entry.extinf)))
        output_entries.extend(migu_by_key.pop(key, []))
        output_entries.append(entry)

    for entries in migu_by_key.values():
        output_entries.extend(entries)

    group_rank = {group: index for index, group in enumerate(FINAL_GROUP_ORDER)}
    output_entries.sort(key=lambda entry: group_rank.get(entry.group, len(group_rank)))

    output = [header]
    for entry in output_entries:
        output.extend([entry.extinf, entry.url])
    return "\n".join(output) + "\n"


def update_time_entry(updated_at: str) -> list[str]:
    return [
        f'#EXTINF:-1 group-title="🕘️更新时间" tvg-logo="https://github.com/taksssss/tv/tree/master/icon/{updated_at}.png",{updated_at}',
        UPDATE_PLACEHOLDER_URL,
    ]


def merge_playlists(base_text: str, source_text: str, updated_at: str) -> str:
    header, base_entries = parse_m3u(base_text)
    _, source_entries = parse_m3u(source_text)
    output: list[str] = [header]
    output.extend(update_time_entry(updated_at))

    for entry in base_entries:
        if entry.group in KEEP_GROUPS:
            output.extend([entry.extinf, entry.url])

    for entry in source_entries:
        if entry.group in SOURCE_GROUPS:
            output.extend([rename_source_group(entry.extinf, entry.group), entry.url])

    return "\n".join(output) + "\n"


def find_latest_guangdong_ip_port(db_path: Path) -> str:
    query = """
        SELECT ip_port, source_type, province_cn, created_at, id
        FROM iptv
        WHERE province_cn = ? OR source_type LIKE ?
        ORDER BY created_at DESC, id DESC
        LIMIT 1
    """
    with sqlite3.connect(str(db_path)) as conn:
        row = conn.execute(query, ("广东", "%广东%")).fetchone()
    if not row:
        raise RuntimeError("no Guangdong multicast record found in iptv.db")
    ip_port = row[0]
    log(f"selected Guangdong multicast: ip_port={ip_port}, source_type={row[1]}, created_at={row[3]}, id={row[4]}")
    return ip_port


def fetch_text(url: str, retries: int = 3, timeout: int = 30) -> str:
    last_error: Optional[Exception] = None
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as response:
                content = response.read()
            text = content.decode("utf-8")
            if not text.startswith("#EXTM3U"):
                raise RuntimeError("playlist response does not start with #EXTM3U")
            return text
        except (urllib.error.URLError, TimeoutError, RuntimeError) as exc:
            last_error = exc
            log(f"fetch failed ({attempt}/{retries}): {exc}")
            if attempt < retries:
                time.sleep(10)
    raise RuntimeError(f"failed to fetch playlist: {last_error}")


def fetch_grouped_playlist(base_url: str, ip_port: str) -> str:
    encoded_ip_port = urllib.parse.quote(ip_port, safe=":")
    url = f"{base_url.rstrip('/')}/playlist/m3u/{encoded_ip_port}"
    log(f"fetching grouped playlist: {url}")
    return fetch_text(url)


def atomic_write(path: Path, content: str) -> None:
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def backup_file(path: Path) -> Path:
    timestamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = path.with_name(f"{path.name}.{timestamp}.bak")
    shutil.copy2(path, backup)
    return backup


def cleanup_old_backups(path: Path, retention_seconds: int = DEFAULT_BACKUP_RETENTION_SECONDS) -> int:
    cutoff = time.time() - retention_seconds
    deleted = 0
    for backup in path.parent.glob(f"{path.name}.*.bak"):
        try:
            if backup.stat().st_mtime < cutoff:
                backup.unlink()
                deleted += 1
        except FileNotFoundError:
            continue
    return deleted


def upload_to_supabase(file_path: Path) -> bool:
    supabase_url = os.getenv("SUPABASE_URL", "").rstrip("/")
    service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    bucket = os.getenv("SUPABASE_BUCKET", "iptv-sources")
    object_name = os.getenv("SUPABASE_OBJECT_NAME", file_path.name)

    if not supabase_url or not service_role_key:
        log("Supabase upload skipped: SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY is not set")
        return False

    object_path = urllib.parse.quote(object_name, safe="/")
    upload_url = f"{supabase_url}/storage/v1/object/{bucket}/{object_path}"
    data = file_path.read_bytes()
    request = urllib.request.Request(
        upload_url,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {service_role_key}",
            "apikey": service_role_key,
            "Content-Type": "audio/x-mpegurl; charset=utf-8",
            "x-upsert": "true",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            response.read()
        log(f"uploaded to Supabase: bucket={bucket}, object={object_name}")
        return True
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Supabase upload failed: HTTP {exc.code}: {body}") from exc


def run_once(db_path: Path, m3u_path: Path, base_url: str) -> None:
    if not db_path.exists():
        raise FileNotFoundError(f"database not found: {db_path}")
    if not m3u_path.exists():
        raise FileNotFoundError(f"M3U file not found: {m3u_path}")

    ip_port = find_latest_guangdong_ip_port(db_path)
    source_playlist = fetch_grouped_playlist(base_url, ip_port)
    base_playlist = m3u_path.read_text(encoding="utf-8")
    updated_at = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    merged = merge_playlists(base_playlist, source_playlist, updated_at)
    if os.getenv("MIGU_MERGE_ENABLED", "1") != "0":
        try:
            log(f"fetching MIGU playlist: {MIGU_SOURCE_URL}")
            migu_playlist = fetch_text(MIGU_SOURCE_URL)
            merged = merge_migu_playlist(merged, migu_playlist)
        except Exception as exc:
            log(f"MIGU merge skipped: {exc}")
    backup = backup_file(m3u_path)
    log(f"backup created: {backup}")
    deleted_backups = cleanup_old_backups(m3u_path)
    if deleted_backups:
        log(f"old backups deleted: {deleted_backups}")
    atomic_write(m3u_path, merged)
    log(f"M3U updated: {m3u_path}")
    upload_to_supabase(m3u_path)


def watch(db_path: Path, m3u_path: Path, base_url: str, interval_seconds: int, settle_seconds: int) -> None:
    last_mtime = db_path.stat().st_mtime if db_path.exists() else None
    log(f"watching db={db_path}, m3u={m3u_path}, interval={interval_seconds}s")
    while True:
        time.sleep(interval_seconds)
        if not db_path.exists():
            log(f"database not found: {db_path}")
            continue
        current_mtime = db_path.stat().st_mtime
        if last_mtime is None or current_mtime != last_mtime:
            log("database mtime changed; waiting for writes to settle")
            time.sleep(settle_seconds)
            try:
                run_once(db_path, m3u_path, base_url)
                last_mtime = current_mtime
            except Exception as exc:
                log(f"update failed; original M3U preserved: {exc}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Update OneTV M3U from latest Guangdong multicast playlist.")
    parser.add_argument("--db", default=os.getenv("IPTV_DB_PATH", DEFAULT_DB_PATH), help="IPTV 数据库路径，默认可由 IPTV_DB_PATH 覆盖。")
    parser.add_argument("--m3u", default=os.getenv("ONETV_M3U_PATH", DEFAULT_M3U_PATH), help="要更新的 OneTV M3U 文件路径，默认可由 ONETV_M3U_PATH 覆盖。")
    parser.add_argument("--base-url", default=os.getenv("IPTV_SPIDER_BASE_URL", DEFAULT_INTERNAL_BASE_URL), help="IPTV-Spider 内部接口地址，默认可由 IPTV_SPIDER_BASE_URL 覆盖。")
    parser.add_argument("--interval", type=int, default=int(os.getenv("CHECK_INTERVAL_SECONDS", DEFAULT_INTERVAL_SECONDS)), help="监控模式下检查数据库变化的间隔秒数，默认可由 CHECK_INTERVAL_SECONDS 覆盖。")
    parser.add_argument("--settle", type=int, default=int(os.getenv("DB_SETTLE_SECONDS", DEFAULT_SETTLE_SECONDS)), help="检测到数据库变化后的等待秒数，默认可由 DB_SETTLE_SECONDS 覆盖。")
    parser.add_argument("--once", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    db_path = Path(args.db)
    m3u_path = Path(args.m3u)
    try:
        if args.once:
            run_once(db_path, m3u_path, args.base_url)
        else:
            watch(db_path, m3u_path, args.base_url, args.interval, args.settle)
        return 0
    except KeyboardInterrupt:
        log("stopped")
        return 130
    except Exception as exc:
        log(f"failed: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
