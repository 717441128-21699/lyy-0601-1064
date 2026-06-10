"""评分模块

负责计算单项分、总分、等级和班级平均分。
项目权重参考《国家学生体质健康标准》：
- BMI: 15%
- 肺活量: 15%
- 50米跑: 20%
- 立定跳远: 10%
- 坐位体前屈: 10%
- 引体向上/仰卧起坐: 10%
- 耐力跑(1000m/800m): 20%
"""

from typing import Dict, Optional
from pathlib import Path

import pandas as pd
import numpy as np

from .standards import (
    PROJECTS,
    PROJECT_NAMES,
    GRADES,
    GENDERS,
    get_required_projects,
    calculate_project_score,
    get_score_level,
)
from .utils import (
    get_data_path,
    load_pickle,
    save_pickle,
    save_json,
    print_table,
    seconds_to_time_str,
    format_number,
)


PROJECT_WEIGHTS = {
    "bmi": 0.15,
    "vital_capacity": 0.15,
    "run_50m": 0.20,
    "standing_jump": 0.10,
    "sit_and_reach": 0.10,
    "pull_up": 0.10,
    "sit_up": 0.10,
    "run_1000m": 0.20,
    "run_800m": 0.20,
}


def calculate_individual_scores(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    
    score_cols = []
    for proj in PROJECTS:
        if proj not in df.columns:
            continue
        score_col = f"{proj}_score"
        df[score_col] = df.apply(
            lambda row: calculate_project_score(
                proj, row.get(proj), row.get("gender", ""), row.get("grade", "")
            ),
            axis=1,
        )
        score_cols.append(score_col)
    
    df["score_cols"] = [score_cols] * len(df)
    return df


def calculate_total_score(row: pd.Series) -> Optional[float]:
    gender = row.get("gender", "")
    required = get_required_projects(gender) if gender in GENDERS else []
    
    total_weight = 0.0
    weighted_sum = 0.0
    has_any_score = False
    
    for proj in required:
        score_col = f"{proj}_score"
        score = row.get(score_col)
        if pd.isna(score) or score is None:
            continue
        weight = PROJECT_WEIGHTS.get(proj, 0)
        weighted_sum += float(score) * weight
        total_weight += weight
        has_any_score = True
    
    if not has_any_score:
        return None
    
    if total_weight == 0:
        return None
    
    return round(weighted_sum / total_weight * 100 / 100, 1) if total_weight != 1.0 else round(weighted_sum, 1)


def calculate_class_stats(df: pd.DataFrame) -> pd.DataFrame:
    if "class_name" not in df.columns or "total_score" not in df.columns:
        return pd.DataFrame()
    
    valid_df = df[df["total_score"].notna()].copy()
    
    if valid_df.empty:
        return pd.DataFrame()
    
    stats = valid_df.groupby("class_name").agg(
        学生人数=("student_id", "count"),
        平均分=("total_score", "mean"),
        最高分=("total_score", "max"),
        最低分=("total_score", "min"),
        优秀率=("total_score", lambda x: (x >= 90).sum() / len(x) * 100),
        良好率=("total_score", lambda x: ((x >= 80) & (x < 90)).sum() / len(x) * 100),
        及格率=("total_score", lambda x: ((x >= 60) & (x < 80)).sum() / len(x) * 100),
        不及格率=("total_score", lambda x: (x < 60).sum() / len(x) * 100),
    ).reset_index()
    
    stats.columns = ["班级", "学生人数", "平均分", "最高分", "最低分", "优秀率(%)", "良好率(%)", "及格率(%)", "不及格率(%)"]
    
    for col in ["平均分", "最高分", "最低分", "优秀率(%)", "良好率(%)", "及格率(%)", "不及格率(%)"]:
        stats[col] = stats[col].round(1)
    
    stats = stats.sort_values("平均分", ascending=False).reset_index(drop=True)
    stats.index = stats.index + 1
    stats.index.name = "排名"
    stats = stats.reset_index()
    
    return stats


def score_data(
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
    print(f"加载 {len(df)} 条学生数据进行评分")
    
    print("\n正在计算单项分数...")
    df = calculate_individual_scores(df)
    
    print("正在计算总分...")
    df["total_score"] = df.apply(calculate_total_score, axis=1)
    
    print("正在评定等级...")
    df["level"] = df["total_score"].apply(
        lambda x: get_score_level(x) if pd.notna(x) else None
    )
    
    score_cols = [f"{p}_score" for p in PROJECTS if f"{p}_score" in df.columns]
    
    display_cols = ["student_id", "name", "gender", "class_name"] + score_cols + ["total_score", "level"]
    display_df = df[display_cols].copy()
    display_df.columns = (
        ["学号", "姓名", "性别", "班级"]
        + [PROJECT_NAMES.get(c.replace("_score", ""), c).replace("(男)", "").replace("(女)", "") + "分" for c in score_cols]
        + ["总分", "等级"]
    )
    
    print("\n学生成绩预览:")
    print_table(display_df)
    
    print("\n正在计算班级统计...")
    class_stats = calculate_class_stats(df)
    if not class_stats.empty:
        print("\n班级成绩统计:")
        print_table(class_stats)
    
    results = {
        "scored_data": df,
        "class_stats": class_stats,
    }
    
    if not preview:
        scored_path = get_data_path(semester, grade_key, "scored_data.pkl")
        save_pickle(df, scored_path)
        print(f"\n评分数据已保存至: {scored_path}")
        
        if not class_stats.empty:
            class_stats_path = get_data_path(semester, grade_key, "class_stats.pkl")
            save_pickle(class_stats, class_stats_path)
        
        level_counts = df["level"].value_counts().to_dict()
        total_scored = df["total_score"].notna().sum()
        summary = {
            "semester": semester,
            "grade": grade,
            "total_students": len(df),
            "scored_students": int(total_scored),
            "avg_score": round(df["total_score"].mean(), 1) if total_scored > 0 else None,
            "level_distribution": level_counts,
            "pass_rate": round((df["total_score"] >= 60).sum() / total_scored * 100, 1) if total_scored > 0 else None,
            "excellent_rate": round((df["total_score"] >= 90).sum() / total_scored * 100, 1) if total_scored > 0 else None,
        }
        summary_path = get_data_path(semester, grade_key, "score_summary.json")
        save_json(summary, summary_path)
        
        print("\n评分汇总:")
        print(f"  参评学生: {total_scored}/{len(df)}")
        if summary["avg_score"] is not None:
            print(f"  平均分: {summary['avg_score']}")
            print(f"  及格率: {summary['pass_rate']}%")
            print(f"  优秀率: {summary['excellent_rate']}%")
        print(f"  等级分布: {level_counts}")
    
    return results
