"""导出模块

负责将处理后的数据导出为各种格式，支持筛选和预览。
所有导出表均按同一批筛选学生收口，文件名体现筛选条件。
支持总工作簿模式：多 sheet 放在同一个 Excel 文件中，首 sheet 为总览。
"""

from typing import Dict, List, Optional, Tuple
from pathlib import Path

import pandas as pd
import numpy as np

from .standards import PROJECTS, PROJECT_NAMES, PROJECT_UNITS, GENDERS, get_required_projects
from .ranker import (
    generate_overall_ranking,
    generate_failed_list,
    generate_retest_list,
    retest_summary_to_df,
)
from .reporter import compute_detailed_status, compute_level_stats
from .scorer import calculate_class_stats
from .utils import (
    get_data_path,
    load_pickle,
    save_dataframe,
    save_workbook,
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
) -> pd.DataFrame:
    result = df.copy()

    if class_name and "class_name" in result.columns:
        result = result[result["class_name"] == class_name]

    if level and "level" in result.columns:
        result = result[result["level"] == level]

    if project:
        if project in result.columns:
            result = result[result[project].notna()]
        score_col = f"{project}_score"
        if score_col in result.columns:
            result = result[result[score_col].notna()]

    return result


def build_file_suffix(
    semester: str,
    grade: Optional[str] = None,
    class_name: Optional[str] = None,
    level: Optional[str] = None,
    project: Optional[str] = None,
) -> str:
    parts = [semester]
    if grade:
        parts.append(grade)
    if class_name:
        parts.append(class_name)
    if level:
        parts.append(level)
    if project:
        parts.append(PROJECT_NAMES.get(project, project))
    return "_".join(parts)


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


def build_info_sheet(
    filtered_df: pd.DataFrame,
    grade_key: str,
    semester: str,
    grade: Optional[str],
    filters_desc: List[str],
) -> pd.DataFrame:
    """构建筛选说明和校验摘要 sheet，交材料时不用再手工补。"""
    rows = []

    rows.append({"分类": "基本信息", "项目": "学期", "内容": semester})
    rows.append({"分类": "基本信息", "项目": "年级", "内容": grade or "全部年级"})
    rows.append({"分类": "基本信息", "项目": "筛选条件", "内容": ", ".join(filters_desc) if filters_desc else "无"})
    rows.append({"分类": "基本信息", "项目": "学生范围", "内容": f"共 {len(filtered_df)} 名学生"})
    rows.append({"分类": "", "项目": "", "内容": ""})

    status = compute_detailed_status(filtered_df)
    rows.append({"分类": "学生状态", "项目": "总人数", "内容": status["total"]})
    rows.append({"分类": "学生状态", "项目": "已完成（全部达标）", "内容": status["fully_passed"]})
    rows.append({"分类": "学生状态", "项目": "部分缺项", "内容": status["partially_missing"]})
    rows.append({"分类": "学生状态", "项目": "完全缺考", "内容": status["fully_absent"]})
    rows.append({"分类": "学生状态", "项目": "单项不及格", "内容": status["single_fail"]})
    rows.append({"分类": "学生状态", "项目": "完成率(%)", "内容": round(status["fully_passed"] / status["total"] * 100, 1) if status["total"] > 0 else 0})
    rows.append({"分类": "", "项目": "", "内容": ""})

    _, _, ss = compute_level_stats(filtered_df)
    if ss:
        rows.append({"分类": "成绩统计", "项目": "参评人数", "内容": ss.get("tested_count", 0)})
        rows.append({"分类": "成绩统计", "项目": "平均分", "内容": ss.get("avg_score", 0)})
        rows.append({"分类": "成绩统计", "项目": "最高分", "内容": ss.get("max_score", 0)})
        rows.append({"分类": "成绩统计", "项目": "最低分", "内容": ss.get("min_score", 0)})
        rows.append({"分类": "成绩统计", "项目": "及格率(%)", "内容": ss.get("pass_rate", 0)})
        rows.append({"分类": "成绩统计", "项目": "良好率(%)", "内容": ss.get("good_rate", 0)})
        rows.append({"分类": "成绩统计", "项目": "优秀率(%)", "内容": ss.get("excellent_rate", 0)})
        rows.append({"分类": "", "项目": "", "内容": ""})

    retest_list, retest_sum = generate_retest_list(filtered_df)
    rows.append({"分类": "补测情况", "项目": "待补测总人数", "内容": retest_sum.get("total", 0)})
    rows.append({"分类": "补测情况", "项目": "完全缺考", "内容": retest_sum.get("fully_absent", 0)})
    rows.append({"分类": "补测情况", "项目": "部分缺项", "内容": retest_sum.get("partially_missing", 0)})
    rows.append({"分类": "补测情况", "项目": "单项不及格", "内容": retest_sum.get("single_fail", 0)})
    rows.append({"分类": "", "项目": "", "内容": ""})

    valid_dfs = _load_validation_sheets_filtered(grade_key, semester, filtered_df)
    rows.append({"分类": "校验问题", "项目": "问题总数", "内容": sum(len(vdf) for _, vdf in valid_dfs)})
    for name, vdf in valid_dfs:
        rows.append({"分类": "校验问题", "项目": name, "内容": f"{len(vdf)} 条"})

    return pd.DataFrame(rows)


