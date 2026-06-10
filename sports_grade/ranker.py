"""排名模块

负责生成各类排名和统计报表：
- 学生总分排名
- 进步榜（与上学期对比）
- 未达标名单
- 补测名单（合并缺考、项目缺失、单项不及格）
- 班级对比表

补测名单的原因分类严格对应 reporter 中的状态：
- 完全缺考：所有必修项目原始值均缺失
- 部分缺项：有必修项目原始值缺失，但不是全缺
- 单项不及格：所有必修项目有原始值，但有单项得分<60
"""

from typing import Dict, List, Optional, Tuple
from pathlib import Path

import pandas as pd
import numpy as np

from .standards import (
    PROJECTS,
    PROJECT_NAMES,
    GRADES,
    GENDERS,
    get_required_projects,
    get_score_level,
)
from .utils import (
    get_data_path,
    load_pickle,
    save_pickle,
    save_json,
    print_table,
)


def generate_overall_ranking(df: pd.DataFrame) -> pd.DataFrame:
    if "total_score" not in df.columns:
        return pd.DataFrame()

    ranked = df[df["total_score"].notna()].copy()
    ranked = ranked.sort_values("total_score", ascending=False)
    ranked = ranked.reset_index(drop=True)
    ranked.index = ranked.index + 1
    ranked.index.name = "排名"
    ranked = ranked.reset_index()

    display_cols = ["排名", "student_id", "name", "gender", "class_name", "total_score", "level"]
    result = ranked[display_cols].copy()
    result.columns = ["排名", "学号", "姓名", "性别", "班级", "总分", "等级"]
    return result


def generate_progress_ranking(
    current_df: pd.DataFrame,
    previous_df: pd.DataFrame,
) -> pd.DataFrame:
    if "total_score" not in current_df.columns or "total_score" not in previous_df.columns:
        return pd.DataFrame()

    current = current_df[current_df["total_score"].notna()][
        ["student_id", "name", "class_name", "total_score", "level"]
    ].copy()
    previous = previous_df[previous_df["total_score"].notna()][
        ["student_id", "total_score"]
    ].copy()

    current.columns = ["学号", "姓名", "班级", "总分", "等级"]
    previous.columns = ["学号", "上次总分"]

    merged = pd.merge(current, previous, on="学号", how="inner")
    if merged.empty:
        return pd.DataFrame()

    merged["进步分数"] = merged["总分"] - merged["上次总分"]
    merged = merged.sort_values("进步分数", ascending=False)
    merged = merged.reset_index(drop=True)
    merged.index = merged.index + 1
    merged.index.name = "进步排名"
    merged = merged.reset_index()

    return merged[["进步排名", "学号", "姓名", "班级", "上次总分", "总分", "进步分数", "等级"]]


def generate_failed_list(df: pd.DataFrame) -> pd.DataFrame:
    if "total_score" not in df.columns:
        return pd.DataFrame()

    failed = df[df["total_score"].notna() & (df["total_score"] < 60)].copy()
    if failed.empty:
        return pd.DataFrame()

    failed = failed.sort_values("total_score")
    failed = failed.reset_index(drop=True)
    failed.index = failed.index + 1
    failed.index.name = "序号"
    failed = failed.reset_index()

    display_cols = ["序号", "student_id", "name", "gender", "class_name", "total_score", "level"]
    result = failed[display_cols].copy()
    result.columns = ["序号", "学号", "姓名", "性别", "班级", "总分", "等级"]
    return result


