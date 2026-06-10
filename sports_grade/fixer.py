"""数据修正模块

支持按学号补录某个项目成绩、修改班级或性别。
修正后自动重新评分并保留操作记录（原值、新值、时间戳）。
补录的新项目会同步到 raw_data，确保后续重新 score/rank/export 时仍然保留。

查看修正记录支持：
- 按学号过滤
- 按项目过滤
- 按日期范围过滤（YYYY-MM-DD ~ YYYY-MM-DD）
- 一键导出为 Excel/CSV 留档
"""

from typing import Dict, List, Optional
from datetime import datetime
from pathlib import Path

import pandas as pd

from .standards import PROJECTS, PROJECT_NAMES, GENDERS, get_score_level
from .scorer import calculate_individual_scores, calculate_total_score, calculate_class_stats
from .utils import (
    get_data_path,
    load_pickle,
    save_pickle,
    save_json,
    load_json,
    save_dataframe,
    ensure_output_dir,
    print_table,
    parse_time_to_seconds,
)


def _coerce_value(project: str, value: str):
    if value is None or (isinstance(value, float) and value != value):
        return None

    val_str = str(value).strip()
    if val_str == "":
        return None

    if project in ["run_50m", "run_1000m", "run_800m"]:
        result = parse_time_to_seconds(val_str)
        if result is None:
            try:
                result = float(val_str)
            except (ValueError, TypeError):
                raise ValueError(f"无效的时间值: {value}")
        return result

    elif project in ["bmi", "sit_and_reach"]:
        try:
            return float(val_str)
        except (ValueError, TypeError):
            raise ValueError(f"无效的数值: {value}")

    elif project in ["vital_capacity", "standing_jump", "pull_up", "sit_up"]:
        try:
            return int(float(val_str))
        except (ValueError, TypeError):
            raise ValueError(f"无效的整数值: {value}")

    else:
        try:
            return float(val_str)
        except (ValueError, TypeError):
            return val_str


def _format_value_for_display(project: str, value) -> str:
    if value is None or (isinstance(value, float) and value != value):
        return "(空)"

    if project in ["run_50m", "run_1000m", "run_800m"]:
        from .utils import seconds_to_time_str
        try:
            return seconds_to_time_str(int(float(value)))
        except (ValueError, TypeError):
            return str(value)

    if project in ["bmi", "sit_and_reach"]:
        try:
            return f"{float(value):.1f}"
        except (ValueError, TypeError):
            return str(value)

    return str(value)


