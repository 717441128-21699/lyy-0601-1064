#!/usr/bin/env python3
"""生成示例数据的脚本"""

import random
import pandas as pd

random.seed(42)

def generate_sample_data():
    data = []
    
    classes = ["1班", "2班", "3班"]
    genders = ["男", "女"]
    
    student_id = 2024001
    for cls in classes:
        for i in range(15):
            gender = random.choice(genders)
            name = f"学生{student_id % 1000:03d}"
            
            row = {
                "学号": f"C{student_id}",
                "姓名": name,
                "性别": gender,
                "班级": cls,
                "年级": "初一",
                "身高": round(random.uniform(150, 180), 1),
                "体重": round(random.uniform(40, 80), 1),
                "肺活量": random.randint(2000, 4500),
                "50米跑": round(random.uniform(7.0, 11.0), 1),
                "立定跳远": random.randint(140, 240),
                "坐位体前屈": round(random.uniform(-5, 20), 1),
            }
            
            if gender == "男":
                row["引体向上"] = random.randint(0, 15)
                row["1000米跑"] = f"{random.randint(3, 5)}'{random.randint(0, 59):02d}\""
            else:
                row["仰卧起坐"] = random.randint(20, 55)
                row["800米跑"] = f"{random.randint(3, 4)}'{random.randint(0, 59):02d}\""
            
            data.append(row)
            student_id += 1
    
    data[5]["肺活量"] = None
    data[10]["50米跑"] = None
    data[15]["坐位体前屈"] = 999
    
    data[20]["学号"] = data[0]["学号"]
    
    df = pd.DataFrame(data)
    return df


if __name__ == "__main__":
    df = generate_sample_data()
    df.to_csv("examples/sample_students.csv", index=False, encoding="utf-8-sig")
    df.to_excel("examples/sample_students.xlsx", index=False)
    print(f"已生成 {len(df)} 条示例数据")
    print("  - examples/sample_students.csv")
    print("  - examples/sample_students.xlsx")