def generate_retest_list(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict]:
    """生成补测名单，同时返回原因分类汇总，和明细对得上。

    每条学生记录标记"原因分类"：
    - 完全缺考：所有必修项目原始值缺失
    - 部分缺项：有必修项目原始值缺失，但不是全缺
    - 单项不及格：所有必修项目有原始值，但有单项得分<60

    分类汇总和明细人数可以对得上：
    - 完全缺考人数 + 部分缺项人数 + 单项不及格人数 = 待补测总人数
    - 项目级"缺项人数"和"不及格人数"也分别统计
    """
    result_rows = []

    count_fully_absent = 0
    count_partially_missing = 0
    count_single_fail = 0

    per_project_missing = {}
    per_project_fail = {}

    for idx, row in df.iterrows():
        gender = row.get("gender", "")
        required = get_required_projects(gender) if gender in GENDERS else []

        missing_projs = []
        fail_projs = []

        for proj in required:
            proj_name = PROJECT_NAMES.get(proj, proj)
            score_col = f"{proj}_score"
            raw_value = row.get(proj)
            score = row.get(score_col)

            value_missing = False
            if proj not in df.columns:
                value_missing = True
            elif pd.isna(raw_value) or (isinstance(raw_value, str) and str(raw_value).strip() == ""):
                value_missing = True

            if value_missing:
                missing_projs.append((proj, proj_name))
                per_project_missing[proj_name] = per_project_missing.get(proj_name, 0) + 1
            elif pd.notna(score) and float(score) < 60:
                fail_projs.append((proj, proj_name, int(float(score))))
                per_project_fail[proj_name] = per_project_fail.get(proj_name, 0) + 1

        if not missing_projs and not fail_projs:
            continue

        if len(missing_projs) == len(required) and len(required) > 0:
            reason_cat = "完全缺考"
            count_fully_absent += 1
        elif len(missing_projs) > 0:
            reason_cat = "部分缺项"
            count_partially_missing += 1
        else:
            reason_cat = "单项不及格"
            count_single_fail += 1

        total_score = row.get("total_score", None)
        level = row.get("level", None)

        all_reasons = []
        for _, pname in missing_projs:
            all_reasons.append(f"{pname}(缺考)")
        for _, pname, sc in fail_projs:
            all_reasons.append(f"{pname}(不及格({sc}分))")

        project_names = [n for _, n in missing_projs] + [n for _, n, _ in fail_projs]

        row_data = {
            "学号": row.get("student_id", ""),
            "姓名": row.get("name", ""),
            "性别": gender,
            "班级": row.get("class_name", ""),
            "总分": round(float(total_score), 1) if pd.notna(total_score) and total_score is not None else None,
            "等级": level if pd.notna(level) else "缺考",
            "需补测项目数": len(all_reasons),
            "需补测项目": ", ".join(project_names),
            "补测原因": ", ".join(all_reasons),
            "原因分类": reason_cat,
        }
        result_rows.append(row_data)

    if not result_rows:
        empty_df = pd.DataFrame()
        summary = {
            "total": 0,
            "fully_absent": 0,
            "partially_missing": 0,
            "single_fail": 0,
            "per_project_missing": {},
            "per_project_fail": {},
        }
        return empty_df, summary

    result = pd.DataFrame(result_rows)
    result = result.sort_values(["班级", "需补测项目数"], ascending=[True, False])
    result = result.reset_index(drop=True)
    result.index = result.index + 1
    result.index.name = "序号"
    result = result.reset_index()

    summary = {
        "total": len(result_rows),
        "fully_absent": count_fully_absent,
        "partially_missing": count_partially_missing,
        "single_fail": count_single_fail,
        "per_project_missing": per_project_missing,
        "per_project_fail": per_project_fail,
    }

    return result, summary


def print_retest_summary(summary: Dict) -> None:
    print(f"共 {summary['total']} 名学生需要补测:")
    print(f"  - 完全缺考:   {summary['fully_absent']} 人")
    print(f"  - 部分缺项:   {summary['partially_missing']} 人")
    print(f"  - 单项不及格: {summary['single_fail']} 人")
    if summary['per_project_missing']:
        print(f"\n  按项目原始缺项人数:")
        for pn, cnt in sorted(summary['per_project_missing'].items(), key=lambda x: -x[1]):
            print(f"    - {pn}: {cnt} 人")
    if summary['per_project_fail']:
        print(f"\n  按项目单项不及格人数:")
        for pn, cnt in sorted(summary['per_project_fail'].items(), key=lambda x: -x[1]):
            print(f"    - {pn}: {cnt} 人")


def retest_summary_to_df(summary: Dict) -> pd.DataFrame:
    rows = [
        {"分类": "待补测总人数", "人数": summary["total"]},
        {"分类": "完全缺考", "人数": summary["fully_absent"]},
        {"分类": "部分缺项", "人数": summary["partially_missing"]},
        {"分类": "单项不及格", "人数": summary["single_fail"]},
    ]
    if summary["per_project_missing"]:
        rows.append({"分类": "", "人数": None})
        rows.append({"分类": "【按项目原始缺项】", "人数": None})
        for pn, cnt in sorted(summary["per_project_missing"].items(), key=lambda x: -x[1]):
            rows.append({"分类": f"  {pn}", "人数": cnt})
    if summary["per_project_fail"]:
        rows.append({"分类": "", "人数": None})
        rows.append({"分类": "【按项目单项不及格】", "人数": None})
        for pn, cnt in sorted(summary["per_project_fail"].items(), key=lambda x: -x[1]):
            rows.append({"分类": f"  {pn}", "人数": cnt})
    return pd.DataFrame(rows)


