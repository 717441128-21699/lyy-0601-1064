"""导入模块

负责导入学生名单和各项目成绩数据。
支持两种格式：
1. 宽表格式：一行一个学生，所有项目在同一行
2. 分项目格式：一行一个学生一个项目，自动合并为完整成绩
支持 Excel、CSV、JSON 格式。
"""

from typing import Optional, List
from pathlib import Path

import pandas as pd

from .standards import PROJECTS, GRADES, GENDERS, PROJECT_NAMES
from .utils import (
    auto_rename_columns,
    load_dataframe,
    parse_time_to_seconds,
    calculate_bmi,
    get_data_path,
    save_pickle,
    save_json,
    print_table,
)


def detect_format(df: pd.DataFrame) -> str:
    project_cols_found = [p for p in PROJECTS if p in df.columns]
    project_name_cols = [c for c in df.columns if c in ["project", "项目", "test_item", "测试项目"]]
    value_cols = [c for c in df.columns if c in ["value", "score", "成绩", "结果", "result", "raw_value"]]

    if project_name_cols and value_cols:
        return "long"

    if len(project_cols_found) >= 2:
        return "wide"

    if project_name_cols:
        return "long"

    return "wide"


def merge_long_format(df: pd.DataFrame) -> pd.DataFrame:
    col_mapping = {
        "project": "项目",
        "test_item": "项目",
        "测试项目": "项目",
        "value": "成绩",
        "score": "成绩",
        "成绩": "成绩",
        "result": "成绩",
        "raw_value": "成绩",
    }
    rename_map = {}
    for col in df.columns:
        if col in col_mapping:
            rename_map[col] = col_mapping[col]
    if rename_map:
        df = df.rename(columns=rename_map)

    if "项目" not in df.columns or "成绩" not in df.columns:
        print("警告: 分项目表未找到'项目'或'成绩'列，无法合并")
        return df

    project_reverse = {}
    for std_key, aliases in PROJECT_NAMES.items():
        project_reverse[aliases] = std_key
        project_reverse[aliases.replace("(男)", "").replace("(女)", "")] = std_key
    for p in PROJECTS:
        project_reverse[p] = p

    df["项目"] = df["项目"].astype(str).str.strip()
    df["_project_key"] = df["项目"].map(lambda x: project_reverse.get(x, x))

    id_cols = [c for c in ["student_id", "学号", "id", "编号"] if c in df.columns]
    if not id_cols:
        print("警告: 分项目表未找到学号列，无法合并")
        return df

    id_col = id_cols[0]
    info_cols = [c for c in [id_col, "name", "姓名", "gender", "性别", "class_name", "班级", "grade", "年级"] if c in df.columns]

    pivoted = df.pivot_table(
        index=info_cols,
        columns="_project_key",
        values="成绩",
        aggfunc="first",
    ).reset_index()

    pivoted.columns.name = None

    return pivoted


def normalize_data(df: pd.DataFrame, default_grade: Optional[str] = None) -> pd.DataFrame:
    df = auto_rename_columns(df).copy()

    if "grade" not in df.columns and default_grade:
        df["grade"] = default_grade

    for col in ["student_id", "name", "gender", "class_name", "grade"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()

    if "gender" in df.columns:
        df["gender"] = df["gender"].replace({
            "男": "男", "M": "男", "m": "男", "male": "男", "Male": "男",
            "女": "女", "F": "女", "f": "女", "female": "女", "Female": "女",
        })

    if "height" in df.columns and "weight" in df.columns:
        if "bmi" not in df.columns:
            df["bmi"] = df.apply(lambda row: calculate_bmi(row.get("height"), row.get("weight")), axis=1)
        else:
            mask = df["bmi"].isna() | (df["bmi"] == "")
            df.loc[mask, "bmi"] = df.loc[mask].apply(
                lambda row: calculate_bmi(row.get("height"), row.get("weight")), axis=1
            )

    time_projects = ["run_50m", "run_1000m", "run_800m"]
    for proj in time_projects:
        if proj in df.columns:
            df[proj] = df[proj].apply(parse_time_to_seconds)

    numeric_projects = [
        "bmi", "vital_capacity", "standing_jump",
        "sit_and_reach", "pull_up", "sit_up",
    ]
    for proj in numeric_projects:
        if proj in df.columns:
            df[proj] = pd.to_numeric(df[proj], errors="coerce")

    return df


def import_data(
    input_files: List[str],
    semester: str,
    grade: Optional[str] = None,
    preview: bool = False,
) -> pd.DataFrame:
    all_dfs = []
    for input_file in input_files:
        file_path = Path(input_file)
        if not file_path.exists():
            raise FileNotFoundError(f"输入文件不存在: {input_file}")

        print(f"正在读取文件: {input_file}")
        raw_df = load_dataframe(file_path)
        print(f"读取到 {len(raw_df)} 条记录")

        fmt = detect_format(raw_df)
        if fmt == "long":
            print(f"检测到分项目表格式，正在合并...")
            df = merge_long_format(raw_df)
            print(f"合并后 {len(df)} 条学生记录")
        else:
            print(f"检测到宽表格式")
            df = raw_df

        all_dfs.append(df)

    if len(all_dfs) > 1:
        df = all_dfs[0]
        for extra_df in all_dfs[1:]:
            if "student_id" in df.columns and "student_id" in extra_df.columns:
                project_cols = [c for c in PROJECTS if c in extra_df.columns and c not in df.columns]
                if project_cols:
                    merge_cols = ["student_id"]
                    extra_subset = extra_df[merge_cols + project_cols].copy()
                    df = pd.merge(df, extra_subset, on=merge_cols, how="outer", suffixes=("", "_extra"))
                    for col in project_cols:
                        extra_col = f"{col}_extra"
                        if extra_col in df.columns:
                            df[col] = df[col].fillna(df[extra_col])
                            df = df.drop(columns=[extra_col])
            else:
                df = pd.concat([df, extra_df], ignore_index=True)
        print(f"多文件合并后共 {len(df)} 条记录")

    df = normalize_data(df, default_grade=grade)

    if grade and "grade" in df.columns:
        before = len(df)
        df = df[df["grade"] == grade]
        print(f"按年级筛选后剩余 {len(df)} 条记录（筛掉 {before - len(df)} 条）")

    info_cols = [c for c in ["student_id", "name", "gender", "class_name", "grade"] if c in df.columns]
    project_cols = [p for p in PROJECTS if p in df.columns]

    if project_cols:
        print(f"检测到项目: {', '.join(project_cols)}")
    else:
        print("警告: 未检测到体测项目列")

    display_cols = info_cols + project_cols

    print("\n数据预览:")
    print_table(df[display_cols])

    if not preview:
        data_path = get_data_path(semester, grade or "all", "raw_data.pkl")
        save_pickle(df, data_path)
        print(f"\n数据已保存至: {data_path}")

        meta = {
            "semester": semester,
            "grade": grade,
            "total_students": len(df),
            "projects": project_cols,
            "classes": sorted(df["class_name"].dropna().unique().tolist()) if "class_name" in df.columns else [],
        }
        meta_path = get_data_path(semester, grade or "all", "meta.json")
        save_json(meta, meta_path)

    return df