def build_sheets(
    filtered_df: pd.DataFrame,
    grade_key: str,
    semester: str,
    grade: Optional[str],
    filters_desc: List[str],
) -> List[Tuple[str, pd.DataFrame]]:
    sheets = []

    overview = build_info_sheet(filtered_df, grade_key, semester, grade, filters_desc)
    sheets.append(("筛选说明和校验摘要", overview))

    formatted = format_for_export(filtered_df)
    sheets.append(("学生成绩", formatted))

    if "total_score" in filtered_df.columns and filtered_df["total_score"].notna().any():
        ranking = generate_overall_ranking(filtered_df)
        if not ranking.empty:
            sheets.append(("总分排名", ranking))

        failed = generate_failed_list(filtered_df)
        if not failed.empty:
            sheets.append(("未达标名单", failed))

        retest, retest_sum = generate_retest_list(filtered_df)
        if not retest.empty:
            sheets.append(("补测名单", retest))
            retest_sum_df = retest_summary_to_df(retest_sum)
            sheets.append(("补测原因汇总", retest_sum_df))

        class_stats = calculate_class_stats(filtered_df)
        if not class_stats.empty:
            sheets.append(("班级统计", class_stats))

    valid_dfs = _load_validation_sheets_filtered(grade_key, semester, filtered_df)
    for name, vdf in valid_dfs:
        sheets.append((name, vdf))

    return sheets


def _load_validation_sheets_filtered(
    grade_key: str, semester: str, filtered_df: pd.DataFrame
) -> List[Tuple[str, pd.DataFrame]]:
    """加载校验问题表，并按当前筛选后的学号过滤，只保留同一批学生"""
    result = []
    valid_path = get_data_path(semester, grade_key, "validation_summary.json")
    if not valid_path.exists():
        return result

    from .utils import load_json
    valid_summary = load_json(valid_path)
    if valid_summary.get("total_issues", 0) <= 0:
        return result

    valid_ids = set(filtered_df["student_id"].dropna().tolist()) if "student_id" in filtered_df.columns else set()

    vnames_map = {
        "duplicate_ids": "校验_重复学号",
        "missing_info": "校验_信息缺失",
        "absent_students": "校验_缺考学生",
        "missing_projects": "校验_项目缺失",
        "abnormal_values": "校验_异常值",
    }
    for vkey, vname in vnames_map.items():
        vpath = get_data_path(semester, grade_key, f"validation_{vkey}.pkl")
        if vpath.exists():
            vdf = load_pickle(vpath)
            if not vdf.empty and valid_ids and "student_id" in vdf.columns:
                vdf = vdf[vdf["student_id"].isin(valid_ids)]
            if not vdf.empty:
                result.append((vname, vdf))
    return result


