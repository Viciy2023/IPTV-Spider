#!/usr/bin/env python3
import argparse
import datetime as dt
import hashlib
import os
import shutil
import sqlite3
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


DEFAULT_DB_PATH = "/app/data/iptv.db"
DEFAULT_M3U_PATH = "/app/data/onetv_api_guangdong_multicast.m3u"
DEFAULT_TEMPLATE_PATH = "/app/data/onetv_api_guangdong_multicast.template.m3u"
DEFAULT_INTERVAL_SECONDS = 3 * 60
DEFAULT_SETTLE_SECONDS = 10
DEFAULT_DB_STABLE_TIMEOUT_SECONDS = 10 * 60
DEFAULT_BACKUP_RETENTION_SECONDS = 1 * 60 * 60
DEFAULT_MIGU_LIMIT = 5
DEFAULT_FIXED_CHECK_INTERVAL_SECONDS = 30 * 60
MIGU_SOURCE_URL = "http://192.168.1.20:1234/zbpro/interface.txt"
WUDALIANSAI_SOURCE_URL = "http://192.168.1.20:18765/live.m3u"
WUDALIANSAI_EXCLUDE_GROUPS = {"注意事项"}
WUDALIANSAI_CHECK_INTERVAL_SECONDS = 90
WUDALIANSAI_UPLOAD_INTERVAL_SECONDS = 10 * 60
UPDATE_LOGO_URL = "https://raw.githubusercontent.com/fanmingming/live/main/tv/CCTV13.png"
LOGO_BASE_URL = "https://raw.githubusercontent.com/fanmingming/live/main/tv"

KEEP_GROUPS = {
    "🕘️更新时间",
    "公众号【壹来了】",
    "国际频道",
    "电竞频道",
    "体育频道",
    "香港频道",
    "澳门频道",
    "台湾频道",
}

REPLACE_GROUPS = {
    "央视频道",
    "卫视频道",
    "广东频道",
    "浙江频道",
    "江苏频道",
    "黑龙江频道",
    "江西频道",
    "陕西频道",
    "安徽频道",
    "吉林频道",
    "重庆频道",
    "四川频道",
    "云南频道",
    "福建频道",
    "湖北频道",
    "新疆频道",
    "山西频道",
    "地方频道",
    "教育频道",
    "熊猫频道",
    "影视频道",
    "财经频道",
    "旅游频道",
    "生活频道",
    "纪实频道",
    "其他频道组",
    "4K节目",
    "中数传媒",
    "未分类节目",
}

MIGU_REGIONAL_GROUPS = {
    "广东地区": "广东频道",
    "浙江地区": "浙江频道",
    "江苏地区": "江苏频道",
    "黑龙江地区": "黑龙江频道",
    "江西地区": "江西频道",
    "陕西地区": "陕西频道",
    "安徽地区": "安徽频道",
    "吉林地区": "吉林频道",
    "重庆地区": "重庆频道",
    "四川地区": "四川频道",
    "云南地区": "云南频道",
    "福建地区": "福建频道",
    "湖北地区": "湖北频道",
    "新疆地区": "新疆频道",
    "山西地区": "山西频道",
}

CONTENT_GROUP_RULES = [
    (
        "体育频道",
        [
            "赛事",
            "赛场",
            "赛场原声",
            "官方解说",
            "英文原声",
            "全场回放",
            "回放",
            "主赛",
            "副赛",
            "资格赛",
            "决赛",
            "半决赛",
            "1/16决赛",
            "锦标赛",
            "公开赛",
            "大奖赛",
            "联赛",
            "总决赛",
            "杯",
            "体坛",
            "体育",
            "足球",
            "篮球",
            "蓝球",
            "排球",
            "网球",
            "羽毛球",
            "乒乓球",
            "斯诺克",
            "台球",
            "钓鱼",
            "垂钓",
            "马术",
            "格斗",
            "拳击",
            "武术",
            "跆拳道",
            "小轮车",
            "UFC",
            "Zuffa",
            "NBA",
            "CBA",
            "WTA",
            "BWF",
            "WTT",
            "UCI",
            "LGCT",
            "中超",
            "中乙",
            "城超",
            "欧冠",
            "英超",
            "西甲",
            "西乙",
            "世界杯",
            "土伦杯",
        ],
    ),
    ("教育频道", ["CETV", "教育", "中学生"]),
    ("熊猫频道", ["熊猫"]),
    ("影视频道", ["影迷", "动作电影", "电影", "影片", "影院", "放映", "放映厅", "影视", "动画", "动漫", "卡通", "卡通频道", "少儿", "轮播", "轮播台", "综艺", "综艺趴", "故事", "老故事", "梨园", "CHC"]),
    ("财经频道", ["财富", "财经", "证券", "股票", "理财", "经济"]),
    ("旅游频道", ["旅游", "环球旅游"]),
    ("生活频道", ["天气", "中华特产", "特产", "乡途", "美食", "健康", "生活"]),
    ("纪实频道", ["发现之旅", "纪实", "纪录", "探索", "航天"]),
]

