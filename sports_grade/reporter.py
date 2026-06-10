"""报表模块

一次性输出某学期年级的体测概览：
- 参测人数、缺考人数、部分缺项人数
- 各等级分布
- 班级均分对比
- 待补测人数及项目统计
- 支持按班级、性别、是否待补测筛选
- 支持学期对比视角
- 支持终端预览和导出到目录
"""

from typing import Dict, Optional, Tuple
from pathlib import Path

import pandas as pd
import numpy as np

from .standards import PROJECTS, PROJECT_NAMES, GENDERS, get_required_projects, get_score_level
from .ranker import generate_retest_list, generate_failed_list, generate_overall_ranking
from .scorer import calculate_class_stats, calculate_individual_scores, calculate_total_score
from .utils import (
    get_data_path,
    load_pickle,
    load_json,
    save_json,
    save_dataframe,
    ensure_output_dir,
    print_table,
)


def filter_report_data(
    df: pd.DataFrame,
    class_name: Optional[str] = None,
    gender: Optional[str] = None,
    only_retest: bool = False,
) -> pd.DataFrame:
    result = df.copy()

    if class_name and "class_name" in result.columns:
        result = result[result["class_name"] == class_name]

    if gender and "gender" in result.columns:
        result = result[result["gender"] == gender]

    if only_retest:
        retest_list = generate_retest_list(result)
        if not retest_list.empty:
            retest_ids = set(retest_list["学号"].tolist())
            result = result[result["student_id"].isin(retest_ids)]
        else:
            result = result.iloc[0:0]

    return result


def compute_status_stats(df: pd.DataFrame) -> Tuple[int, int, int, int]:
    total = len(df)

    completed_count = 0
    incomplete_count = 0
    absent_count = 0

    for idx, row in df.iterrows():
        gender = row.get("gender", "")
        required = get_required_projects(gender) if gender in GENDERS else []

        missing_count = 0
        for proj in required:
            if proj not in df.columns:
                missing_count += 1
                continue
            val = row.get(proj)
            if pd.isna(val) or (isinstance(val, str) and str(val).strip() == ""):
                missing_count += 1

        if missing_count == 0:
            completed_count += 1
        elif missing_count == len(required):
            absent_count += 1
        else:
            incomplete_count += 1

    return total, completed_count, incomplete_count, absent_count


def compute_retest_project_stats(df: pd.DataFrame) -> Dict[str, int]:
    retest_list = generate_retest_list(df)
    if retest_list.empty:
        return {}

    project_counter = {}
    for _, row in retest_list.iterrows():
        for proj_str in str(row.get("需补测项目", "")).split(", "):
            proj_str = proj_str.strip()
            if proj_str:
                project_counter[proj_str] = project_counter.get(proj_str, 0) + 1

    return project_counter


def compute_level_stats(df: pd.DataFrame) -> Tuple[Dict, Dict, Dict]:
    level_distribution = {}
    level_pcts = {}
    score_stats = {}

    if "total_score" not in df.columns:
        return level_distribution, level_pcts, score_stats

    scored_df = df[df["total_score"].notna()]
    tested_count = len(scored_df)

    if tested_count == 0:
        return level_distribution, level_pcts, score_stats

    level_counts = scored_df["level"].value_counts()
    for level_name in ["优秀", "良好", "及格", "不及格"]:
        cnt = int(level_counts.get(level_name, 0))
        level_distribution[level_name] = cnt
        level_pcts[level_name] = round(cnt / tested_count * 100, 1)

    score_stats = {
        "tested_count": tested_count,
        "avg_score": round(scored_df["total_score"].mean(), 1),
        "max_score": round(scored_df["total_score"].max(), 1),
        "min_score": round(scored_df["total_score"].min(), 1),
        "pass_rate": round((scored_df["total_score"] >= 60).sum() / tested_count * 100, 1),
        "excellent_rate": round((scored_df["total_score"] >= 90).sum() / tested_count * 100, 1),
        "good_rate": round(((scored_df["total_score"] >= 80) & (scored_df["total_score"] < 90)).sum() / tested_count * 100, 1),
        "fail_rate": round((scored_df["total_score"] < 60).sum() / tested_count * 100, 1),
    }

    return level_distribution, level_pcts, score_stats