def export_data(
    semester: str,
    grade: Optional[str] = None,
    output_dir: str = "./output",
    output_format: str = "xlsx",
    class_name: Optional[str] = None,
    level: Optional[str] = None,
    project: Optional[str] = None,
    workbook: bool = False,
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

    filters_desc = []
    if class_name:
        filters_desc.append(f"班级={class_name}")
    if level:
        filters_desc.append(f"等级={level}")
    if project:
        filters_desc.append(f"项目={PROJECT_NAMES.get(project, project)}")
    if filters_desc:
        print(f"  筛选条件: {', '.join(filters_desc)}")

    formatted_df = format_for_export(filtered_df)

    print("\n数据预览:")
    print_table(formatted_df)

    export_files = {}

    if workbook and output_format != "xlsx":
        print(f"警告: 工作簿模式仅支持 xlsx，自动切换为 xlsx 格式")
        output_format = "xlsx"

    if not preview:
        output_path = ensure_output_dir(output_dir)
        suffix = build_file_suffix(semester, grade, class_name, level, project)

        if workbook:
            sheets = build_sheets(filtered_df, grade_key, semester, grade, filters_desc)
            wb_file = output_path / f"体测工作簿_{suffix}.xlsx"
            save_workbook(sheets, wb_file)
            export_files["体测工作簿"] = str(wb_file)
            print(f"\n✓ 已导出工作簿: {wb_file}")
            print(f"  包含 {len(sheets)} 个 sheet: {', '.join([n for n, _ in sheets])}")
        else:
            main_file = output_path / f"学生成绩_{suffix}.{output_format}"
            save_dataframe(formatted_df, main_file)
            export_files["学生成绩"] = str(main_file)
            print(f"\n✓ 已导出: {main_file}")

            if not filtered_df.empty and "total_score" in filtered_df.columns:
                ranking = generate_overall_ranking(filtered_df)
                if not ranking.empty:
                    rank_file = output_path / f"总分排名_{suffix}.{output_format}"
                    save_dataframe(ranking, rank_file)
                    export_files["总分排名"] = str(rank_file)
                    print(f"✓ 已导出: {rank_file}")

                failed = generate_failed_list(filtered_df)
                if not failed.empty:
                    failed_file = output_path / f"未达标名单_{suffix}.{output_format}"
                    save_dataframe(failed, failed_file)
                    export_files["未达标名单"] = str(failed_file)
                    print(f"✓ 已导出: {failed_file}")

                retest, retest_sum = generate_retest_list(filtered_df)
                if not retest.empty:
                    retest_file = output_path / f"补测名单_{suffix}.{output_format}"
                    save_dataframe(retest, retest_file)
                    export_files["补测名单"] = str(retest_file)
                    print(f"✓ 已导出: {retest_file}")

                    retest_sum_file = output_path / f"补测原因汇总_{suffix}.{output_format}"
                    retest_sum_df = retest_summary_to_df(retest_sum)
                    save_dataframe(retest_sum_df, retest_sum_file)
                    export_files["补测原因汇总"] = str(retest_sum_file)
                    print(f"✓ 已导出: {retest_sum_file}")

                class_stats = calculate_class_stats(filtered_df)
                if not class_stats.empty:
                    class_file = output_path / f"班级统计_{suffix}.{output_format}"
                    save_dataframe(class_stats, class_file)
                    export_files["班级统计"] = str(class_file)
                    print(f"✓ 已导出: {class_file}")

            valid_dfs = _load_validation_sheets_filtered(grade_key, semester, filtered_df)
            for name, vdf in valid_dfs:
                vfile = output_path / f"{name}_{suffix}.{output_format}"
                save_dataframe(vdf, vfile)
                export_files[name] = str(vfile)
                print(f"✓ 已导出: {vfile}")

            print(f"\n共导出 {len(export_files)} 个文件至: {output_path}")

    return {
        "filtered_data": filtered_df,
        "formatted_data": formatted_df,
        "export_files": export_files,
    }
