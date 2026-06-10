"""工具函数模块

提供数据加载、保存、校验等通用工具函数。
"""

import os
import json
import pickle
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path

import pandas as pd


DEFAULT_DATA_DIR = ".sports_grade_data"
DEFAULT_MAPS_DIR = Path(DEFAULT_DATA_DIR) / "maps"


def get_maps_dir() -> Path:
    DEFAULT_MAPS_DIR.mkdir(parents=True, exist_ok=True)
    return DEFAULT_MAPS_DIR


def list_map_templates() -> List[str]:
    maps_dir = get_maps_dir()
    if not maps_dir.exists():
        return []
    return sorted([f.stem for f in maps_dir.glob("*.json")])


def save_map_template(name: str, mapping: Dict[str, str]) -> Path:
    maps_dir = get_maps_dir()
    path = maps_dir / f"{name}.json"
    save_json(mapping, path)
    return path


def load_map_template(name: str) -> Optional[Dict[str, str]]:
    maps_dir = get_maps_dir()
    path = maps_dir / f"{name}.json"
    if not path.exists():
        return None
    return load_json(path)


def delete_map_template(name: str) -> bool:
    maps_dir = get_maps_dir()
    path = maps_dir / f"{name}.json"
    if path.exists():
        path.unlink()
        return True
    return False


def get_data_path(semester: str, grade: str, filename: str) -> Path:
    base = Path(DEFAULT_DATA_DIR) / semester / grade
    base.mkdir(parents=True, exist_ok=True)
    return base / filename


def save_dataframe(df: pd.DataFrame, path: Path) -> None:
    suffix = path.suffix.lower()
    if suffix in [".xlsx", ".xls"]:
        df.to_excel(path, index=False)
    elif suffix == ".csv":
        df.to_csv(path, index=False, encoding="utf-8-sig")
    elif suffix == ".json":
        df.to_json(path, orient="records", force_ascii=False, indent=2)
    else:
        df.to_pickle(path)


def save_workbook(sheets: List[Tuple[str, pd.DataFrame]], path: Path) -> None:
    suffix = path.suffix.lower()
    if suffix not in [".xlsx", ".xls"]:
        raise ValueError(f"工作簿模式仅支持 Excel 格式，当前: {suffix}")

    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for sheet_name, df in sheets:
            safe_name = str(sheet_name)[:31]
            df.to_excel(writer, sheet_name=safe_name, index=False)


def load_dataframe(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix in [".xlsx", ".xls"]:
        return pd.read_excel(path)
    elif suffix == ".csv":
        return pd.read_csv(path, encoding="utf-8-sig")
    elif suffix == ".json":
        return pd.read_json(path, orient="records")
    else:
        return pd.read_pickle(path)


def save_pickle(obj: Any, path: Path) -> None:
    with open(path, "wb") as f:
        pickle.dump(obj, f)


def load_pickle(path: Path) -> Any:
    with open(path, "rb") as f:
        return pickle.load(f)


def save_json(obj: Any, path: Path) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def load_json(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def parse_time_to_seconds(time_str: str) -> Optional[int]:
    if pd.isna(time_str) or time_str is None or str(time_str).strip() == "":
        return None
    time_str = str(time_str).strip()
    try:
        if "'" in time_str or '"' in time_str:
            parts = time_str.replace('"', "").split("'")
            if len(parts) == 2:
                minutes = int(parts[0])
                seconds = float(parts[1]) if parts[1] else 0
                return int(minutes * 60 + seconds)
        if ":" in time_str:
            parts = time_str.split(":")
            if len(parts) == 2:
                minutes = int(parts[0])
                seconds = float(parts[1])
                return int(minutes * 60 + seconds)
            elif len(parts) == 3:
                hours = int(parts[0])
                minutes = int(parts[1])
                seconds = float(parts[2])
                return int(hours * 3600 + minutes * 60 + seconds)
        return int(float(time_str))
    except (ValueError, TypeError):
        return None


def seconds_to_time_str(seconds: Optional[int]) -> str:
    if seconds is None or pd.isna(seconds):
        return ""
    seconds = int(seconds)
    if seconds >= 60:
        mins = seconds // 60
        secs = seconds % 60
        return f"{mins}'{secs:02d}\""
    return str(seconds)


def format_number(value, decimals: int = 1) -> str:
    if value is None or pd.isna(value):
        return ""
    try:
        return f"{float(value):.{decimals}f}"
    except (ValueError, TypeError):
        return str(value)


def ensure_output_dir(output_dir: str) -> Path:
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def print_table(df: pd.DataFrame, max_rows: int = 20) -> None:
    if df.empty:
        print("(空数据)")
        return
    display_df = df.head(max_rows)
    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", None)
    pd.set_option("display.max_colwidth", 20)
    pd.set_option("display.unicode.ambiguous_as_wide", True)
    pd.set_option("display.unicode.east_asian_width", True)
    print(display_df.to_string(index=False))
    if len(df) > max_rows:
        print(f"\n... 共 {len(df)} 条记录，仅显示前 {max_rows} 条")


def get_column_mapping() -> Dict[str, List[str]]:
    return {
        "student_id": ["学号", "student_id", "id", "编号"],
        "name": ["姓名", "name", "学生姓名"],
        "gender": ["性别", "gender", "sex"],
        "class_name": ["班级", "class", "class_name", "班"],
        "grade": ["年级", "grade"],
        "height": ["身高", "height", "身高(cm)"],
        "weight": ["体重", "weight", "体重(kg)"],
        "bmi": ["BMI", "bmi", "身高体重指数"],
        "vital_capacity": ["肺活量", "vital_capacity", "vc"],
        "run_50m": ["50米跑", "50m", "50米", "run_50m"],
        "standing_jump": ["立定跳远", "standing_jump", "跳远"],
        "sit_and_reach": ["坐位体前屈", "sit_and_reach", "体前屈"],
        "pull_up": ["引体向上", "pull_up", "引体"],
        "sit_up": ["仰卧起坐", "sit_up", "仰卧起"],
        "run_1000m": ["1000米跑", "1000m", "1000米", "run_1000m"],
        "run_800m": ["800米跑", "800m", "800米", "run_800m"],
    }


def auto_rename_columns(df: pd.DataFrame) -> pd.DataFrame:
    mapping = get_column_mapping()
    reverse_map = {}
    for std_name, aliases in mapping.items():
        for alias in aliases:
            reverse_map[alias.lower().strip()] = std_name
            reverse_map[alias] = std_name
    
    new_columns = []
    for col in df.columns:
        col_str = str(col).strip()
        if col_str in reverse_map:
            new_columns.append(reverse_map[col_str])
        elif col_str.lower() in reverse_map:
            new_columns.append(reverse_map[col_str.lower()])
        else:
            new_columns.append(col_str)
    df.columns = new_columns
    return df


def calculate_bmi(height, weight):
    if pd.isna(height) or pd.isna(weight):
        return None
    try:
        h = float(height) / 100.0
        w = float(weight)
        if h <= 0:
            return None
        return round(w / (h * h), 1)
    except (ValueError, TypeError, ZeroDivisionError):
        return None


def is_numeric_value(value) -> bool:
    if value is None or pd.isna(value):
        return False
    try:
        float(value)
        return True
    except (ValueError, TypeError):
        return False
