"""校验模块

负责检查数据质量，包括：
- 缺考检查
- 异常高低值检查
- 重复学号检查
- 项目缺失检查
"""

from typing import Dict, List, Optional, Tuple
from pathlib import Path

import pandas as pd
import numpy as np

from .standards import PROJECTS, PROJECT_NAMES, GENDERS, get_required_projects
from .utils import (
    get_data_path,
    load_pickle,
    save_pickle,
    save_json,
    print_table,
    is_numeric_value,
)


NORMAL_RANGES = {
    "bmi": (10, 40),
    "vital_capacity": (500, 8000),
    "run_50m": (5, 20),
    "standing_jump": (50, 350),
    "sit_and_reach": (-20, 40),
    "pull_up": (0, 50),
    "sit_up": (0, 80),
    "run_1000m": (150, 600),
    "run_800m": (120, 500),
}


def check_duplicate_ids(df: pd.DataFrame) -> pd.DataFrame:
    if "student_id" not in df.columns:
        return pd.DataFrame()
    dup_mask = df["student_id"].duplicated(keep=False) & df["student_id"].notna()
    duplicates = df[dup_mask].sort_values("student_id")
    return duplicates


def check_missing_info(df: pd.DataFrame) -> pd.DataFrame:
    required_info = ["student_id", "name", "gender", "class_name"]
    missing_info_mask = pd.Series(False, index=df.index)
    for col in required_info:
        if col in df.columns:
            missing_info_mask = missing_info_mask | df[col].isna() | (df[col].astype(str).str.strip() == "")
        else:
            missing_info_mask = pd.Series(True, index=df.index)
    info_cols = [c for c in ["student_id", "name", "gender", "class_name"] if c in df.columns]
    return df[missing_info_mask][info_cols]


def check_missing_projects(df: pd.DataFrame) -> pd.DataFrame:
    result_rows = []
    for idx, row in df.iterrows():
        gender = row.get("gender", "")
        required = get_required_projects(gender) if gender in GENDERS else []
        missing = []
        for proj in required:
            if proj not in df.columns:
                missing.append(proj)
            elif pd.isna(row.get(proj)) or (isinstance(row.get(proj), str) and row.get(proj).strip() == ""):
                missing.append(proj)
        if missing:
            row_data = {
                "student_id": row.get("student_id", ""),
                "name": row.get("name", ""),
                "class_name": row.get("class_name", ""),
                "missing_projects": ", ".join([PROJECT_NAMES.get(p, p) for p in missing]),
            }
            result_rows.append(row_data)
    return pd.DataFrame(result_rows)


def check_abnormal_values(df: pd.DataFrame) -> pd.DataFrame:
    result_rows = []
    available_projects = [p for p in PROJECTS if p in df.columns]
    
    for idx, row in df.iterrows():
        gender = row.get("gender", "")
        abnormal = []
        for proj in available_projects:
            value = row.get(proj)
            if pd.isna(value):
                continue
            if not is_numeric_value(value):
                continue
            
            if proj == "pull_up" and gender != "男":
                continue
            if proj == "sit_up" and gender != "女":
                continue
            if proj == "run_1000m" and gender != "男":
                continue
            if proj == "run_800m" and gender != "女":
                continue
            
            val = float(value)
            low, high = NORMAL_RANGES.get(proj, (float("-inf"), float("inf")))
            if val < low or val > high:
                proj_name = PROJECT_NAMES.get(proj, proj)
                abnormal.append(f"{proj_name}: {val}")
        
        if abnormal:
            row_data = {
                "student_id": row.get("student_id", ""),
                "name": row.get("name", ""),
                "class_name": row.get("class_name", ""),
                "abnormal_values": "; ".join(abnormal),
            }
            result_rows.append(row_data)
    return pd.DataFrame(result_rows)


