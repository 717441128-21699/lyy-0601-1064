"""导出模块

负责将处理后的数据导出为各种格式，支持筛选和预览。
支持 Excel、CSV、JSON 格式输出。
"""

from typing import Dict, List, Optional
from pathlib import Path

import pandas as pd
import numpy as np

from .standards import PROJECTS, PROJECT_NAMES, PROJECT_UNITS
from .utils import (
    get_data_path,
    load_pickle,
    save_dataframe,
    ensure_output_dir,
    print_table,
    seconds_to_time_str,
    format_number,
)


def filter_data(
    df: pd.DataFrame,
    class_name: Optional[str] = None,
    level: Optional[str] = None,
    project: Optional[str] = None,
    project_score_min: Optional[float] = None,
) -> pd.DataFrame:
    result = df.copy()

    if class_name and "class_name" in result.columns:
        result = result[result["class_name"] == class_name]

    if level and "level" in result.columns:
        result = result[result["level"] == level]

    if project:
        if project in result.columns:
            if project_score_min is not None:
                result = result[result[project].notna() & (result[project] >= project_score_min)]
            else:
                result = result[result[project].notna()]
        score_col = f"{project}_score"
        if score_col in result.columns:
            if project_score_min is not None:
                result = result[result[score_col].notna() & (result[score_col] >= project_score_min)]

    return result


def format_for_export(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()

    keep_cols = ["student_id", "name", "gender", "class_name", "grade", "total_score", "level"]
    for proj in PROJECTS:
        if proj in result.columns:
            keep_cols.append(proj)
        score_col = f"{proj}_score"
        if score_col in result.columns:
            keep_cols.append(score_col)
    
    result = result[[c for c in keep_cols if c in result.columns]].copy()

    column_mapping = {
        "student_id": "学号",
        "name": "姓名",
        "gender": "性别",
        "class_name": "班级",
        "grade": "年级",
        "total_score": "总分",
        "level": "等级",
    }

    for proj in PROJECTS:
        if proj in result.columns:
            unit = PROJECT_UNITS.get(proj, "")
            name = PROJECT_NAMES.get(proj, proj)
            if proj in ["run_50m", "run_1000m", "run_800m"]:
                result[proj] = result[proj].apply(seconds_to_time_str)
            elif proj in ["bmi", "sit_and_reach"]:
                result[proj] = result[proj].apply(lambda x: format_number(x, 1))
            elif proj in ["vital_capacity", "standing_jump", "pull_up", "sit_up"]:
                result[proj] = result[proj].apply(lambda x: format_number(x, 0))
            column_mapping[proj] = f"{name}({unit})" if unit else name

        score_col = f"{proj}_score"
        if score_col in result.columns:
            name = PROJECT_NAMES.get(proj, proj)
            column_mapping[score_col] = f"{name}得分"

    rename_cols = {k: v for k, v in column_mapping.items() if k in result.columns}
    result = result.rename(columns=rename_cols)

    return result


def export_data(
    semester: str,
    grade: Optional[str] = None,
    output_dir: str = "./output",
    output_format: str = "xlsx",
    class_name: Optional[str] = None,
    level: Optional[str] = None,
    project: Optional[str] = None,
    preview: bool = False,
) -> Dict:
    grade_key = grade or "all"

    scored_path = get_data_path(semester, grade_key, "scored_data.pkl")
    if not scored_path.exists():
        raise FileNotFoundError(
            f"未找到评分数据，请先执行 score 命令。\n"
            f"期望路径: {scored_path}"
        )

    df = load_pickle(scored_path)
    print(f"加载 {len(df)} 条评分数据")

    filtered_df = filter_data(df, class_name=class_name, level=level, project=project)
    print(f"筛选后剩余 {len(filtered_df)} 条记录")

    if class_name:
        print(f"  - 按班级筛选: {class_name}")
    if level:
        print(f"  - 按等级筛选: {level}")
    if project:
        print(f"  - 按项目筛选: {PROJECT_NAMES.get(project, project)}")

    formatted_df = format_for_export(filtered_df)

    print("\n数据预览:")
    print_table(formatted_df)

    export_files = {}

    if not preview:
        output_path = ensure_output_dir(output_dir)

        file_suffix = f"_{semester}"
        if grade:
            file_suffix += f"_{grade}"
        if class_name:
            file_suffix += f"_{class_name}"
        if level:
            file_suffix += f"_{level}"
        if project:
            file_suffix += f"_{project}"

        formatted_df = format_for_export(filtered_df)
        main_file = output_path / f"学生成绩{file_suffix}.{output_format}"
        save_dataframe(formatted_df, main_file)
        export_files["学生成绩"] = str(main_file)
        print(f"\n✓ 已导出: {main_file}")

        rank_files = {
            "overall_ranking": "总分排名",
            "failed_list": "未达标名单",
            "retest_list": "补测名单",
            "progress_ranking": "进步榜",
            "class_comparison": "班级对比表",
        }
        for rank_key, rank_name in rank_files.items():
            rank_path = get_data_path(semester, grade_key, f"rank_{rank_key}.pkl")
            if rank_path.exists():
                rank_df = load_pickle(rank_path)
                if not rank_df.empty:
                    rank_file = output_path / f"{rank_name}{file_suffix}.{output_format}"
                    save_dataframe(rank_df, rank_file)
                    export_files[rank_name] = str(rank_file)
                    print(f"✓ 已导出: {rank_file}")

        class_stats_path = get_data_path(semester, grade_key, "class_stats.pkl")
        if class_stats_path.exists():
            class_stats = load_pickle(class_stats_path)
            if not class_stats.empty:
                class_file = output_path / f"班级统计{file_suffix}.{output_format}"
                save_dataframe(class_stats, class_file)
                export_files["班级统计"] = str(class_file)
                print(f"✓ 已导出: {class_file}")

        valid_path = get_data_path(semester, grade_key, "validation_summary.json")
        if valid_path.exists():
            from .utils import load_json
            valid_summary = load_json(valid_path)
            if valid_summary.get("total_issues", 0) > 0:
                for vname in ["duplicate_ids", "missing_info", "absent_students", "missing_projects", "abnormal_values"]:
                    vpath = get_data_path(semester, grade_key, f"validation_{vname}.pkl")
                    if vpath.exists():
                        vdf = load_pickle(vpath)
                        if not vdf.empty:
                            vnames_cn = {
                                "duplicate_ids": "重复学号",
                                "missing_info": "信息缺失",
                                "absent_students": "缺考学生",
                                "missing_projects": "项目缺失",
                                "abnormal_values": "异常值",
                            }
                            vfile = output_path / f"校验_{vnames_cn.get(vname, vname)}{file_suffix}.{output_format}"
                            save_dataframe(vdf, vfile)
                            export_files[f"校验_{vnames_cn.get(vname, vname)}"] = str(vfile)
                            print(f"✓ 已导出: {vfile}")

        print(f"\n共导出 {len(export_files)} 个文件至: {output_path}")

    return {
        "filtered_data": filtered_df,
        "formatted_data": formatted_df,
        "export_files": export_files,
    }