LOCAL_CONTENT_KEYWORDS = [
    "新闻",
    "综合",
    "都市",
    "公共",
    "资讯",
    "自贸",
    "文旅",
    "社会与法",
    "广播电视总台",
    "教科",
    "十八频道",
]

LOCAL_KEYWORDS = [
    "北京",
    "天津",
    "上海",
    "重庆",
    "河北",
    "山西",
    "辽宁",
    "吉林",
    "黑龙江",
    "江苏",
    "浙江",
    "安徽",
    "福建",
    "江西",
    "山东",
    "河南",
    "湖北",
    "湖南",
    "广东",
    "海南",
    "四川",
    "贵州",
    "云南",
    "陕西",
    "甘肃",
    "青海",
    "内蒙古",
    "广西",
    "西藏",
    "宁夏",
    "新疆",
    "西安",
    "榆林",
    "宝鸡",
    "咸阳",
    "汉中",
    "安康",
    "延安",
    "渭南",
    "商洛",
    "铜川",
    "海口",
    "三亚",
    "儋州",
    "南京",
    "盐城",
    "淮安",
    "泰州",
    "连云港",
    "宿迁",
    "徐州",
    "江阴",
    "南通",
    "宜兴",
    "溧水",
    "镇江",
    "深圳",
    "广州",
]

FIXED_SOURCE_GROUPS = {
    "央视频道",
    "卫视频道",
    "超清频道",
    "其他频道组",
    "未分类节目",
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
    "安徽频道",
    "吉林频道",
    "重庆频道",
    "四川频道",
    "云南频道",
    "福建频道",
    "湖北频道",
    "新疆频道",
    "山西频道",
    "地方频道",
    "体育频道",
    "教育频道",
    "熊猫频道",
    "影视频道",
    "财经频道",
    "旅游频道",
    "生活频道",
    "纪实频道",
    "其他频道组",
    "4K节目",
    "中数传媒",
    "国际频道",
    "电竞频道",
    "香港频道",
    "澳门频道",
    "台湾频道",
]


@dataclass
class MiguSource:
    id: int
    ip_port: str
    source_type: str
    channel_lists: str
    status: str
    created_at: str


@dataclass
class Entry:
    extinf: str
    url: str
    group: str
    name: str
    priority: int = 1


def log(message: str) -> None:
    print(f"[{dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}", flush=True)


def now() -> dt.datetime:
    return dt.datetime.now()


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def is_fixed_check_due(current: dt.datetime, last_check: Optional[dt.datetime], interval_seconds: int) -> bool:
    return last_check is None or (current - last_check).total_seconds() >= interval_seconds


def extract_group(extinf: str) -> str:
    marker = 'group-title="'
    start = extinf.find(marker)
    if start == -1:
        return ""
    start += len(marker)
    end = extinf.find('"', start)
    return extinf[start:end] if end != -1 else ""


def entry_name(extinf: str) -> str:
    return extinf.rsplit(",", 1)[-1].strip() if "," in extinf else ""


def parse_m3u(text: str) -> tuple[str, list[Entry]]:
    lines = text.splitlines()
    header = lines[0] if lines and lines[0].startswith("#EXTM3U") else "#EXTM3U"
    entries: list[Entry] = []
    i = 1 if lines and lines[0].startswith("#EXTM3U") else 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("#EXTINF") and i + 1 < len(lines):
            group = extract_group(line)
            entries.append(Entry(line, lines[i + 1], group, entry_name(line)))
            i += 2
        else:
            i += 1
    return header, entries


CCTV_SUFFIXES = ("新闻", "综合", "财经", "体育", "电影", "纪录", "科教", "少儿", "戏曲", "音乐", "农业农村", "国防军事")


