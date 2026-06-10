"""体测评分标准模块

包含各年级、各性别的体测项目评分标准数据。
评分等级：优秀(90-100)、良好(80-89)、及格(60-79)、不及格(<60)
"""

from typing import Dict, List, Tuple, Optional

GRADES = ["初一", "初二", "初三", "高一", "高二", "高三"]
GENDERS = ["男", "女"]

PROJECTS = [
    "bmi",
    "vital_capacity",
    "run_50m",
    "standing_jump",
    "sit_and_reach",
    "pull_up",
    "sit_up",
    "run_1000m",
    "run_800m",
]

PROJECT_NAMES = {
    "bmi": "身高体重指数(BMI)",
    "vital_capacity": "肺活量",
    "run_50m": "50米跑",
    "standing_jump": "立定跳远",
    "sit_and_reach": "坐位体前屈",
    "pull_up": "引体向上(男)",
    "sit_up": "仰卧起坐(女)",
    "run_1000m": "1000米跑(男)",
    "run_800m": "800米跑(女)",
}

PROJECT_UNITS = {
    "bmi": "kg/m²",
    "vital_capacity": "ml",
    "run_50m": "s",
    "standing_jump": "cm",
    "sit_and_reach": "cm",
    "pull_up": "次",
    "sit_up": "次/分钟",
    "run_1000m": "s",
    "run_800m": "s",
}

GRADE_LEVEL_MAP = {
    "初一": 7,
    "初二": 8,
    "初三": 9,
    "高一": 10,
    "高二": 11,
    "高三": 12,
}


def get_grade_level(grade: str) -> int:
    return GRADE_LEVEL_MAP.get(grade, 0)


def get_required_projects(gender: str) -> List[str]:
    if gender == "男":
        return ["bmi", "vital_capacity", "run_50m", "standing_jump", "sit_and_reach", "pull_up", "run_1000m"]
    elif gender == "女":
        return ["bmi", "vital_capacity", "run_50m", "standing_jump", "sit_and_reach", "sit_up", "run_800m"]
    return []


BMI_RANGES = {
    "男": {
        7: [(15.5, 21.3), (21.4, 23.1), (23.2, 25.2), (0, float('inf'))],
        8: [(15.7, 21.8), (21.9, 23.8), (23.9, 25.8), (0, float('inf'))],
        9: [(15.9, 22.3), (22.4, 24.3), (24.4, 26.3), (0, float('inf'))],
        10: [(16.3, 22.9), (23.0, 24.9), (25.0, 27.0), (0, float('inf'))],
        11: [(16.5, 23.3), (23.4, 25.3), (25.4, 27.4), (0, float('inf'))],
        12: [(16.7, 23.7), (23.8, 25.7), (25.8, 27.8), (0, float('inf'))],
    },
    "女": {
        7: [(14.7, 20.5), (20.6, 22.3), (22.4, 24.3), (0, float('inf'))],
        8: [(14.9, 20.9), (21.0, 22.9), (23.0, 24.9), (0, float('inf'))],
        9: [(15.1, 21.3), (21.4, 23.3), (23.4, 25.3), (0, float('inf'))],
        10: [(15.4, 21.8), (21.9, 23.8), (23.9, 25.8), (0, float('inf'))],
        11: [(15.6, 22.2), (22.3, 24.2), (24.3, 26.2), (0, float('inf'))],
        12: [(15.8, 22.6), (22.7, 24.6), (24.7, 26.6), (0, float('inf'))],
    },
}


def _interpolate_score(value: float, thresholds: List[Tuple[float, int]], higher_is_better: bool = True) -> int:
    if higher_is_better:
        for threshold, score in thresholds:
            if value >= threshold:
                return score
    else:
        for threshold, score in thresholds:
            if value <= threshold:
                return score
    return thresholds[-1][1]


def score_bmi(bmi: float, gender: str, grade_level: int) -> int:
    gender_data = BMI_RANGES.get(gender, {})
    ranges = gender_data.get(grade_level, [(0, float('inf')), (0, 0), (0, 0), (0, 0)])
    
    normal_low, normal_high = ranges[0]
    if normal_low <= bmi <= normal_high:
        return 100
    elif ranges[1][0] <= bmi <= ranges[1][1]:
        return 80
    elif ranges[2][0] <= bmi <= ranges[2][1]:
        return 60
    else:
        return 50


