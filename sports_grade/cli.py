"""命令行接口模块

提供 import、validate、score、rank、export、report、fix 7个命令。
"""

import argparse
import sys
from typing import Optional, List

from .standards import GRADES, PROJECTS, PROJECT_NAMES


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--semester", "-s",
        type=str,
        required=True,
        help="学期，例如：2024-2025-1",
    )
    parser.add_argument(
        "--grade", "-g",
        type=str,
        choices=GRADES,
        default=None,
        help="年级，可选值：初一、初二、初三、高一、高二、高三。不指定则处理所有年级。",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="只预览不写入文件",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sports-grade",
        description="智慧体育体测成绩管理工具 - 供学校体育老师批量整理学生成绩",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 导入学生成绩数据（宽表格式）
  sports-grade import -i students.xlsx -s 2024-2025-1 -g 初一

  # 导入多个文件（自动检测宽表/分项目表并合并）
  sports-grade import -i bmi.csv run50m.csv -s 2024-2025-1 -g 初一

  # 导入自定义列名并保存为模板
  sports-grade import -i students.xlsx -s 2024-2025-1 -g 初一 \\
    --map 短跑=run_50m 肺活=vital_capacity 班级名称=class_name --save-map 初一模板

  # 列出/使用映射模板
  sports-grade import --list-maps
  sports-grade import -i students.xlsx -s 2024-2025-1 -g 初一 --use-map 初一模板

  # 校验数据质量
  sports-grade validate -s 2024-2025-1 -g 初一

  # 计算评分
  sports-grade score -s 2024-2025-1 -g 初一

  # 生成排名（含进步榜，与上学期对比）
  sports-grade rank -s 2024-2025-1 -g 初一 --previous 2023-2024-2

  # 导出Excel（仅预览）
  sports-grade export -s 2024-2025-1 -g 初一 -o ./output --preview

  # 导出总工作簿（多sheet同一Excel）
  sports-grade export -s 2024-2025-1 -g 初一 -o ./output --workbook

  # 按班级和等级筛选导出
  sports-grade export -s 2024-2025-1 -g 初一 -o ./output --class 1班 --level 优秀

  # 生成体测概览报表（终端预览）
  sports-grade report -s 2024-2025-1 -g 初一

  # 生成体测概览（按班级+性别筛选，导出到目录）
  sports-grade report -s 2024-2025-1 -g 初一 --class 1班 --gender 男 -o ./output

  # 生成学期对比报表
  sports-grade report -s 2024-2025-1 -g 初一 --previous 2023-2024-2 -o ./output

  # 修正数据：补录肺活量成绩
  sports-grade fix -s 2024-2025-1 -g 初一 --id C2024006 --project vital_capacity --value 3200

  # 修正数据：修改班级
  sports-grade fix -s 2024-2025-1 -g 初一 --id C2024006 --class 2班 --note "转班"

  # 查看修正记录
  sports-grade fix -s 2024-2025-1 -g 初一 --log
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    import_parser = subparsers.add_parser(
        "import",
        help="导入学生名单和成绩数据（支持宽表/分项目表、自定义列名映射模板）",
    )
    import_parser.add_argument(
        "--semester", "-s",
        type=str,
        default=None,
        help="学期，例如：2024-2025-1",
    )
    import_parser.add_argument(
        "--grade", "-g",
        type=str,
        choices=GRADES,
        default=None,
        help="年级，可选值：初一、初二、初三、高一、高二、高三。不指定则处理所有年级。",
    )
    import_parser.add_argument(
        "--preview",
        action="store_true",
        help="只预览不写入文件",
    )
    import_parser.add_argument(
        "--input", "-i",
        type=str,
        nargs="+",
        default=None,
        help="输入文件路径（可指定多个），支持 .xlsx、.xls、.csv、.json",
    )
    import_parser.add_argument(
        "--map", "-m",
        type=str,
        nargs="+",
        default=None,
        help="自定义列名映射，格式: 原列名=标准列名，可指定多个。标准列名示例: student_id, name, gender, class_name, vital_capacity, run_50m 等",
    )
    import_parser.add_argument(
        "--use-map",
        type=str,
        default=None,
        help="使用已保存的列名映射模板",
    )
    import_parser.add_argument(
        "--save-map",
        type=str,
        default=None,
        help="将本次使用的列名映射保存为模板，供后续复用",
    )
    import_parser.add_argument(
        "--list-maps",
        action="store_true",
        help="列出所有已保存的列名映射模板",
    )

    validate_parser = subparsers.add_parser("validate", help="校验数据质量")
    add_common_args(validate_parser)

    score_parser = subparsers.add_parser("score", help="计算单项分、总分、等级和班级平均分")
    add_common_args(score_parser)

    rank_parser = subparsers.add_parser("rank", help="生成排名和各类名单")
    add_common_args(rank_parser)
    rank_parser.add_argument(
        "--previous", "-p",
        type=str,
        default=None,
        help="上学期名称，用于生成进步榜，例如：2023-2024-2",
    )

    export_parser = subparsers.add_parser(
        "export",
        help="导出数据（支持筛选，所有表按同一批学生收口；支持总工作簿模式）",
    )
    add_common_args(export_parser)
    export_parser.add_argument(
        "--output", "-o",
        type=str,
        default="./output",
        help="输出目录，默认：./output",
    )
    export_parser.add_argument(
        "--format", "-f",
        type=str,
        choices=["xlsx", "csv", "json"],
        default="xlsx",
        help="输出格式，默认：xlsx",
    )
    export_parser.add_argument(
        "--class", "-c",
        type=str,
        default=None,
        dest="class_name",
        help="按班级筛选，例如：1班",
    )
    export_parser.add_argument(
        "--level", "-l",
        type=str,
        choices=["优秀", "良好", "及格", "不及格"],
        default=None,
        help="按等级筛选",
    )
    export_parser.add_argument(
        "--project", "-j",
        type=str,
        choices=PROJECTS,
        default=None,
        help=f"按项目筛选，可选值：{', '.join(PROJECTS)}",
    )
    export_parser.add_argument(
        "--workbook", "-w",
        action="store_true",
        help="总工作簿模式：所有表放在同一个 Excel 文件的不同 sheet 中",
    )

    report_parser = subparsers.add_parser(
        "report",
        help="生成体测概览报表（支持筛选和学期对比）",
    )
    add_common_args(report_parser)
    report_parser.add_argument(
        "--output", "-o",
        type=str,
        default=None,
        help="输出目录（不指定则仅终端预览）",
    )
    report_parser.add_argument(
        "--format", "-f",
        type=str,
        choices=["xlsx", "csv", "json"],
        default="xlsx",
        help="输出格式，默认：xlsx",
    )
    report_parser.add_argument(
        "--class", "-c",
        type=str,
        default=None,
        dest="class_name",
        help="按班级筛选",
    )
    report_parser.add_argument(
        "--gender",
        type=str,
        choices=["男", "女"],
        default=None,
        help="按性别筛选",
    )
    report_parser.add_argument(
        "--only-retest",
        action="store_true",
        help="仅看待补测学生的概览",
    )
    report_parser.add_argument(
        "--previous", "-p",
        type=str,
        default=None,
        help="对比上学期，生成学期对比视角",
    )

    fix_parser = subparsers.add_parser(
        "fix",
        help="修正数据（补录成绩/修改信息，自动重新评分，保留操作记录）",
    )
    add_common_args(fix_parser)
    fix_parser.add_argument(
        "--id",
        type=str,
        default=None,
        dest="student_id",
        help="要修改的学生学号",
    )
    fix_parser.add_argument(
        "--project", "-j",
        type=str,
        choices=PROJECTS,
        default=None,
        help="要补录/修改的项目",
    )
    fix_parser.add_argument(
        "--value", "-v",
        type=str,
        default=None,
        help="项目成绩值（时间格式如 3'28\" 或 3:28，数值直接输入）",
    )
    fix_parser.add_argument(
        "--class",
        type=str,
        default=None,
        dest="fix_class",
        help="修改班级",
    )
    fix_parser.add_argument(
        "--gender",
        type=str,
        choices=["男", "女"],
        default=None,
        dest="fix_gender",
        help="修改性别",
    )
    fix_parser.add_argument(
        "--note", "-n",
        type=str,
        default=None,
        help="修正备注，会记录在操作日志中",
    )
    fix_parser.add_argument(
        "--log",
        action="store_true",
        help="查看修正操作记录",
    )
    fix_parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="操作记录显示条数，默认 20",
    )

    return parser