def normalize_channel(name: str) -> str:
    normalized = name.strip()
    if normalized.startswith("CCTV"):
        if normalized.startswith("CCTV5+"):
            return "CCTV5+"
        digits = ""
        rest_after_digits = ""
        for char in normalized[4:]:
            if char.isdigit():
                digits += char
            else:
                rest_after_digits = normalized[4 + len(digits):]
                break
        if digits:
            if not rest_after_digits:
                return f"CCTV{digits}"
            for suffix in CCTV_SUFFIXES:
                if rest_after_digits == suffix:
                    return f"CCTV{digits}"
    if normalized.endswith("4K"):
        normalized = normalized[:-2].strip()
    return normalized


def infer_group(name: str) -> str:
    if name.startswith("CCTV") or name.startswith("CGTN"):
        return "央视频道"
    if name.endswith("卫视"):
        return "卫视频道"
    if any(keyword in name for keyword in LOCAL_KEYWORDS) and any(keyword in name for keyword in LOCAL_CONTENT_KEYWORDS):
        return "地方频道"
    if any(keyword in name for keyword in LOCAL_CONTENT_KEYWORDS) and "频道" in name:
        return "地方频道"
    for group, keywords in CONTENT_GROUP_RULES:
        if any(keyword in name for keyword in keywords):
            return group
    if any(keyword in name for keyword in LOCAL_KEYWORDS):
        return "地方频道"
    return "其他频道组"


def map_fixed_group(source_group: str, normalized_name: str) -> str:
    if source_group in MIGU_REGIONAL_GROUPS:
        return MIGU_REGIONAL_GROUPS[source_group]
    if source_group == "超清频道":
        return "央视频道" if normalized_name.startswith("CCTV") else "卫视频道"
    if source_group == "未分类节目":
        return infer_group(normalized_name)
    if source_group == "其他频道组":
        return infer_group(normalized_name)
    return source_group


def metadata(group: str, name: str) -> str:
    return f'#EXTINF:-1 group-title="{group}" tvg-logo="{LOGO_BASE_URL}/{name}.png",{name}'


def update_entry(group: str, updated_at: str, url: str, priority: int) -> Entry:
    name = f"ONETV更新日期: {updated_at}"
    extinf = f'#EXTINF:-1 group-title="{group}" tvg-logo="{UPDATE_LOGO_URL}",{name}'
    return Entry(extinf, url, group, name, priority)


def load_latest_migu_sources(db_path: Path, limit: int = DEFAULT_MIGU_LIMIT) -> list[MiguSource]:
    query = """
        SELECT id, ip_port, source_type, channel_lists, status, created_at
        FROM iptv
        WHERE type = 'migu'
          AND COALESCE(status, '') NOT LIKE '%失效%'
          AND COALESCE(channel_lists, '') <> ''
        ORDER BY created_at DESC, id DESC
        LIMIT ?
    """
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(query, (limit,)).fetchall()
    finally:
        conn.close()
    return [MiguSource(row[0], row[1], row[2] or "", row[3] or "", row[4] or "", row[5] or "") for row in rows]


EXCLUDE_CHANNELS = {"CHC动作电影"}


def entries_from_db_sources(sources: list[MiguSource]) -> list[Entry]:
    entries: list[Entry] = []
    seen: set[tuple[str, str, str]] = set()
    for source_index, source in enumerate(sources):
        for line in source.channel_lists.splitlines():
            if not line.strip() or "," not in line:
                continue
            raw_name, url = line.split(",", 1)
            normalized_name = normalize_channel(raw_name)
            if normalized_name in EXCLUDE_CHANNELS:
                continue
            group = infer_group(normalized_name)
            key = (group, normalized_name, url.strip())
            if key in seen:
                continue
            seen.add(key)
            entries.append(Entry(metadata(group, normalized_name), url.strip(), group, normalized_name, source_index))
    return entries


def entries_from_fixed_playlist(fixed_text: str) -> tuple[list[Entry], str, str]:
    _, fixed_entries = parse_m3u(fixed_text)
    entries: list[Entry] = []
    seen: set[tuple[str, str, str]] = set()
    update_date = ""
    cctv13_url = ""
    for entry in fixed_entries:
        if entry.group not in FIXED_SOURCE_GROUPS:
            continue
        raw_name = entry.name
        if raw_name.startswith("更新日期:"):
            update_date = raw_name.removeprefix("更新日期:").strip()
            continue
        normalized_name = normalize_channel(raw_name)
        group = map_fixed_group(entry.group, normalized_name)
        key = (group, normalized_name, entry.url)
        if key in seen:
            continue
        seen.add(key)
        entries.append(Entry(metadata(group, normalized_name), entry.url, group, normalized_name, 10))
        if normalized_name == "CCTV13" and not cctv13_url:
            cctv13_url = entry.url
    return entries, update_date, cctv13_url