def print_status_block(total: int, completed: int, incomplete: int, absent: int) -> None:
    print(f"\n{'─' * 40}")
    print(f"  总人数:     {total}")
    print(f"  全部完成:   {completed}")
    print(f"  部分缺项:   {incomplete}")
    print(f"  完全缺考:   {absent}")
    print(f"  完成率:     {round(completed / total * 100, 1) if total > 0 else 0}%")
    print(f"{'─' * 40}")


def print_level_block(level_distribution: Dict, level_pcts: Dict, score_stats: Dict) -> None:
    if not score_stats:
        return

    print(f"\n  等级分布 (参评 {score_stats['tested_count']} 人):")
    print(f"  ┌──────────┬──────┬──────────┐")
    print(f"  │ 等级     │ 人数 │ 占比     │")
    print(f"  ├──────────┼──────┼──────────┤")
    for level_name in ["优秀", "良好", "及格", "不及格"]:
        cnt = level_distribution.get(level_name, 0)
        pct = level_pcts.get(level_name, 0)
        print(f"  │ {level_name:<8} │ {cnt:>4} │ {pct:>6.1f}%  │")
    print(f"  └──────────┴──────┴──────────┘")

    print(f"\n  总分统计:")
    print(f"    平均分: {score_stats['avg_score']}  最高分: {score_stats['max_score']}  最低分: {score_stats['min_score']}")
    print(f"    及格率: {score_stats['pass_rate']}%  良好率: {score_stats['good_rate']}%  优秀率: {score_stats['excellent_rate']}%")


def print_retest_block(retest_count: int, project_stats: Dict) -> None:
    print(f"\n  待补测人数: {retest_count}")
    if project_stats:
        print(f"\n  补测项目统计:")
        for proj_name, cnt in sorted(project_stats.items(), key=lambda x: -x[1]):
            print(f"    - {proj_name}: {cnt} 人")


