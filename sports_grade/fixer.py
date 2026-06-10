"""数据修正模块

支持按学号补录某个项目成绩、修改班级或性别。
修正后自动重新评分并保留操作记录。
"""

from typing import Dict, Optional
from datetime import datetime
from pathlib import Path

import pandas as pd

from .standards import PROJECTS, PROJECT_NAMES, GENDERS
from .scorer import calculate_individual_scores, calculate_total_score, calculate_class_stats
from .standards import get_score_level
from .utils import (
    get_data_path,
    load_pickle,
    save_pickle,
    save_json,
    print_table,
)


def fix_record(
    semester: str,
    grade: Optional[str] = None,
    student_id: Optional[str] = None,
    project: Optional[str] = None,
    value: Optional[str] = None,
    class_name: Optional[str] = None,
    gender: Optional[str] = None,
    preview: bool = False,
) -> Dict:
    grade_key = grade or "all"

    scored_path = get_data_path(semester, grade_key, "scored_data.pkl")
    raw_path = get_data_path(semester, grade_key, "raw_data.pkl")

    if scored_path.exists():
        df = load_pickle(scored_path)
        data_source = "scored_data"
    elif raw_path.exists():
        df = load_pickle(raw_path)
        data_source = "raw_data"
    else:
        raise FileNotFoundError(
            f"未找到数据，请先执行 import 命令。\n"
            f"期望路径: {raw_path}"
        )

    if student_id is None:
        raise ValueError("必须指定 --id（学号）")

    mask = df["student_id"] == student_id
    if not mask.any():
        raise ValueError(f"未找到学号为 {student_id} 的学生")

    row_idx = df[mask].index[0]
    old_values = {}

    changes_made = False

    if project and value is not None:
        if project not in PROJECTS:
            raise ValueError(f"无效项目: {project}，可选值: {', '.join(PROJECTS)}")

        if project not in df.columns:
            df[project] = None

        from .utils import parse_time_to_seconds

        old_val = df.at[row_idx, project]
        old_values[project] = old_val

        if project in ["run_50m", "run_1000m", "run_800m"]:
            new_val = parse_time_to_seconds(value)
            if new_val is None:
                try:
                    new_val = float(value)
                except (ValueError, TypeError):
                    raise ValueError(f"无效的时间值: {value}")
        elif project in ["bmi", "sit_and_reach"]:
            try:
                new_val = float(value)
            except (ValueError, TypeError):
                raise ValueError(f"无效的数值: {value}")
        elif project in ["vital_capacity", "standing_jump", "pull_up", "sit_up"]:
            try:
                new_val = int(float(value))
            except (ValueError, TypeError):
                raise ValueError(f"无效的整数值: {value}")
        else:
            try:
                new_val = float(value)
            except (ValueError, TypeError):
                new_val = value

        df.at[row_idx, project] = new_val
        changes_made = True
        proj_name = PROJECT_NAMES.get(project, project)
        print(f"✓ 修改成绩: {student_id} {proj_name}  {old_val} → {new_val}")

    if class_name is not None:
        old_val = df.at[row_idx, "class_name"]
        old_values["class_name"] = old_val
        df.at[row_idx, "class_name"] = class_name
        changes_made = True
        print(f"✓ 修改班级: {student_id}  {old_val} → {class_name}")

    if gender is not None:
        if gender not in GENDERS:
            raise ValueError(f"无效性别: {gender}，可选: 男、女")
        old_val = df.at[row_idx, "gender"]
        old_values["gender"] = old_val
        df.at[row_idx, "gender"] = gender
        changes_made = True
        print(f"✓ 修改性别: {student_id}  {old_val} → {gender}")

    if not changes_made:
        print("未做任何修改（需要指定 --project + --value 或 --class 或 --gender）")
        return {"modified": False}

    print("\n修改后数据:")
    info_cols = [c for c in ["student_id", "name", "gender", "class_name", "grade"] if c in df.columns]
    project_cols = [p for p in PROJECTS if p in df.columns]
    print_table(df.loc[[row_idx]][info_cols + project_cols])

    df = calculate_individual_scores(df)
    df["total_score"] = df.apply(calculate_total_score, axis=1)
    df["level"] = df["total_score"].apply(
        lambda x: get_score_level(x) if pd.notna(x) else None
    )

    new_score = df.at[row_idx, "total_score"]
    new_level = df.at[row_idx, "level"]
    print(f"\n重新评分: 总分={new_score}  等级={new_level}")

    if not preview:
        save_pickle(df, scored_path)
        print(f"数据已更新保存: {scored_path}")

        raw_df = load_pickle(raw_path) if raw_path.exists() else df.copy()
        if project and value is not None and project in raw_df.columns:
            raw_df.at[raw_df[raw_df["student_id"] == student_id].index[0], project] = df.at[row_idx, project]
        if class_name is not None and "class_name" in raw_df.columns:
            raw_df.at[raw_df[raw_df["student_id"] == student_id].index[0], "class_name"] = class_name
        if gender is not None and "gender" in raw_df.columns:
            raw_df.at[raw_df[raw_df["student_id"] == student_id].index[0], "gender"] = gender
        save_pickle(raw_df, raw_path)

        class_stats = calculate_class_stats(df)
        if not class_stats.empty:
            class_stats_path = get_data_path(semester, grade_key, "class_stats.pkl")
            save_pickle(class_stats, class_stats_path)

        log_entry = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "semester": semester,
            "grade": grade,
            "student_id": student_id,
            "changes": old_values,
            "new_score": round(new_score, 1) if pd.notna(new_score) else None,
            "new_level": new_level,
        }
        log_path = get_data_path(semester, grade_key, "fix_log.json")
        existing_log = []
        if log_path.exists():
            from .utils import load_json
            existing_log = load_json(log_path)
            if not isinstance(existing_log, list):
                existing_log = []
        existing_log.append(log_entry)
        save_json(existing_log, log_path)
        print(f"操作记录已保存: {log_path}")

    return {
        "modified": True,
        "student_id": student_id,
        "old_values": old_values,
        "new_score": new_score,
        "new_level": new_level,
    }


def show_fix_log(
    semester: str,
    grade: Optional[str] = None,
) -> None:
    grade_key = grade or "all"
    log_path = get_data_path(semester, grade_key, "fix_log.json")

    if not log_path.exists():
        print("暂无修正记录")
        return

    from .utils import load_json
    log = load_json(log_path)

    if not log:
        print("暂无修正记录")
        return

    print(f"\n修正操作记录（共 {len(log)} 条）:")
    print("=" * 60)
    for i, entry in enumerate(log, 1):
        print(f"\n[{i}] {entry.get('timestamp', '')}")
        print(f"    学号: {entry.get('student_id', '')}")
        changes = entry.get("changes", {})
        for field, old_val in changes.items():
            print(f"    修改 {field}: 原值={old_val}")
        print(f"    修正后: 总分={entry.get('new_score')}  等级={entry.get('new_level')}")