def entries_from_wudaliansai_source(wudaliansai_text: str) -> tuple[list[Entry], list[str]]:
    _, wudaliansai_entries = parse_m3u(wudaliansai_text)
    entries: list[Entry] = []
    seen_groups: list[str] = []
    seen_keys: set[tuple[str, str, str]] = set()
    for entry in wudaliansai_entries:
        if entry.group in WUDALIANSAI_EXCLUDE_GROUPS:
            continue
        if entry.group not in seen_groups:
            seen_groups.append(entry.group)
        key = (entry.group, entry.name, entry.url)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        entries.append(Entry(entry.extinf, entry.url, entry.group, entry.name, 3))
    return entries, seen_groups


def build_final_group_order(wudaliansai_groups: list[str]) -> list[str]:
    order = list(FINAL_GROUP_ORDER)
    insert_index = order.index("央视频道")
    for group in wudaliansai_groups:
        if group not in order:
            order.insert(insert_index, group)
            insert_index += 1
    return order


def cctv13_update_entries(group: str, updated_at: str, dynamic_entries: list[Entry], fixed_entries: list[Entry]) -> list[Entry]:
    entries: list[Entry] = []
    seen_urls: set[str] = set()
    for entry in dynamic_entries:
        if entry.group == "央视频道" and entry.name == "CCTV13" and entry.url not in seen_urls:
            seen_urls.add(entry.url)
            entries.append(update_entry(group, updated_at, entry.url, -100 + entry.priority))
    for entry in fixed_entries:
        if entry.group == "央视频道" and entry.name == "CCTV13" and entry.url not in seen_urls:
            seen_urls.add(entry.url)
            entries.append(update_entry(group, updated_at, entry.url, -90 + entry.priority))
    if not entries:
        entries.append(update_entry(group, updated_at, "https://proshls.wns.live/hls/stream.m3u8", -1))
    return entries


def should_drop_template_entry(entry: Entry) -> bool:
    if entry.group in REPLACE_GROUPS:
        return True
    if entry.group in {"🕘️更新时间", "公众号【壹来了】"}:
        return entry.name.startswith("ONETV更新日期:") or entry.name.startswith("MIGU更新日期:")
    return False


def build_playlist(template_text: str, db_sources: list[MiguSource], fixed_text: str, updated_at: str, wudaliansai_text: str = "") -> str:
    header, template_entries = parse_m3u(template_text)
    dynamic_entries = entries_from_db_sources(db_sources)
    fixed_entries, fixed_update_date, _cctv13_url = entries_from_fixed_playlist(fixed_text)
    wudaliansai_entries, wudaliansai_groups = entries_from_wudaliansai_source(wudaliansai_text) if wudaliansai_text else ([], [])
    output_entries: list[Entry] = []
    update_label = updated_at or fixed_update_date or dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    output_entries.extend(cctv13_update_entries("🕘️更新时间", update_label, dynamic_entries, fixed_entries))
    output_entries.extend(cctv13_update_entries("公众号【壹来了】", update_label, dynamic_entries, fixed_entries))
    for entry in template_entries:
        if not should_drop_template_entry(entry) and entry.group in KEEP_GROUPS:
            output_entries.append(entry)
    output_entries.extend(dynamic_entries)
    output_entries.extend(fixed_entries)
    output_entries.extend(wudaliansai_entries)
    final_order = build_final_group_order(wudaliansai_groups)
    group_rank = {group: index for index, group in enumerate(final_order)}
    output_entries.sort(key=lambda entry: (group_rank.get(entry.group, len(group_rank)), entry.priority, 1 if "超清" in entry.name else 0))
    output = [header]
    for entry in output_entries:
        output.extend([entry.extinf, entry.url])
    return "\n".join(output) + "\n"