def fix_record(
    semester: str,
    grade: Optional[str] = None,
    student_id: Optional[str] = None,
    project: Optional[str] = None,
    value: Optional[str] = None,
    class_name: Optional[str] = None,
    gender: Optional[str] = None,
    note: Optional[str] = None,
    preview: bool = False,
) -> Dict:
    grade_key = grade or "all"

    scored_path = get_data_path(semester, grade_key, "scored_data.pkl")
    raw_path = get_data_path(semester, grade_key, "raw_data.pkl")

    if not raw_path.exists():
        raise FileNotFoundError(
            f"未找到原始数据，请先执行 import 命令。\n"
            f"期望路径: {raw_path}"
        )

    raw_df = load_pickle(raw_path)

    if student_id is None:
        raise ValueError("必须指定 --id（学号）")

    raw_mask = raw_df["student_id"] == student_id
    if not raw_mask.any():
        raise ValueError(f"未找到学号为 {student_id} 的学生")

    raw_row_idx = raw_df[raw_mask].index[0]
    changes = []

    if project and value is not None:
        if project not in PROJECTS:
            raise ValueError(f"无效项目: {project}，可选值: {', '.join(PROJECTS)}")

        if project not in raw_df.columns:
            raw_df[project] = None

        old_raw = raw_df.at[raw_row_idx, project]
        new_val = _coerce_value(project, value)
        raw_df.at[raw_row_idx, project] = new_val

        proj_name = PROJECT_NAMES.get(project, project)
        old_disp = _format_value_for_display(project, old_raw)
        new_disp = _format_value_for_display(project, new_val)
        print(f"✓ 修正成绩: {proj_name}")
        print(f"    原值: {old_disp}  →  新值: {new_disp}")
        changes.append({
            "field": project,
            "field_name": proj_name,
            "type": "project_score",
            "old_value": old_raw if not isinstance(old_raw, float) or old_raw == old_raw else None,
            "new_value": new_val,
            "old_display": old_disp,
            "new_display": new_disp,
        })

    if class_name is not None:
        old_val = raw_df.at[raw_row_idx, "class_name"]
        raw_df.at[raw_row_idx, "class_name"] = class_name
        print(f"✓ 修正班级: {old_val}  →  {class_name}")
        changes.append({
            "field": "class_name",
            "field_name": "班级",
            "type": "info",
            "old_value": old_val,
            "new_value": class_name,
            "old_display": str(old_val),
            "new_display": class_name,
        })

    if gender is not None:
        if gender not in GENDERS:
            raise ValueError(f"无效性别: {gender}，可选: 男、女")
        old_val = raw_df.at[raw_row_idx, "gender"]
        raw_df.at[raw_row_idx, "gender"] = gender
        print(f"✓ 修正性别: {old_val}  →  {gender}")
        changes.append({
            "field": "gender",
            "field_name": "性别",
            "type": "info",
            "old_value": old_val,
            "new_value": gender,
            "old_display": str(old_val),
            "new_display": gender,
        })

    if not changes:
        print("未做任何修改（需要指定 --project + --value 或 --class 或 --gender）")
        return {"modified": False}

    scored_df = calculate_individual_scores(raw_df)
    scored_df["total_score"] = scored_df.apply(calculate_total_score, axis=1)
    scored_df["level"] = scored_df["total_score"].apply(
        lambda x: get_score_level(x) if pd.notna(x) else None
    )

    scored_mask = scored_df["student_id"] == student_id
    scored_row_idx = scored_df[scored_mask].index[0]
    new_total_score = scored_df.at[scored_row_idx, "total_score"]
    new_level = scored_df.at[scored_row_idx, "level"]

    old_total_score = None
    old_level = None
    if scored_path.exists():
        old_scored = load_pickle(scored_path)
        old_mask = old_scored["student_id"] == student_id
        if old_mask.any():
            old_idx = old_scored[old_mask].index[0]
            old_total_score = old_scored.at[old_idx, "total_score"] if "total_score" in old_scored.columns else None
            old_level = old_scored.at[old_idx, "level"] if "level" in old_scored.columns else None

    print(f"\n修正后评分: 总分={new_total_score}  等级={new_level}")
    if old_total_score is not None:
        print(f"之前评分:   总分={old_total_score}  等级={old_level}")
        diff = round(new_total_score - old_total_score, 1) if pd.notna(new_total_score) and pd.notna(old_total_score) else None
        if diff is not None:
            print(f"分差: {diff:+.1f}")

    print("\n修正后学生信息:")
    info_cols = [c for c in ["student_id", "name", "gender", "class_name", "grade", "total_score", "level"] if c in scored_df.columns]
    project_cols = [p for p in PROJECTS if p in scored_df.columns]
    print_table(scored_df.loc[[scored_row_idx]][info_cols + project_cols])

    if not preview:
        save_pickle(raw_df, raw_path)
        print(f"\n✓ 原始数据已更新: {raw_path}")

        save_pickle(scored_df, scored_path)
        print(f"✓ 评分数据已更新: {scored_path}")

        class_stats = calculate_class_stats(scored_df)
        if not class_stats.empty:
            class_stats_path = get_data_path(semester, grade_key, "class_stats.pkl")
            save_pickle(class_stats, class_stats_path)
            print(f"✓ 班级统计已更新: {class_stats_path}")

        log_entry = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "semester": semester,
            "grade": grade,
            "student_id": student_id,
            "student_name": raw_df.at[raw_row_idx, "name"] if "name" in raw_df.columns else "",
            "changes": changes,
            "old_total_score": old_total_score if not isinstance(old_total_score, float) or old_total_score == old_total_score else None,
            "new_total_score": new_total_score if not isinstance(new_total_score, float) or new_total_score == new_total_score else None,
            "old_level": old_level,
            "new_level": new_level,
            "note": note,
        }

        log_path = get_data_path(semester, grade_key, "fix_log.json")
        existing_log = []
        if log_path.exists():
            existing_log = load_json(log_path)
            if not isinstance(existing_log, list):
                existing_log = []
        existing_log.append(log_entry)
        save_json(existing_log, log_path)
        print(f"✓ 操作记录已保存: {log_path}")

    return {
        "modified": True,
        "student_id": student_id,
        "changes": changes,
        "old_total_score": old_total_score,
        "new_total_score": new_total_score,
        "old_level": old_level,
        "new_level": new_level,
    }