def score_vital_capacity(value: int, gender: str, grade_level: int) -> int:
    thresholds = {
        "男": {
            7: [(4200, 100), (3800, 90), (3400, 80), (3000, 70), (2600, 60), (2000, 50), (0, 30)],
            8: [(4500, 100), (4100, 90), (3700, 80), (3300, 70), (2900, 60), (2300, 50), (0, 30)],
            9: [(4800, 100), (4400, 90), (4000, 80), (3600, 70), (3200, 60), (2600, 50), (0, 30)],
            10: [(5100, 100), (4700, 90), (4300, 80), (3900, 70), (3500, 60), (2900, 50), (0, 30)],
            11: [(5300, 100), (4900, 90), (4500, 80), (4100, 70), (3700, 60), (3100, 50), (0, 30)],
            12: [(5500, 100), (5100, 90), (4700, 80), (4300, 70), (3900, 60), (3300, 50), (0, 30)],
        },
        "女": {
            7: [(3000, 100), (2700, 90), (2400, 80), (2100, 70), (1800, 60), (1400, 50), (0, 30)],
            8: [(3200, 100), (2900, 90), (2600, 80), (2300, 70), (2000, 60), (1600, 50), (0, 30)],
            9: [(3400, 100), (3100, 90), (2800, 80), (2500, 70), (2200, 60), (1800, 50), (0, 30)],
            10: [(3600, 100), (3300, 90), (3000, 80), (2700, 70), (2400, 60), (2000, 50), (0, 30)],
            11: [(3700, 100), (3400, 90), (3100, 80), (2800, 70), (2500, 60), (2100, 50), (0, 30)],
            12: [(3800, 100), (3500, 90), (3200, 80), (2900, 70), (2600, 60), (2200, 50), (0, 30)],
        },
    }
    return _interpolate_score(value, thresholds[gender][grade_level], higher_is_better=True)


def score_run_50m(value: float, gender: str, grade_level: int) -> int:
    thresholds = {
        "男": {
            7: [(7.3, 100), (7.6, 90), (7.9, 80), (8.4, 70), (9.1, 60), (10.1, 50), (float('inf'), 30)],
            8: [(7.1, 100), (7.4, 90), (7.7, 80), (8.2, 70), (8.9, 60), (9.9, 50), (float('inf'), 30)],
            9: [(6.9, 100), (7.2, 90), (7.5, 80), (8.0, 70), (8.7, 60), (9.7, 50), (float('inf'), 30)],
            10: [(6.8, 100), (7.1, 90), (7.4, 80), (7.9, 70), (8.6, 60), (9.6, 50), (float('inf'), 30)],
            11: [(6.7, 100), (7.0, 90), (7.3, 80), (7.8, 70), (8.5, 60), (9.5, 50), (float('inf'), 30)],
            12: [(6.6, 100), (6.9, 90), (7.2, 80), (7.7, 70), (8.4, 60), (9.4, 50), (float('inf'), 30)],
        },
        "女": {
            7: [(7.9, 100), (8.2, 90), (8.5, 80), (9.0, 70), (9.7, 60), (10.7, 50), (float('inf'), 30)],
            8: [(7.7, 100), (8.0, 90), (8.3, 80), (8.8, 70), (9.5, 60), (10.5, 50), (float('inf'), 30)],
            9: [(7.5, 100), (7.8, 90), (8.1, 80), (8.6, 70), (9.3, 60), (10.3, 50), (float('inf'), 30)],
            10: [(7.4, 100), (7.7, 90), (8.0, 80), (8.5, 70), (9.2, 60), (10.2, 50), (float('inf'), 30)],
            11: [(7.3, 100), (7.6, 90), (7.9, 80), (8.4, 70), (9.1, 60), (10.1, 50), (float('inf'), 30)],
            12: [(7.2, 100), (7.5, 90), (7.8, 80), (8.3, 70), (9.0, 60), (10.0, 50), (float('inf'), 30)],
        },
    }
    return _interpolate_score(value, thresholds[gender][grade_level], higher_is_better=False)