def main(argv: Optional[list] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 1

    try:
        if args.command == "import":
            from .importer import import_data, parse_map_arg

            custom_mapping = parse_map_arg(args.map) if args.map else None

            if args.list_maps:
                from .utils import list_map_templates
                templates = list_map_templates()
                if not templates:
                    print("暂无已保存的列名映射模板")
                else:
                    print(f"已保存的列名映射模板（共 {len(templates)} 个）:")
                    for t in templates:
                        print(f"  - {t}")
                return 0

            if not args.semester:
                parser.error("import 命令需要 --semester/-s 参数")
            if not args.input:
                parser.error("import 命令需要 --input/-i 参数")

            import_data(
                input_files=args.input,
                semester=args.semester,
                grade=args.grade,
                custom_mapping=custom_mapping,
                map_template=args.use_map,
                save_map_as=args.save_map,
                preview=args.preview,
            )

        elif args.command == "validate":
            from .validator import validate_data
            validate_data(
                semester=args.semester,
                grade=args.grade,
                preview=args.preview,
            )

        elif args.command == "score":
            from .scorer import score_data
            score_data(
                semester=args.semester,
                grade=args.grade,
                preview=args.preview,
            )

        elif args.command == "rank":
            from .ranker import rank_data
            rank_data(
                semester=args.semester,
                grade=args.grade,
                previous_semester=args.previous,
                preview=args.preview,
            )

        elif args.command == "export":
            from .exporter import export_data
            export_data(
                semester=args.semester,
                grade=args.grade,
                output_dir=args.output,
                output_format=args.format,
                class_name=args.class_name,
                level=args.level,
                project=args.project,
                workbook=args.workbook,
                preview=args.preview,
            )

        elif args.command == "report":
            from .reporter import generate_report
            generate_report(
                semester=args.semester,
                grade=args.grade,
                class_name=args.class_name,
                gender=args.gender,
                only_retest=args.only_retest,
                previous_semester=args.previous,
                output_dir=args.output,
                output_format=args.format,
                preview=args.preview,
            )

        elif args.command == "fix":
            from .fixer import fix_record, show_fix_log
            if args.log:
                show_fix_log(
                    semester=args.semester,
                    grade=args.grade,
                    limit=args.limit,
                )
            else:
                fix_record(
                    semester=args.semester,
                    grade=args.grade,
                    student_id=args.student_id,
                    project=args.project,
                    value=args.value,
                    class_name=args.fix_class,
                    gender=args.fix_gender,
                    note=args.note,
                    preview=args.preview,
                )

        else:
            parser.print_help()
            return 1

    except FileNotFoundError as e:
        print(f"错误: {e}", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"参数错误: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"执行出错: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