def _parse_date(s: str) -> Optional[datetime]:
    s = s.strip()
    for fmt in ["%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"]:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _match_date_range(ts_str: str, date_from: Optional[str], date_to: Optional[str]) -> bool:
    if not date_from and not date_to:
        return True
    try:
        ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return True
    if date_from:
        df = _parse_date(date_from)
        if df and ts < df:
            return False
    if date_to:
        dt = _parse_date(date_to)
        if dt:
            dt_end = dt.replace(hour=23, minute=59, second=59)
            if ts > dt_end:
                return False
    return True


def show_fix_log(
    semester: str,
    grade: Optional[str] = None,
    limit: int = 20,
    student_id: Optional[str] = None,
    project: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    output_dir: Optional[str] = None,
    output_format: str = "xlsx",
) -> None:
    grade_key = grade or "all"
    log_path = get_data_path(semester, grade_key, "fix_log.json")

    if not log_path.exists():
        print("暂无修正记录")
        return

    log = load_json(log_path)

    if not log:
        print("暂无修正记录")
        return

    filtered: List[Dict] = []
    for entry in log:
        if student_id and entry.get("student_id") != student_id:
            continue
        if project:
            projs_in_entry = {ch.get("field") for ch in entry.get("changes", [])}
            if project not in projs_in_entry:
                continue
        if not _match_date_range(entry.get("timestamp", ""), date_from, date_to):
            continue
        filtered.append(entry)

    if not filtered:
        print("没有符合条件的修正记录")
        return

    log_sorted = list(reversed(filtered))
    display_log = log_sorted[:limit]

    filter_parts = []
    if student_id:
        filter_parts.append(f"学号={student_id}")
    if project:
        filter_parts.append(f"项目={PROJECT_NAMES.get(project, project)}")
    if date_from or date_to:
        filter_parts.append(f"日期={date_from or '开始'} ~ {date_to or '今天'}")

    print(f"\n修正操作记录（共 {len(filtered)} 条，显示最近 {len(display_log)} 条"
          f"{'，筛选: ' + ', '.join(filter_parts) if filter_parts else ''}）:")
    print("=" * 60)

    for i, entry in enumerate(display_log, 1):
        ts = entry.get("timestamp", "")
        sid = entry.get("student_id", "")
        sname = entry.get("student_name", "")
        old_score = entry.get("old_total_score")
        new_score = entry.get("new_total_score")
        old_level = entry.get("old_level")
        new_level = entry.get("new_level")
        note = entry.get("note", "")

        print(f"\n[{len(filtered) - i + 1}] {ts}  学号: {sid}  姓名: {sname}")
        for ch in entry.get("changes", []):
            print(f"    · {ch.get('field_name', ch.get('field', ''))}: "
                  f"{ch.get('old_display', ch.get('old_value', ''))} → {ch.get('new_display', ch.get('new_value', ''))}")
        if old_score is not None or new_score is not None:
            score_diff = ""
            if old_score is not None and new_score is not None:
                diff = round(float(new_score) - float(old_score), 1)
                score_diff = f"  ({diff:+.1f}分)"
            print(f"    总分: {old_score} → {new_score}{score_diff}")
            print(f"    等级: {old_level} → {new_level}")
        if note:
            print(f"    备注: {note}")

    if output_dir:
        out_path = ensure_output_dir(output_dir)
        rows = []
        for entry in filtered:
            base = {
                "时间": entry.get("timestamp", ""),
                "学号": entry.get("student_id", ""),
                "姓名": entry.get("student_name", ""),
                "学期": entry.get("semester", ""),
                "年级": entry.get("grade", ""),
                "原总分": entry.get("old_total_score"),
                "新总分": entry.get("new_total_score"),
                "原等级": entry.get("old_level"),
                "新等级": entry.get("new_level"),
                "备注": entry.get("note", ""),
            }
            changes = entry.get("changes", [])
            if not changes:
                rows.append({**base, "修改项": "", "原值": "", "新值": ""})
            else:
                for ch in changes:
                    rows.append({
                        **base,
                        "修改项": ch.get("field_name", ch.get("field", "")),
                        "原值": ch.get("old_display", ch.get("old_value", "")),
                        "新值": ch.get("new_display", ch.get("new_value", "")),
                    })

        df = pd.DataFrame(rows)
        suffix_parts = [semester]
        if grade:
            suffix_parts.append(grade)
        suffix = "_".join(suffix_parts)
        file_path = out_path / f"修正记录_{suffix}.{output_format}"
        save_dataframe(df, file_path)
        print(f"\n✓ 修正记录已导出: {file_path}（共 {len(df)} 行）")
    else:
        print(f"\n提示: 加 -o <目录> 可导出修正记录，完整记录保存在 {log_path}")