def score_standing_jump(value: int, gender: str, grade_level: int) -> int:
    thresholds = {
        "男": {
            7: [(225, 100), (210, 90), (195, 80), (175, 70), (155, 60), (130, 50), (0, 30)],
            8: [(240, 100), (225, 90), (210, 80), (190, 70), (170, 60), (145, 50), (0, 30)],
            9: [(250, 100), (235, 90), (220, 80), (200, 70), (180, 60), (155, 50), (0, 30)],
            10: [(258, 100), (243, 90), (228, 80), (208, 70), (188, 60), (163, 50), (0, 30)],
            11: [(263, 100), (248, 90), (233, 80), (213, 70), (193, 60), (168, 50), (0, 30)],
            12: [(268, 100), (253, 90), (238, 80), (218, 70), (198, 60), (173, 50), (0, 30)],
        },
        "女": {
            7: [(186, 100), (174, 90), (162, 80), (146, 70), (130, 60), (110, 50), (0, 30)],
            8: [(196, 100), (184, 90), (172, 80), (156, 70), (140, 60), (120, 50), (0, 30)],
            9: [(202, 100), (190, 90), (178, 80), (162, 70), (146, 60), (126, 50), (0, 30)],
            10: [(206, 100), (194, 90), (182, 80), (166, 70), (150, 60), (130, 50), (0, 30)],
            11: [(208, 100), (196, 90), (184, 80), (168, 70), (152, 60), (132, 50), (0, 30)],
            12: [(210, 100), (198, 90), (186, 80), (170, 70), (154, 60), (134, 50), (0, 30)],
        },
    }
    return _interpolate_score(value, thresholds[gender][grade_level], higher_is_better=True)


def score_sit_and_reach(value: float, gender: str, grade_level: int) -> int:
    thresholds = {
        "男": {
            7: [(16, 100), (13, 90), (10, 80), (5, 70), (0, 60), (-5, 50), (float('-inf'), 30)],
            8: [(17, 100), (14, 90), (11, 80), (6, 70), (1, 60), (-4, 50), (float('-inf'), 30)],
            9: [(18, 100), (15, 90), (12, 80), (7, 70), (2, 60), (-3, 50), (float('-inf'), 30)],
            10: [(19, 100), (16, 90), (13, 80), (8, 70), (3, 60), (-2, 50), (float('-inf'), 30)],
            11: [(20, 100), (17, 90), (14, 80), (9, 70), (4, 60), (-1, 50), (float('-inf'), 30)],
            12: [(21, 100), (18, 90), (15, 80), (10, 70), (5, 60), (0, 50), (float('-inf'), 30)],
        },
        "女": {
            7: [(19, 100), (16, 90), (13, 80), (8, 70), (3, 60), (-2, 50), (float('-inf'), 30)],
            8: [(20, 100), (17, 90), (14, 80), (9, 70), (4, 60), (-1, 50), (float('-inf'), 30)],
            9: [(21, 100), (18, 90), (15, 80), (10, 70), (5, 60), (0, 50), (float('-inf'), 30)],
            10: [(22, 100), (19, 90), (16, 80), (11, 70), (6, 60), (1, 50), (float('-inf'), 30)],
            11: [(23, 100), (20, 90), (17, 80), (12, 70), (7, 60), (2, 50), (float('-inf'), 30)],
            12: [(24, 100), (21, 90), (18, 80), (13, 70), (8, 60), (3, 50), (float('-inf'), 30)],
        },
    }
    return _interpolate_score(value, thresholds[gender][grade_level], higher_is_better=True)


def score_pull_up(value: int, grade_level: int) -> int:
    thresholds = {
        7: [(15, 100), (12, 90), (9, 80), (6, 70), (3, 60), (1, 50), (0, 30)],
        8: [(16, 100), (13, 90), (10, 80), (7, 70), (4, 60), (2, 50), (0, 30)],
        9: [(17, 100), (14, 90), (11, 80), (8, 70), (5, 60), (3, 50), (0, 30)],
        10: [(18, 100), (15, 90), (12, 80), (9, 70), (6, 60), (4, 50), (0, 30)],
        11: [(19, 100), (16, 90), (13, 80), (10, 70), (7, 60), (5, 50), (0, 30)],
        12: [(20, 100), (17, 90), (14, 80), (11, 70), (8, 60), (6, 50), (0, 30)],
    }
    return _interpolate_score(value, thresholds[grade_level], higher_is_better=True)


