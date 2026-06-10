"""报表模块

一次性输出某学期年级的体测概览：
- 体测状态：原始缺项、完全缺考、单项不及格分别统计
- 各等级分布、班级均分对比
- 待补测人数及项目统计
- 支持按班级、性别、是否待补测筛选
- 支持学期对比视角（年级总览 + 多班级并排）
- 支持终端预览和导出到目录
"""

from typing import Dict, List, Optional, Tuple
from pathlib import Path

import pandas as pd
import numpy as np

from .standards import PROJECTS, PROJECT_NAMES, GENDERS, get_required_projects, get_score_level
from .ranker import (
    generate_retest_list,
    generate_failed_list,
    generate_overall_ranking,
    print_retest_summary,
    retest_summary_to_df,
)
from .scorer import calculate_class_stats, calculate_individual_scores, calculate_total_score
from .utils import (
    get_data_path,
    load_pickle,
    load_json,
    save_json,
    save_dataframe,
    ensure_output_dir,
    print_table,
    save_workbook,
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
        retest_list, _ = generate_retest_list(result)
        if not retest_list.empty:
            retest_ids = set(retest_list["学号"].tolist())
            result = result[result["student_id"].isin(retest_ids)]
        else:
            result = result.iloc[0:0]

    return result


def compute_detailed_status(df: pd.DataFrame) -> Dict:
    """拆分统计：原始缺项（按项目缺失）、完全缺考、单项不及格、已完成。

    这里口径严格拆分，避免和待补测人数交叉：
    - 完全缺考：所有必修项目均无原始成绩
    - 部分缺项：有必修项目缺原始成绩，但不是全缺
    - 单项不及格：所有必修项目都有原始成绩，但有单项得分<60
    - 已完成：所有必修项目有成绩，且所有单项得分≥60
    这四类互斥且加和=总人数
    """
    total = len(df)
    fully_absent = 0
    partially_missing = 0
    single_fail = 0
    fully_passed = 0

    per_project_missing = {}
    per_project_fail = {}

    for idx, row in df.iterrows():
        gender = row.get("gender", "")
        required = get_required_projects(gender) if gender in GENDERS else []

        missing_projs = []
        fail_projs = []

        for proj in required:
            raw_val = row.get(proj) if proj in df.columns else None
            raw_missing = pd.isna(raw_val) or (isinstance(raw_val, str) and str(raw_val).strip() == "")

            score_val = row.get(f"{proj}_score") if f"{proj}_score" in df.columns else None
            score_fail = (
                score_val is not None
                and pd.notna(score_val)
                and float(score_val) < 60
            )

            if raw_missing:
                missing_projs.append(proj)
                per_project_missing[proj] = per_project_missing.get(proj, 0) + 1
            elif score_fail:
                fail_projs.append(proj)
                per_project_fail[proj] = per_project_fail.get(proj, 0) + 1

        if len(missing_projs) == len(required) and len(required) > 0:
            fully_absent += 1
        elif len(missing_projs) > 0:
            partially_missing += 1
        elif len(fail_projs) > 0:
            single_fail += 1
        else:
            fully_passed += 1

    return {
        "total": total,
        "fully_absent": fully_absent,
        "partially_missing": partially_missing,
        "single_fail": single_fail,
        "fully_passed": fully_passed,
        "per_project_missing": per_project_missing,
        "per_project_fail": per_project_fail,
    }


def compute_retest_project_stats(df: pd.DataFrame) -> Dict[str, int]:
    retest_list, _ = generate_retest_list(df)
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


def _fmt_num(v) -> str:
    """格式化数值显示，0 就显示 0，None 显示 -"""
    if v is None:
        return "-"
    if isinstance(v, float) and v != v:
        return "-"
    if isinstance(v, float):
        if v.is_integer():
            return str(int(v))
        return f"{v:.1f}"
    return str(v)


def _fmt_change(cur, prev) -> str:
    """格式化变化值：两者都为数字时算差，都为 0 显示 0"""
    cur_n = None
    prev_n = None
    try:
        if cur is not None and not (isinstance(cur, float) and cur != cur):
            cur_n = float(cur)
    except (TypeError, ValueError):
        pass
    try:
        if prev is not None and not (isinstance(prev, float) and prev != prev):
            prev_n = float(prev)
    except (TypeError, ValueError):
        pass

    if cur_n is None or prev_n is None:
        return "-"
    diff = round(cur_n - prev_n, 1)
    if diff == 0:
        return "0"
    if diff > 0:
        if diff.is_integer():
            return f"+{int(diff)}"
        return f"+{diff}"
    if diff.is_integer():
        return str(int(diff))
    return str(diff)


def print_detailed_status_block(status: Dict) -> None:
    total = status["total"]
    fa = status["fully_absent"]
    pm = status["partially_missing"]
    sf = status["single_fail"]
    fp = status["fully_passed"]

    print(f"\n{'─' * 48}")
    print(f"  总人数:           {total}")
    print(f"  已完成（全部达标）: {fp}")
    print(f"  部分缺项:         {pm}")
    print(f"  完全缺考:         {fa}")
    print(f"  单项不及格:       {sf}")
    print(f"  完成率:           {round(fp / total * 100, 1) if total > 0 else 0}%")
    print(f"{'─' * 48}")

    if status["per_project_missing"]:
        print(f"\n  按项目原始缺项人数:")
        for proj, cnt in sorted(status["per_project_missing"].items(), key=lambda x: -x[1]):
            print(f"    - {PROJECT_NAMES.get(proj, proj)}: {cnt} 人")

    if status["per_project_fail"]:
        print(f"\n  按项目单项不及格人数:")
        for proj, cnt in sorted(status["per_project_fail"].items(), key=lambda x: -x[1]):
            print(f"    - {PROJECT_NAMES.get(proj, proj)}: {cnt} 人")


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
        print(f"\n  补测项目统计（按需补测学生计）:")
        for proj_name, cnt in sorted(project_stats.items(), key=lambda x: -x[1]):
            print(f"    - {proj_name}: {cnt} 人")


def _class_summary(df: pd.DataFrame) -> pd.DataFrame:
    """对每个班级计算关键指标，用于班级并排对比"""
    rows = []
    if "class_name" not in df.columns or df.empty:
        return pd.DataFrame(rows)

    for cls in sorted(df["class_name"].dropna().unique()):
        sub = df[df["class_name"] == cls]
        status = compute_detailed_status(sub)
        _, _, ss = compute_level_stats(sub)
        retest, _ = generate_retest_list(sub)
        retest_count = len(retest) if not retest.empty else 0

        rows.append({
            "班级": cls,
            "总人数": status["total"],
            "已完成": status["fully_passed"],
            "部分缺项": status["partially_missing"],
            "完全缺考": status["fully_absent"],
            "单项不及格": status["single_fail"],
            "平均分": ss.get("avg_score", 0) if ss else 0,
            "及格率(%)": ss.get("pass_rate", 0) if ss else 0,
            "优秀率(%)": ss.get("excellent_rate", 0) if ss else 0,
            "待补测人数": retest_count,
        })
    return pd.DataFrame(rows)


def print_semester_comparison(
    summary: Dict,
    prev_summary: Dict,
    cur_status: Dict,
    prev_status: Dict,
    cur_score: Dict,
    prev_score: Dict,
    cur_retest: int,
    prev_retest: int,
) -> None:
    semester = summary["semester"]
    previous_semester = summary["previous_semester"]

    print(f"\n{'=' * 60}")
    print(f"  学期对比  {previous_semester} → {semester}")
    print(f"{'=' * 60}")

    rows = [
        ["总人数", cur_status["total"], prev_status["total"]],
        ["已完成（全部达标）", cur_status["fully_passed"], prev_status["fully_passed"]],
        ["部分缺项", cur_status["partially_missing"], prev_status["partially_missing"]],
        ["完全缺考", cur_status["fully_absent"], prev_status["fully_absent"]],
        ["单项不及格", cur_status["single_fail"], prev_status["single_fail"]],
        ["平均分", cur_score.get("avg_score"), prev_score.get("avg_score")],
        ["及格率(%)", cur_score.get("pass_rate"), prev_score.get("pass_rate")],
        ["优秀率(%)", cur_score.get("excellent_rate"), prev_score.get("excellent_rate")],
        ["待补测人数", cur_retest, prev_retest],
    ]

    print(f"\n  {'指标':<18} {semester:>10} {previous_semester:>10} {'变化':>10}")
    print(f"  {'─' * 52}")
    for name, cur, prev in rows:
        chg = _fmt_change(cur, prev)
        print(f"  {name:<18} {_fmt_num(cur):>10} {_fmt_num(prev):>10} {chg:>10}")


def print_class_semester_comparison(
    cur_df: pd.DataFrame,
    prev_df: pd.DataFrame,
    semester: str,
    previous_semester: str,
) -> Optional[pd.DataFrame]:
    cur_class = _class_summary(cur_df)
    prev_class = _class_summary(prev_df)

    if cur_class.empty:
        return None

    merged = cur_class.merge(
        prev_class,
        on="班级",
        how="outer",
        suffixes=(f"_{semester}", f"_{previous_semester}"),
    ).fillna(0)

    display_cols = ["班级"]
    for metric, label in [
        ("总人数", "总人数"),
        ("平均分", "平均分"),
        ("及格率(%)", "及格率(%)"),
        ("优秀率(%)", "优秀率(%)"),
        ("待补测人数", "待补测人数"),
    ]:
        c_cur = f"{metric}_{semester}"
        c_prev = f"{metric}_{previous_semester}"
        c_chg = f"{metric}_变化"
        if c_cur in merged.columns and c_prev in merged.columns:
            merged[c_chg] = merged.apply(
                lambda r: _fmt_change(r.get(c_cur), r.get(c_prev)), axis=1
            )
            merged[c_cur] = merged[c_cur].apply(_fmt_num)
            merged[c_prev] = merged[c_prev].apply(_fmt_num)
            display_cols += [c_cur, c_prev, c_chg]

    display_df = merged[display_cols].copy()
    rename_map = {}
    for c in display_cols:
        if c.endswith(f"_{semester}"):
            rename_map[c] = f"{c[:-len(semester)-1]}({semester})"
        elif c.endswith(f"_{previous_semester}"):
            rename_map[c] = f"{c[:-len(previous_semester)-1]}({previous_semester})"
        elif c.endswith("_变化"):
            rename_map[c] = f"{c[:-3]}变化"
    display_df = display_df.rename(columns=rename_map)

    print(f"\n  班级并排对比 ({previous_semester} → {semester}):")
    print_table(display_df)

    return merged


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

    status = compute_detailed_status(df)
    print_detailed_status_block(status)

    level_distribution, level_pcts, score_stats = compute_level_stats(df)
    print_level_block(level_distribution, level_pcts, score_stats)

    class_stats = pd.DataFrame()
    if not class_name and "class_name" in df.columns and not df.empty:
        class_stats = calculate_class_stats(df)
        if not class_stats.empty:
            print(f"\n  班级均分对比:")
            print_table(class_stats)

    retest_list, retest_summary = generate_retest_list(df)
    retest_count = len(retest_list) if not retest_list.empty else 0
    project_stats = compute_retest_project_stats(df)
    print_retest_summary(retest_summary)
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
        "total_students": status["total"],
        "fully_passed": status["fully_passed"],
        "partially_missing": status["partially_missing"],
        "fully_absent": status["fully_absent"],
        "single_fail": status["single_fail"],
        "pass_rate": round(status["fully_passed"] / status["total"] * 100, 1) if status["total"] > 0 else 0,
        "per_project_missing": status["per_project_missing"],
        "per_project_fail": status["per_project_fail"],
        "level_distribution": level_distribution,
        "level_pcts": level_pcts,
        "score_stats": score_stats,
        "retest_count": retest_count,
        "retest_project_stats": project_stats,
        "retest_summary": retest_summary,
    }

    class_compare_df = None
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

            prev_status = compute_detailed_status(prev_df)
            prev_level_dist, prev_level_pcts, prev_score_stats = compute_level_stats(prev_df)
            prev_retest_list, _ = generate_retest_list(prev_df)
            prev_retest_count = len(prev_retest_list) if not prev_retest_list.empty else 0

            summary["previous_semester"] = previous_semester
            summary["comparison"] = {
                "total_students": {"当前": status["total"], "上学期": prev_status["total"]},
                "fully_passed": {"当前": status["fully_passed"], "上学期": prev_status["fully_passed"]},
                "partially_missing": {"当前": status["partially_missing"], "上学期": prev_status["partially_missing"]},
                "fully_absent": {"当前": status["fully_absent"], "上学期": prev_status["fully_absent"]},
                "single_fail": {"当前": status["single_fail"], "上学期": prev_status["single_fail"]},
                "avg_score": {"当前": score_stats.get("avg_score", 0), "上学期": prev_score_stats.get("avg_score", 0)},
                "pass_rate": {"当前": score_stats.get("pass_rate", 0), "上学期": prev_score_stats.get("pass_rate", 0)},
                "excellent_rate": {"当前": score_stats.get("excellent_rate", 0), "上学期": prev_score_stats.get("excellent_rate", 0)},
                "retest_count": {"当前": retest_count, "上学期": prev_retest_count},
            }

            print_semester_comparison(
                summary,
                {"semester": previous_semester},
                status,
                prev_status,
                score_stats,
                prev_score_stats,
                retest_count,
                prev_retest_count,
            )

            class_compare_df = print_class_semester_comparison(df, prev_df, semester, previous_semester)

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

        status_df = pd.DataFrame([
            {"指标": "总人数", "人数": status["total"]},
            {"指标": "已完成（全部达标）", "人数": status["fully_passed"]},
            {"指标": "部分缺项", "人数": status["partially_missing"]},
            {"指标": "完全缺考", "人数": status["fully_absent"]},
            {"指标": "单项不及格", "人数": status["single_fail"]},
        ])
        status_file = output_path / f"体测状态统计_{suffix}.{output_format}"
        save_dataframe(status_df, status_file)
        print(f"✓ 体测状态已导出: {status_file}")

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
            names_cn = {
                "total_students": "总人数",
                "fully_passed": "已完成（全部达标）",
                "partially_missing": "部分缺项",
                "fully_absent": "完全缺考",
                "single_fail": "单项不及格",
                "avg_score": "平均分",
                "pass_rate": "及格率(%)",
                "excellent_rate": "优秀率(%)",
                "retest_count": "待补测人数",
            }
            for key, cn in names_cn.items():
                item = comp.get(key, {})
                cur = item.get("当前")
                prev = item.get("上学期")
                comp_rows.append({
                    "指标": cn,
                    f"{semester}": _fmt_num(cur),
                    f"{previous_semester}": _fmt_num(prev),
                    "变化": _fmt_change(cur, prev),
                })
            comp_df = pd.DataFrame(comp_rows)
            comp_file = output_path / f"学期对比_{suffix}.{output_format}"
            save_dataframe(comp_df, comp_file)
            print(f"✓ 学期对比已导出: {comp_file}")

            if class_compare_df is not None and not class_compare_df.empty:
                cc_file = output_path / f"班级并排对比_{suffix}.{output_format}"
                save_dataframe(class_compare_df, cc_file)
                print(f"✓ 班级并排对比已导出: {cc_file}")

            retest_sum_cur = retest_summary_to_df(summary.get("retest_summary", {}))
            _, prev_retest_sum = generate_retest_list(prev_df) if not prev_df.empty else (pd.DataFrame(), {})
            retest_sum_prev = retest_summary_to_df(prev_retest_sum)
            retest_change_rows = []
            for i, row in retest_sum_cur.iterrows():
                cat = row["分类"]
                cur_cnt = row["人数"]
                prev_cnt = retest_sum_prev[retest_sum_prev["分类"] == cat]["人数"].values[0] if cat in retest_sum_prev["分类"].values else 0
                retest_change_rows.append({
                    "分类": cat,
                    f"{semester}": _fmt_num(cur_cnt),
                    f"{previous_semester}": _fmt_num(prev_cnt),
                    "变化": _fmt_change(cur_cnt, prev_cnt),
                })
            retest_change_df = pd.DataFrame(retest_change_rows)
            rc_file = output_path / f"待补测变化_{suffix}.{output_format}"
            save_dataframe(retest_change_df, rc_file)
            print(f"✓ 待补测变化已导出: {rc_file}")

            cur_level_rows = []
            for k in ["优秀", "良好", "及格", "不及格"]:
                cur_cnt = level_distribution.get(k, 0)
                cur_pct = level_pcts.get(k, 0)
                prev_cnt = prev_level_dist.get(k, 0)
                prev_pct = prev_level_pcts.get(k, 0)
                cur_level_rows.append({
                    "等级": k,
                    f"{semester}_人数": cur_cnt,
                    f"{semester}_占比(%)": cur_pct,
                    f"{previous_semester}_人数": prev_cnt,
                    f"{previous_semester}_占比(%)": prev_pct,
                    "人数变化": _fmt_change(cur_cnt, prev_cnt),
                    "占比变化(%)": _fmt_change(cur_pct, prev_pct),
                })
            level_change_df = pd.DataFrame(cur_level_rows)
            lc_file = output_path / f"等级变化_{suffix}.{output_format}"
            save_dataframe(level_change_df, lc_file)
            print(f"✓ 等级变化已导出: {lc_file}")

            if output_format == "xlsx":
                sheets = [
                    ("年级总览", comp_df),
                    ("班级并排", class_compare_df if class_compare_df is not None else pd.DataFrame()),
                    ("待补测变化", retest_change_df),
                    ("等级变化", level_change_df),
                ]
                wb_file = output_path / f"学期对比工作簿_{suffix}.xlsx"
                save_workbook(sheets, wb_file)
                print(f"✓ 学期对比总工作簿已导出: {wb_file}")

    return {
        "summary": summary,
        "class_stats": class_stats,
        "retest_list": retest_list,
        "class_compare": class_compare_df,
    }
