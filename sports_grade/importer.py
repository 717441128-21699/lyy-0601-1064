"""导入模块

负责导入学生名单和各项目成绩数据。
支持 Excel、CSV、JSON 格式。
"""

from typing import Optional
from pathlib import Path

import pandas as pd

from .standards import PROJECTS, GRADES, GENDERS
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
    input_file: str,
    semester: str,
    grade: Optional[str] = None,
    preview: bool = False,
) -> pd.DataFrame:
    file_path = Path(input_file)
    if not file_path.exists():
        raise FileNotFoundError(f"输入文件不存在: {input_file}")
    
    print(f"正在读取文件: {input_file}")
    df = load_dataframe(file_path)
    print(f"读取到 {len(df)} 条记录")
    
    df = normalize_data(df, default_grade=grade)
    
    if grade and "grade" in df.columns:
        df = df[df["grade"] == grade]
        print(f"按年级筛选后剩余 {len(df)} 条记录")
    
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