def fetch_text(url: str, retries: int = 3, timeout: int = 30) -> str:
    last_error: Optional[Exception] = None
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as response:
                text = response.read().decode("utf-8")
            if not text.startswith("#EXTM3U"):
                raise RuntimeError("playlist response does not start with #EXTM3U")
            return text
        except (urllib.error.URLError, TimeoutError, RuntimeError) as exc:
            last_error = exc
            log(f"fetch failed ({attempt}/{retries}): {exc}")
            if attempt < retries:
                time.sleep(10)
    raise RuntimeError(f"failed to fetch playlist: {last_error}")


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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
    request = urllib.request.Request(
        upload_url,
        data=file_path.read_bytes(),
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


def run_once(db_path: Path, m3u_path: Path, template_path: Path, migu_url: str = MIGU_SOURCE_URL, wudaliansai_text: str = "") -> bool:
    if not db_path.exists():
        raise FileNotFoundError(f"database not found: {db_path}")
    if not template_path.exists():
        raise FileNotFoundError(f"template M3U not found: {template_path}")
    template_text = template_path.read_text(encoding="utf-8")
    current_text = m3u_path.read_text(encoding="utf-8") if m3u_path.exists() else ""
    sources = load_latest_migu_sources(db_path, DEFAULT_MIGU_LIMIT)
    log(f"loaded MIGU source groups: {len(sources)}")
    try:
        fixed_text = fetch_text(migu_url)
    except Exception as exc:
        log(f"fixed MIGU fetch failed; update skipped to preserve current M3U: {exc}")
        return False
    updated_at = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    merged = build_playlist(template_text, sources, fixed_text, updated_at, wudaliansai_text)
    if merged == current_text:
        log(f"M3U unchanged; upload skipped: {m3u_path}")
        return False
    if m3u_path.exists():
        backup = backup_file(m3u_path)
        log(f"backup created: {backup}")
        deleted = cleanup_old_backups(m3u_path)
        if deleted:
            log(f"old backups deleted: {deleted}")
    atomic_write(m3u_path, merged)
    log(f"M3U updated: {m3u_path}")
    upload_to_supabase(m3u_path)
    return True


def wait_for_stable_db_mtime(db_path: Path, stable_seconds: int, timeout_seconds: int) -> float:
    waited = 0
    last_mtime = db_path.stat().st_mtime
    while waited < timeout_seconds:
        time.sleep(stable_seconds)
        waited += stable_seconds
        current_mtime = db_path.stat().st_mtime
        if current_mtime == last_mtime:
            return current_mtime
        last_mtime = current_mtime
    return last_mtime


def watch(
    db_path: Path,
    m3u_path: Path,
    template_path: Path,
    interval_seconds: int,
    settle_seconds: int,
    fixed_check_interval_seconds: int = DEFAULT_FIXED_CHECK_INTERVAL_SECONDS,
    wudaliansai_check_interval_seconds: int = WUDALIANSAI_CHECK_INTERVAL_SECONDS,
) -> None:
    last_mtime = db_path.stat().st_mtime if db_path.exists() else None
    last_fixed_hash: Optional[str] = None
    last_fixed_check: Optional[dt.datetime] = None
    last_wudaliansai_hash: Optional[str] = None
    last_wudaliansai_check: Optional[dt.datetime] = None
    current_wudaliansai_text: str = ""
    wudaliansai_pending_upload = False
    wudaliansai_last_change: Optional[dt.datetime] = None
    log(f"watching db={db_path}, m3u={m3u_path}, template={template_path}, interval={interval_seconds}s")
    try:
        try:
            last_fixed_hash = content_hash(fetch_text(MIGU_SOURCE_URL))
            last_fixed_check = now()
        except Exception as exc:
            log(f"fixed source baseline check skipped: {exc}")
        try:
            wudaliansai_text = fetch_text(WUDALIANSAI_SOURCE_URL, retries=2, timeout=10)
            current_wudaliansai_text = wudaliansai_text
            last_wudaliansai_hash = content_hash(wudaliansai_text)
            last_wudaliansai_check = now()
            log("wudaliansai source baseline loaded")
        except Exception as exc:
            log(f"wudaliansai source baseline check skipped: {exc}")
        run_once(db_path, m3u_path, template_path, wudaliansai_text=current_wudaliansai_text)
    except Exception as exc:
        log(f"startup update failed; original M3U preserved: {exc}")
    while True:
        time.sleep(interval_seconds)
        if not db_path.exists():
            log(f"database not found: {db_path}")
            continue
        current_mtime = db_path.stat().st_mtime
        if last_mtime is None or current_mtime != last_mtime:
            log("database mtime changed; waiting for writes to settle")
            current_mtime = wait_for_stable_db_mtime(db_path, settle_seconds, DEFAULT_DB_STABLE_TIMEOUT_SECONDS)
            try:
                run_once(db_path, m3u_path, template_path, wudaliansai_text=current_wudaliansai_text)
                last_mtime = current_mtime
            except Exception as exc:
                log(f"update failed; original M3U preserved: {exc}")
            continue
        current_time = now()
        if is_fixed_check_due(current_time, last_fixed_check, fixed_check_interval_seconds):
            try:
                fixed_text = fetch_text(MIGU_SOURCE_URL)
                fixed_hash = content_hash(fixed_text)
                last_fixed_check = current_time
                if last_fixed_hash is None:
                    last_fixed_hash = fixed_hash
                elif fixed_hash != last_fixed_hash:
                    log("fixed MIGU source changed; starting sync")
                    run_once(db_path, m3u_path, template_path, wudaliansai_text=current_wudaliansai_text)
                    last_fixed_hash = fixed_hash
            except Exception as exc:
                log(f"fixed source change check skipped: {exc}")
        if is_fixed_check_due(current_time, last_wudaliansai_check, wudaliansai_check_interval_seconds):
            try:
                wudaliansai_text = fetch_text(WUDALIANSAI_SOURCE_URL, retries=2, timeout=10)
                wudaliansai_hash = content_hash(wudaliansai_text)
                last_wudaliansai_check = current_time
                if last_wudaliansai_hash is None:
                    last_wudaliansai_hash = wudaliansai_hash
                    current_wudaliansai_text = wudaliansai_text
                    run_once(db_path, m3u_path, template_path, wudaliansai_text=current_wudaliansai_text)
                elif wudaliansai_hash != last_wudaliansai_hash:
                    log("wudaliansai source changed; updating M3U")
                    current_wudaliansai_text = wudaliansai_text
                    run_once(db_path, m3u_path, template_path, wudaliansai_text=current_wudaliansai_text)
                    last_wudaliansai_hash = wudaliansai_hash
                    wudaliansai_pending_upload = True
                    wudaliansai_last_change = current_time
            except Exception as exc:
                log(f"wudaliansai source check skipped: {exc}")
        if wudaliansai_pending_upload and wudaliansai_last_change is not None:
            if (current_time - wudaliansai_last_change).total_seconds() >= WUDALIANSAI_UPLOAD_INTERVAL_SECONDS:
                try:
                    upload_to_supabase(m3u_path)
                    log("wudaliansai delayed upload completed")
                except Exception as exc:
                    log(f"wudaliansai delayed upload failed: {exc}")
                wudaliansai_pending_upload = False
                wudaliansai_last_change = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Update OneTV M3U from latest MIGU source groups in IPTV-Spider database.")
    parser.add_argument("--db", default=os.getenv("IPTV_DB_PATH", DEFAULT_DB_PATH))
    parser.add_argument("--m3u", default=os.getenv("ONETV_M3U_PATH", DEFAULT_M3U_PATH))
    parser.add_argument("--template", default=os.getenv("ONETV_TEMPLATE_PATH", DEFAULT_TEMPLATE_PATH))
    parser.add_argument("--interval", type=int, default=int(os.getenv("CHECK_INTERVAL_SECONDS", DEFAULT_INTERVAL_SECONDS)))
    parser.add_argument("--settle", type=int, default=int(os.getenv("DB_SETTLE_SECONDS", DEFAULT_SETTLE_SECONDS)))
    parser.add_argument(
        "--fixed-check-interval",
        type=int,
        default=int(os.getenv("FIXED_CHECK_INTERVAL_SECONDS", DEFAULT_FIXED_CHECK_INTERVAL_SECONDS)),
    )
    parser.add_argument(
        "--wudaliansai-check-interval",
        type=int,
        default=int(os.getenv("WUDALIANSAI_CHECK_INTERVAL_SECONDS", WUDALIANSAI_CHECK_INTERVAL_SECONDS)),
    )
    parser.add_argument("--once", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    db_path = Path(args.db)
    m3u_path = Path(args.m3u)
    template_path = Path(args.template)
    try:
        if args.once:
            run_once(db_path, m3u_path, template_path)
        else:
            watch(db_path, m3u_path, template_path, args.interval, args.settle, args.fixed_check_interval, args.wudaliansai_check_interval)
        return 0
    except KeyboardInterrupt:
        log("stopped")
        return 130
    except Exception as exc:
        log(f"failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
