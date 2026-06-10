"""报表模块

一次性输出某学期年级的体测概览：
- 参测人数、缺考人数
- 各等级分布
- 班级均分对比
- 待补测人数及项目统计
- 支持终端预览和导出到目录
"""

from typing import Dict, Optional
from pathlib import Path

import pandas as pd
import numpy as np

from .standards import PROJECTS, PROJECT_NAMES, GENDERS, get_required_projects
from .ranker import generate_retest_list
from .scorer import calculate_class_stats
from .utils import (
    get_data_path,
    load_pickle,
    load_json,
    save_json,
    save_dataframe,
    ensure_output_dir,
    print_table,
)


def generate_report(
    semester: str,
    grade: Optional[str] = None,
    output_dir: Optional[str] = None,
    output_format: str = "xlsx",
    preview: bool = False,
) -> Dict:
    grade_key = grade or "all"

    raw_path = get_data_path(semester, grade_key, "raw_data.pkl")
    scored_path = get_data_path(semester, grade_key, "scored_data.pkl")

    if not scored_path.exists() and not raw_path.exists():
        raise FileNotFoundError(
            f"未找到数据，请先执行 import 和 score 命令。\n"
            f"期望路径: {scored_path}"
        )

    if scored_path.exists():
        df = load_pickle(scored_path)
    else:
        df = load_pickle(raw_path)

    total_students = len(df)
    grade_label = grade or "全部年级"

    print("=" * 60)
    print(f"  体测概览报表  {semester} {grade_label}")
    print("=" * 60)

    if "total_score" in df.columns:
        scored_df = df[df["total_score"].notna()]
        unscored_df = df[df["total_score"].isna()]
    else:
        scored_df = pd.DataFrame()
        unscored_df = df

    tested_count = len(scored_df) if not scored_df.empty else 0
    absent_count = 0
    if not unscored_df.empty:
        available_projects = [p for p in PROJECTS if p in unscored_df.columns]
        if available_projects:
            all_missing_mask = pd.Series(True, index=unscored_df.index)
            for proj in available_projects:
                all_missing_mask = all_missing_mask & (
                    unscored_df[proj].isna() |
                    (unscored_df[proj].astype(str).str.strip() == "")
                )
            absent_count = all_missing_mask.sum()

    incomplete_count = total_students - tested_count - absent_count

    print(f"\n{'─' * 40}")
    print(f"  参测人数:   {tested_count}")
    print(f"  部分缺项:   {incomplete_count}")
    print(f"  完全缺考:   {absent_count}")
    print(f"  总人数:     {total_students}")
    print(f"{'─' * 40}")

    level_distribution = {}
    level_pcts = {}
    if not scored_df.empty and "level" in scored_df.columns:
        level_counts = scored_df["level"].value_counts()
        for level_name in ["优秀", "良好", "及格", "不及格"]:
            cnt = level_counts.get(level_name, 0)
            level_distribution[level_name] = int(cnt)
            level_pcts[level_name] = round(cnt / tested_count * 100, 1) if tested_count > 0 else 0

        print(f"\n  等级分布:")
        print(f"  ┌──────────┬──────┬──────────┐")
        print(f"  │ 等级     │ 人数 │ 占比     │")
        print(f"  ├──────────┼──────┼──────────┤")
        for level_name in ["优秀", "良好", "及格", "不及格"]:
            cnt = level_distribution[level_name]
            pct = level_pcts[level_name]
            print(f"  │ {level_name:<8} │ {cnt:>4} │ {pct:>6.1f}%  │")
        print(f"  └──────────┴──────┴──────────┘")

        avg_score = round(scored_df["total_score"].mean(), 1) if tested_count > 0 else None
        max_score = round(scored_df["total_score"].max(), 1) if tested_count > 0 else None
        min_score = round(scored_df["total_score"].min(), 1) if tested_count > 0 else None
        pass_rate = round((scored_df["total_score"] >= 60).sum() / tested_count * 100, 1) if tested_count > 0 else 0
        excellent_rate = round((scored_df["total_score"] >= 90).sum() / tested_count * 100, 1) if tested_count > 0 else 0

        print(f"\n  总分统计:")
        print(f"    平均分: {avg_score}  最高分: {max_score}  最低分: {min_score}")
        print(f"    及格率: {pass_rate}%  优秀率: {excellent_rate}%")

    class_stats = pd.DataFrame()
    if not scored_df.empty and "class_name" in scored_df.columns:
        class_stats = calculate_class_stats(df)
        if not class_stats.empty:
            print(f"\n  班级均分对比:")
            print_table(class_stats)

    retest_list = pd.DataFrame()
    if not df.empty:
        retest_list = generate_retest_list(df)
        retest_count = len(retest_list) if not retest_list.empty else 0
        print(f"\n  待补测人数: {retest_count}")

        if not retest_list.empty:
            project_counter = {}
            for _, row in retest_list.iterrows():
                for proj_str in str(row.get("需补测项目", "")).split(", "):
                    proj_str = proj_str.strip()
                    if proj_str:
                        project_counter[proj_str] = project_counter.get(proj_str, 0) + 1

            if project_counter:
                print(f"\n  补测项目统计:")
                for proj_name, cnt in sorted(project_counter.items(), key=lambda x: -x[1]):
                    print(f"    - {proj_name}: {cnt} 人")

            print(f"\n  补测名单（前10）:")
            print_table(retest_list.head(10))

    report_summary = {
        "semester": semester,
        "grade": grade,
        "total_students": total_students,
        "tested_count": tested_count,
        "incomplete_count": incomplete_count,
        "absent_count": absent_count,
        "level_distribution": level_distribution,
        "level_pcts": level_pcts,
        "retest_count": len(retest_list) if not retest_list.empty else 0,
    }

    if not preview and output_dir:
        output_path = ensure_output_dir(output_dir)
        suffix = f"{semester}"
        if grade:
            suffix += f"_{grade}"

        summary_file = output_path / f"体测概览_{suffix}.json"
        save_json(report_summary, summary_file)
        print(f"\n✓ 概览摘要已导出: {summary_file}")

        if not class_stats.empty:
            class_file = output_path / f"班级均分对比_{suffix}.{output_format}"
            save_dataframe(class_stats, class_file)
            print(f"✓ 班级统计已导出: {class_file}")

        if not retest_list.empty:
            retest_file = output_path / f"补测名单_{suffix}.{output_format}"
            save_dataframe(retest_list, retest_file)
            print(f"✓ 补测名单已导出: {retest_file}")

        if not scored_df.empty:
            level_df = pd.DataFrame([
                {"等级": k, "人数": v, "占比(%)": level_pcts.get(k, 0)}
                for k, v in level_distribution.items()
            ])
            level_file = output_path / f"等级分布_{suffix}.{output_format}"
            save_dataframe(level_df, level_file)
            print(f"✓ 等级分布已导出: {level_file}")

    print("\n" + "=" * 60)
    print("  报表生成完成")
    print("=" * 60)

    return {
        "summary": report_summary,
        "class_stats": class_stats,
        "retest_list": retest_list,
    }