def generate_class_comparison(
    current_stats: pd.DataFrame,
    previous_stats: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    if current_stats.empty:
        return pd.DataFrame()

    result = current_stats.copy()

    if previous_stats is not None and not previous_stats.empty:
        prev = previous_stats[["班级", "平均分"]].copy()
        prev.columns = ["班级", "上次平均分"]
        result = pd.merge(result, prev, on="班级", how="left")
        result["平均分变化"] = result["平均分"] - result["上次平均分"]
        result["平均分变化"] = result["平均分变化"].round(1)

    return result


def rank_data(
    semester: str,
    grade: Optional[str] = None,
    previous_semester: Optional[str] = None,
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

    class_stats_path = get_data_path(semester, grade_key, "class_stats.pkl")
    class_stats = load_pickle(class_stats_path) if class_stats_path.exists() else pd.DataFrame()

    results = {}

    print("\n" + "=" * 60)
    print("1. 学生总分排名")
    print("=" * 60)
    overall_ranking = generate_overall_ranking(df)
    results["overall_ranking"] = overall_ranking
    if overall_ranking.empty:
        print("无排名数据")
    else:
        print_table(overall_ranking.head(20))

    print("\n" + "=" * 60)
    print("2. 未达标名单（总分<60分）")
    print("=" * 60)
    failed_list = generate_failed_list(df)
    results["failed_list"] = failed_list
    if failed_list.empty:
        print("✓ 没有未达标学生，所有学生均已达标！")
    else:
        print(f"共 {len(failed_list)} 名学生未达标:")
        print_table(failed_list)

    print("\n" + "=" * 60)
    print("3. 补测名单（缺考+项目缺失+单项不及格）")
    print("=" * 60)
    retest_list, retest_summary = generate_retest_list(df)
    results["retest_list"] = retest_list
    results["retest_summary"] = retest_summary
    if retest_list.empty:
        print("✓ 没有需要补测的学生")
    else:
        print_retest_summary(retest_summary)
        print()
        print_table(retest_list)

    print("\n" + "=" * 60)
    print("4. 班级对比表")
    print("=" * 60)
    if class_stats.empty:
        print("无班级统计数据")
        results["class_comparison"] = class_stats
    else:
        if previous_semester:
            prev_class_path = get_data_path(previous_semester, grade_key, "class_stats.pkl")
            if prev_class_path.exists():
                prev_class_stats = load_pickle(prev_class_path)
                class_compare = generate_class_comparison(class_stats, prev_class_stats)
                results["class_comparison"] = class_compare
                print_table(class_compare)
            else:
                results["class_comparison"] = class_stats
                print_table(class_stats)
        else:
            results["class_comparison"] = class_stats
            print_table(class_stats)

    if previous_semester:
        print("\n" + "=" * 60)
        print("5. 进步榜")
        print("=" * 60)
        prev_scored_path = get_data_path(previous_semester, grade_key, "scored_data.pkl")
        if prev_scored_path.exists():
            prev_df = load_pickle(prev_scored_path)
            progress = generate_progress_ranking(df, prev_df)
            results["progress_ranking"] = progress
            if progress.empty:
                print("无进步榜数据（可能没有匹配的上学期成绩）")
            else:
                print_table(progress.head(20))
        else:
            print(f"上学期 ({previous_semester}) 数据不存在，跳过进步榜生成")

    print("\n" + "=" * 60)
    print("排名统计完成")
    print("=" * 60)

    if not preview:
        for name, result_df in results.items():
            if isinstance(result_df, pd.DataFrame) and not result_df.empty:
                out_path = get_data_path(semester, grade_key, f"rank_{name}.pkl")
                save_pickle(result_df, out_path)

        summary = {
            "semester": semester,
            "grade": grade,
            "previous_semester": previous_semester,
            "total_students": len(df),
            "failed_count": len(failed_list) if not failed_list.empty else 0,
            "retest_count": retest_summary.get("total", 0),
            "retest_summary": retest_summary,
            "has_progress": previous_semester and "progress_ranking" in results,
        }
        summary_path = get_data_path(semester, grade_key, "rank_summary.json")
        save_json(summary, summary_path)
        print(f"\n排名结果已保存至: {get_data_path(semester, grade_key, '')}")

    return results
