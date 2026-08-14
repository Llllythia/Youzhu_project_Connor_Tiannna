"""合并爬取结果和手动检索结果，生成标准格式用于GitHub提交"""
import json
import pandas as pd
from pathlib import Path
from datetime import datetime

def merge_results():
    """合并自动爬取和手动检索的结果"""

    # 1. 读取爬取结果
    df_crawled = pd.read_excel("城市更新政策抓取结果2.xlsx", sheet_name="政策记录")

    # 2. 读取手动结果（如果存在）
    manual_file = Path("手动检索结果.json")
    manual_records = []
    if manual_file.exists():
        with open(manual_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            manual_records = data.get("记录", [])

    # 3. 转换手动记录为DataFrame格式
    if manual_records:
        df_manual = pd.DataFrame(manual_records)
        # 添加来源标记
        df_manual["数据来源"] = "手动"
        df_crawled["数据来源"] = "自动"
    else:
        df_crawled["数据来源"] = "自动"
        df_manual = pd.DataFrame()

    # 4. 合并
    if not df_manual.empty:
        df_combined = pd.concat([df_crawled, df_manual], ignore_index=True)
    else:
        df_combined = df_crawled

    # 5. 标准化字段
    standard_columns = ["信源ID", "信源名称", "层级", "标题", "记录URL", "日期", "发文号", "数据来源"]
    for col in standard_columns:
        if col not in df_combined.columns:
            df_combined[col] = ""

    df_combined = df_combined[standard_columns]

    # 6. 去除重复（按URL去重）
    df_combined = df_combined.drop_duplicates(subset=["记录URL"], keep="first")

    return df_combined

def generate_summary(df):
    """生成统计摘要"""
    total = len(df)
    by_source = df.groupby("信源ID").size().to_dict()
    by_level = df.groupby("层级").size().to_dict()
    has_date = df["日期"].notna() & (df["日期"] != "")
    date_rate = has_date.sum() / total * 100 if total > 0 else 0

    summary = {
        "生成时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "总记录数": total,
        "自动爬取": len(df[df["数据来源"] == "自动"]),
        "手动补充": len(df[df["数据来源"] == "手动"]),
        "日期填充率": f"{date_rate:.1f}%",
        "按层级分布": by_level,
        "按信源分布": by_level
    }
    return summary

def export_for_github(df, summary, output_dir="github_upload"):
    """导出GitHub提交所需的文件"""
    Path(output_dir).mkdir(exist_ok=True)

    # 1. 导出政策记录CSV
    df.to_csv(f"{output_dir}/政策记录.csv", index=False, encoding="utf-8-sig")

    # 2. 导出统计摘要
    with open(f"{output_dir}/统计摘要.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    # 3. 导出失败信源清单
    df_failed = pd.read_excel("城市更新政策抓取结果2.xlsx", sheet_name="信源状态")
    df_failed = df_failed[df_failed["连通性"] == "不可达"]
    df_failed.to_csv(f"{output_dir}/失败信源.csv", index=False, encoding="utf-8-sig")

    print(f"已导出到 {output_dir}/ 目录:")
    print(f"  - 政策记录.csv ({len(df)} 条)")
    print(f"  - 统计摘要.json")
    print(f"  - 失败信源.csv")

    return output_dir

def main():
    print("=" * 50)
    print("合并爬取结果和手动检索结果")
    print("=" * 50)

    # 合并
    df = merge_results()
    print(f"\n合并后总记录数: {len(df)}")

    # 生成摘要
    summary = generate_summary(df)
    print("\n统计摘要:")
    for k, v in summary.items():
        print(f"  {k}: {v}")

    # 导出
    export_dir = export_for_github(df, summary)
    print(f"\n导出完成: {export_dir}")

if __name__ == "__main__":
    main()