def score_sit_up(value: int, grade_level: int) -> int:
    thresholds = {
        7: [(50, 100), (45, 90), (40, 80), (34, 70), (28, 60), (20, 50), (0, 30)],
        8: [(52, 100), (47, 90), (42, 80), (36, 70), (30, 60), (22, 50), (0, 30)],
        9: [(54, 100), (49, 90), (44, 80), (38, 70), (32, 60), (24, 50), (0, 30)],
        10: [(55, 100), (50, 90), (45, 80), (39, 70), (33, 60), (25, 50), (0, 30)],
        11: [(56, 100), (51, 90), (46, 80), (40, 70), (34, 60), (26, 50), (0, 30)],
        12: [(57, 100), (52, 90), (47, 80), (41, 70), (35, 60), (27, 50), (0, 30)],
    }
    return _interpolate_score(value, thresholds[grade_level], higher_is_better=True)


def score_run_1000m(value: int, grade_level: int) -> int:
    thresholds = {
        7: [(230, 100), (245, 90), (260, 80), (280, 70), (305, 60), (335, 50), (float('inf'), 30)],
        8: [(225, 100), (240, 90), (255, 80), (275, 70), (300, 60), (330, 50), (float('inf'), 30)],
        9: [(220, 100), (235, 90), (250, 80), (270, 70), (295, 60), (325, 50), (float('inf'), 30)],
        10: [(215, 100), (230, 90), (245, 80), (265, 70), (290, 60), (320, 50), (float('inf'), 30)],
        11: [(212, 100), (227, 90), (242, 80), (262, 70), (287, 60), (317, 50), (float('inf'), 30)],
        12: [(210, 100), (225, 90), (240, 80), (260, 70), (285, 60), (315, 50), (float('inf'), 30)],
    }
    return _interpolate_score(value, thresholds[grade_level], higher_is_better=False)


def score_run_800m(value: int, grade_level: int) -> int:
    thresholds = {
        7: [(210, 100), (225, 90), (240, 80), (260, 70), (285, 60), (315, 50), (float('inf'), 30)],
        8: [(205, 100), (220, 90), (235, 80), (255, 70), (280, 60), (310, 50), (float('inf'), 30)],
        9: [(200, 100), (215, 90), (230, 80), (250, 70), (275, 60), (305, 50), (float('inf'), 30)],
        10: [(198, 100), (213, 90), (228, 80), (248, 70), (273, 60), (303, 50), (float('inf'), 30)],
        11: [(196, 100), (211, 90), (226, 80), (246, 70), (271, 60), (301, 50), (float('inf'), 30)],
        12: [(194, 100), (209, 90), (224, 80), (244, 70), (269, 60), (299, 50), (float('inf'), 30)],
    }
    return _interpolate_score(value, thresholds[grade_level], higher_is_better=False)


def get_score_level(score: float) -> str:
    if score >= 90:
        return "优秀"
    elif score >= 80:
        return "良好"
    elif score >= 60:
        return "及格"
    else:
        return "不及格"


def calculate_project_score(project: str, value, gender: str, grade: str) -> Optional[int]:
    if value is None or (isinstance(value, float) and (value != value)):
        return None
    
    grade_level = get_grade_level(grade)
    if grade_level == 0:
        return None
    
    try:
        if project == "bmi":
            return score_bmi(float(value), gender, grade_level)
        elif project == "vital_capacity":
            return score_vital_capacity(int(float(value)), gender, grade_level)
        elif project == "run_50m":
            return score_run_50m(float(value), gender, grade_level)
        elif project == "standing_jump":
            return score_standing_jump(int(float(value)), gender, grade_level)
        elif project == "sit_and_reach":
            return score_sit_and_reach(float(value), gender, grade_level)
        elif project == "pull_up":
            if gender == "男":
                return score_pull_up(int(float(value)), grade_level)
            return None
        elif project == "sit_up":
            if gender == "女":
                return score_sit_up(int(float(value)), grade_level)
            return None
        elif project == "run_1000m":
            if gender == "男":
                return score_run_1000m(int(float(value)), grade_level)
            return None
        elif project == "run_800m":
            if gender == "女":
                return score_run_800m(int(float(value)), grade_level)
            return None
    except (ValueError, TypeError):
        return None
    
    return None