def generate_report(
    semester: str,
    grade: Optional[str] = None,
    class_name: Optional[str] = None,
    gender: Optional[str] = None,
    only_retest: bool = False,
    previous_semester: Optional[str] = None,
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
        if "total_score" not in df.columns:
            df = calculate_individual_scores(df)
            df["total_score"] = df.apply(calculate_total_score, axis=1)
            df["level"] = df["total_score"].apply(
                lambda x: get_score_level(x) if pd.notna(x) else None
            )

    grade_label = grade or "全部年级"
    filter_labels = []
    if class_name:
        filter_labels.append(f"班级={class_name}")
    if gender:
        filter_labels.append(f"性别={gender}")
    if only_retest:
        filter_labels.append("仅待补测")

    df = filter_report_data(df, class_name=class_name, gender=gender, only_retest=only_retest)

    print("=" * 60)
    print(f"  体测概览报表  {semester} {grade_label}")
    if filter_labels:
        print(f"  筛选: {', '.join(filter_labels)}")
    print("=" * 60)

    total, completed, incomplete, absent = compute_status_stats(df)
    print_status_block(total, completed, incomplete, absent)

    level_distribution, level_pcts, score_stats = compute_level_stats(df)
    print_level_block(level_distribution, level_pcts, score_stats)

    class_stats = pd.DataFrame()
    if not class_name and "class_name" in df.columns and not df.empty:
        class_stats = calculate_class_stats(df)
        if not class_stats.empty:
            print(f"\n  班级均分对比:")
            print_table(class_stats)

    retest_list = generate_retest_list(df)
    retest_count = len(retest_list) if not retest_list.empty else 0
    project_stats = compute_retest_project_stats(df)
    print_retest_block(retest_count, project_stats)

    if not retest_list.empty:
        print(f"\n  补测名单（前10）:")
        print_table(retest_list.head(10))

    summary = {
        "semester": semester,
        "grade": grade,
        "class_name": class_name,
        "gender": gender,
        "only_retest": only_retest,
        "total_students": total,
        "completed_count": completed,
        "incomplete_count": incomplete,
        "absent_count": absent,
        "completion_rate": round(completed / total * 100, 1) if total > 0 else 0,
        "level_distribution": level_distribution,
        "level_pcts": level_pcts,
        "score_stats": score_stats,
        "retest_count": retest_count,
        "retest_project_stats": project_stats,
    }

    if previous_semester:
        prev_raw_path = get_data_path(previous_semester, grade_key, "raw_data.pkl")
        prev_scored_path = get_data_path(previous_semester, grade_key, "scored_data.pkl")

        if prev_scored_path.exists() or prev_raw_path.exists():
            if prev_scored_path.exists():
                prev_df = load_pickle(prev_scored_path)
            else:
                prev_df = load_pickle(prev_raw_path)
                if "total_score" not in prev_df.columns:
                    prev_df = calculate_individual_scores(prev_df)
                    prev_df["total_score"] = prev_df.apply(calculate_total_score, axis=1)
                    prev_df["level"] = prev_df["total_score"].apply(
                        lambda x: get_score_level(x) if pd.notna(x) else None
                    )

            prev_df = filter_report_data(prev_df, class_name=class_name, gender=gender, only_retest=only_retest)

            prev_total, prev_completed, prev_incomplete, prev_absent = compute_status_stats(prev_df)
            prev_level_dist, prev_level_pcts, prev_score_stats = compute_level_stats(prev_df)
            prev_retest_list = generate_retest_list(prev_df)
            prev_retest_count = len(prev_retest_list) if not prev_retest_list.empty else 0

            comparison = {
                "current_semester": semester,
                "previous_semester": previous_semester,
                "total_students": {"当前": total, "上学期": prev_total, "变化": total - prev_total},
                "completed_count": {"当前": completed, "上学期": prev_completed, "变化": completed - prev_completed},
                "absent_count": {"当前": absent, "上学期": prev_absent, "变化": absent - prev_absent},
                "avg_score": {
                    "当前": score_stats.get("avg_score"),
                    "上学期": prev_score_stats.get("avg_score"),
                    "变化": round(score_stats.get("avg_score", 0) - (prev_score_stats.get("avg_score") or 0), 1) if score_stats.get("avg_score") and prev_score_stats.get("avg_score") else None,
                },
                "pass_rate": {
                    "当前": score_stats.get("pass_rate"),
                    "上学期": prev_score_stats.get("pass_rate"),
                    "变化": round(score_stats.get("pass_rate", 0) - (prev_score_stats.get("pass_rate") or 0), 1) if score_stats.get("pass_rate") and prev_score_stats.get("pass_rate") else None,
                },
                "excellent_rate": {
                    "当前": score_stats.get("excellent_rate"),
                    "上学期": prev_score_stats.get("excellent_rate"),
                    "变化": round(score_stats.get("excellent_rate", 0) - (prev_score_stats.get("excellent_rate") or 0), 1) if score_stats.get("excellent_rate") and prev_score_stats.get("excellent_rate") else None,
                },
                "retest_count": {"当前": retest_count, "上学期": prev_retest_count, "变化": retest_count - prev_retest_count},
            }
            summary["comparison"] = comparison

            print(f"\n{'=' * 60}")
            print(f"  学期对比  {previous_semester} → {semester}")
            print(f"{'=' * 60}")

            rows = [
                ["总人数", total, prev_total, total - prev_total],
                ["全部完成", completed, prev_completed, completed - prev_completed],
                ["完全缺考", absent, prev_absent, absent - prev_absent],
                ["平均分", score_stats.get("avg_score", "-"), prev_score_stats.get("avg_score", "-"),
                 round(score_stats.get("avg_score", 0) - (prev_score_stats.get("avg_score") or 0), 1) if score_stats.get("avg_score") and prev_score_stats.get("avg_score") else "-"],
                ["及格率(%)", score_stats.get("pass_rate", "-"), prev_score_stats.get("pass_rate", "-"),
                 round(score_stats.get("pass_rate", 0) - (prev_score_stats.get("pass_rate") or 0), 1) if score_stats.get("pass_rate") and prev_score_stats.get("pass_rate") else "-"],
                ["优秀率(%)", score_stats.get("excellent_rate", "-"), prev_score_stats.get("excellent_rate", "-"),
                 round(score_stats.get("excellent_rate", 0) - (prev_score_stats.get("excellent_rate") or 0), 1) if score_stats.get("excellent_rate") and prev_score_stats.get("excellent_rate") else "-"],
                ["待补测人数", retest_count, prev_retest_count, retest_count - prev_retest_count],
            ]

            print(f"\n  {'指标':<12} {'当前学期':>10} {'上学期':>10} {'变化':>10}")
            print(f"  {'─' * 46}")
            for row in rows:
                name, cur, prev, chg = row
                cur_str = str(cur) if cur is not None else "-"
                prev_str = str(prev) if prev is not None else "-"
                chg_str = str(chg) if chg is not None and chg != "-" else "-"
                if isinstance(chg, (int, float)) and chg > 0:
                    chg_str = f"+{chg}"
                print(f"  {name:<12} {cur_str:>10} {prev_str:>10} {chg_str:>10}")

    print("\n" + "=" * 60)
    print("  报表生成完成")
    print("=" * 60)

    if not preview and output_dir:
        output_path = ensure_output_dir(output_dir)
        suffix_parts = [semester]
        if grade:
            suffix_parts.append(grade)
        if class_name:
            suffix_parts.append(class_name)
        if gender:
            suffix_parts.append(gender)
        if only_retest:
            suffix_parts.append("待补测")
        suffix = "_".join(suffix_parts)

        summary_file = output_path / f"体测概览_{suffix}.json"
        save_json(summary, summary_file)
        print(f"\n✓ 概览摘要已导出: {summary_file}")

        if not class_stats.empty:
            class_file = output_path / f"班级均分对比_{suffix}.{output_format}"
            save_dataframe(class_stats, class_file)
            print(f"✓ 班级统计已导出: {class_file}")

        if not retest_list.empty:
            retest_file = output_path / f"补测名单_{suffix}.{output_format}"
            save_dataframe(retest_list, retest_file)
            print(f"✓ 补测名单已导出: {retest_file}")

        if score_stats:
            level_df = pd.DataFrame([
                {"等级": k, "人数": v, "占比(%)": level_pcts.get(k, 0)}
                for k, v in level_distribution.items()
            ])
            level_file = output_path / f"等级分布_{suffix}.{output_format}"
            save_dataframe(level_df, level_file)
            print(f"✓ 等级分布已导出: {level_file}")

        if previous_semester and "comparison" in summary:
            comp = summary["comparison"]
            comp_rows = []
            for key in ["total_students", "completed_count", "absent_count",
                        "avg_score", "pass_rate", "excellent_rate", "retest_count"]:
                item = comp.get(key, {})
                names_cn = {
                    "total_students": "总人数",
                    "completed_count": "全部完成",
                    "absent_count": "完全缺考",
                    "avg_score": "平均分",
                    "pass_rate": "及格率(%)",
                    "excellent_rate": "优秀率(%)",
                    "retest_count": "待补测人数",
                }
                comp_rows.append({
                    "指标": names_cn.get(key, key),
                    f"{semester}": item.get("当前"),
                    f"{previous_semester}": item.get("上学期"),
                    "变化": item.get("变化"),
                })
            comp_df = pd.DataFrame(comp_rows)
            comp_file = output_path / f"学期对比_{suffix}.{output_format}"
            save_dataframe(comp_df, comp_file)
            print(f"✓ 学期对比已导出: {comp_file}")

    return {
        "summary": summary,
        "class_stats": class_stats,
        "retest_list": retest_list,
    }