def check_absent_students(df: pd.DataFrame) -> pd.DataFrame:
    available_projects = [p for p in PROJECTS if p in df.columns]
    if not available_projects:
        return pd.DataFrame()
    
    all_missing_mask = pd.Series(True, index=df.index)
    for proj in available_projects:
        all_missing_mask = all_missing_mask & (
            df[proj].isna() | 
            (df[proj].astype(str).str.strip() == "")
        )
    
    info_cols = [c for c in ["student_id", "name", "gender", "class_name"] if c in df.columns]
    return df[all_missing_mask][info_cols]


def validate_data(
    semester: str,
    grade: Optional[str] = None,
    preview: bool = False,
) -> Dict:
    grade_key = grade or "all"
    data_path = get_data_path(semester, grade_key, "raw_data.pkl")
    
    if not data_path.exists():
        raise FileNotFoundError(
            f"未找到原始数据，请先执行 import 命令。\n"
            f"期望路径: {data_path}"
        )
    
    df = load_pickle(data_path)
    print(f"加载 {len(df)} 条学生数据进行校验")
    
    results = {}
    
    print("\n" + "=" * 60)
    print("1. 重复学号检查")
    print("=" * 60)
    dup_df = check_duplicate_ids(df)
    results["duplicate_ids"] = dup_df
    if dup_df.empty:
        print("✓ 未发现重复学号")
    else:
        print(f"✗ 发现 {len(dup_df)} 条重复学号记录:")
        print_table(dup_df)
    
    print("\n" + "=" * 60)
    print("2. 基本信息缺失检查")
    print("=" * 60)
    missing_info_df = check_missing_info(df)
    results["missing_info"] = missing_info_df
    if missing_info_df.empty:
        print("✓ 所有学生基本信息完整")
    else:
        print(f"✗ 发现 {len(missing_info_df)} 条基本信息缺失记录:")
        print_table(missing_info_df)
    
    print("\n" + "=" * 60)
    print("3. 缺考检查（所有项目均无成绩）")
    print("=" * 60)
    absent_df = check_absent_students(df)
    results["absent_students"] = absent_df
    if absent_df.empty:
        print("✓ 未发现完全缺考学生")
    else:
        print(f"✗ 发现 {len(absent_df)} 名完全缺考学生:")
        print_table(absent_df)
    
    print("\n" + "=" * 60)
    print("4. 项目缺失检查")
    print("=" * 60)
    missing_proj_df = check_missing_projects(df)
    results["missing_projects"] = missing_proj_df
    if missing_proj_df.empty:
        print("✓ 所有学生必修项目成绩完整")
    else:
        print(f"✗ 发现 {len(missing_proj_df)} 名学生存在项目缺失:")
        print_table(missing_proj_df)
    
    print("\n" + "=" * 60)
    print("5. 异常值检查")
    print("=" * 60)
    abnormal_df = check_abnormal_values(df)
    results["abnormal_values"] = abnormal_df
    if abnormal_df.empty:
        print("✓ 未发现异常值")
    else:
        print(f"✗ 发现 {len(abnormal_df)} 条异常值记录:")
        print_table(abnormal_df)
    
    total_issues = sum(len(v) for v in results.values() if isinstance(v, pd.DataFrame))
    print("\n" + "=" * 60)
    print(f"校验完成，共发现 {total_issues} 个问题")
    print("=" * 60)
    
    if not preview:
        for name, result_df in results.items():
            if isinstance(result_df, pd.DataFrame) and not result_df.empty:
                out_path = get_data_path(semester, grade_key, f"validation_{name}.pkl")
                save_pickle(result_df, out_path)
        
        summary = {
            "semester": semester,
            "grade": grade,
            "total_students": len(df),
            "duplicate_ids_count": len(results["duplicate_ids"]),
            "missing_info_count": len(results["missing_info"]),
            "absent_count": len(results["absent_students"]),
            "missing_projects_count": len(results["missing_projects"]),
            "abnormal_values_count": len(results["abnormal_values"]),
            "total_issues": total_issues,
        }
        summary_path = get_data_path(semester, grade_key, "validation_summary.json")
        save_json(summary, summary_path)
        print(f"\n校验结果已保存至: {get_data_path(semester, grade_key, '')}")
    
    return results
