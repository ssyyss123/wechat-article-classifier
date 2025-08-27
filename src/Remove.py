import os
import re
import pandas as pd

def deduplicate_files_and_clean_excel(base_folder, subfolders, excel_file):
    """
    主函数，用于执行文件去重和Excel记录清理。

    参数:
    base_folder (str): 包含子文件夹和Excel文件的根文件夹路径。
    subfolders (list): 需要处理的子文件夹名称列表。
    excel_file (str): Excel文件的名称。
    """
    
    print("--- 开始处理重复的Markdown文件 ---")
    all_deleted_files = []
    for folder in subfolders:
        folder_path = os.path.join(base_folder, folder)
        if not os.path.isdir(folder_path):
            print(f"警告：找不到文件夹 {folder_path}，已跳过。")
            continue

        print(f"\n正在处理文件夹: {folder}")
        
        files = os.listdir(folder_path)
        md_files = [f for f in files if f.endswith('.md')]
        
        # 使用正则表达式查找重复文件，例如 "文件名 (2).md"
        duplicate_pattern = re.compile(r'(.+?)\s*\(\d+\)\.md$')
        
        # 文件名字典，用于存储基本文件名和其所有版本
        file_versions = {}
        for md_file in md_files:
            match = duplicate_pattern.match(md_file)
            if match:
                base_name = match.group(1).strip()
                if base_name not in file_versions:
                    file_versions[base_name] = []
                file_versions[base_name].append(md_file)
            else:
                base_name = md_file.replace('.md', '').strip()
                if base_name not in file_versions:
                    file_versions[base_name] = []
                # 将原始文件也加入列表，便于后续处理
                file_versions[base_name].insert(0, md_file)

        # 删除重复文件
        deleted_files_in_folder = []
        for base_name, versions in file_versions.items():
            if len(versions) > 1:
                # 第一个文件是原始文件，保留它，删除后面的重复文件
                files_to_delete = versions[1:]
                for file_to_delete in files_to_delete:
                    try:
                        file_path_to_delete = os.path.join(folder_path, file_to_delete)
                        os.remove(file_path_to_delete)
                        print(f"  已删除文件: {file_to_delete}")
                        deleted_files_in_folder.append(file_to_delete)
                    except OSError as e:
                        print(f"  删除文件失败: {file_to_delete}，错误: {e}")
        
        all_deleted_files.extend(deleted_files_in_folder)

    print("\n--- Markdown文件去重处理完成 ---")

    print("\n--- 开始清理Excel文件中的记录 ---")
    clean_excel_records(base_folder, excel_file)
    print("--- Excel文件记录清理完成 ---")


def clean_excel_records(base_folder, excel_file):
    """
    清理Excel文件中的重复记录。

    参数:
    base_folder (str): Excel文件所在的文件夹路径。
    excel_file (str): Excel文件的名称。
    """
    excel_path = os.path.join(base_folder, excel_file)
    try:
        df = pd.read_excel(excel_path)
    except FileNotFoundError:
        print(f"错误：找不到Excel文件 {excel_path}。请确保文件名和路径正确。")
        return

    # 创建一个标准化的文档名称列，用于匹配
    # 逻辑是：移除末尾的.md（如果有），然后移除括号和其中的数字，最后去除首尾空格
    df['normalized_name'] = df['文档名称'].astype(str).apply(
        lambda x: re.sub(r'\s*\(\d+\)$', '', x.replace('.md', '')).strip()
    )

    # 将'入库日期'转换为datetime对象，方便排序
    df['入库日期'] = pd.to_datetime(df['入库日期'], errors='coerce')
    
    # 按'小类'和'normalized_name'分组，并保留每组中'入库日期'最早的一行
    # 这将同时处理文件名重复和内容重复（但文件名有细微差别）的情况
    df_cleaned = df.sort_values('入库日期').drop_duplicates(
        subset=['小类', 'normalized_name'],
        keep='first'
    )

    # 删除辅助列
    df_cleaned = df_cleaned.drop(columns=['normalized_name'])
    
    # 保存清理后的数据到新文件
    output_filename = os.path.join(base_folder, '资料汇总1_cleaned.xlsx')
    try:
        df_cleaned.to_excel(output_filename, index=False)
        print(f"\n清理完成！结果已保存到：{output_filename}")
        print(f"原始记录数: {len(df)}, 清理后记录数: {len(df_cleaned)}")
    except Exception as e:
        print(f"保存文件失败：{e}")


if __name__ == '__main__':
    # --- 请在这里配置您的文件夹路径 ---
    # 请将这里的路径替换为您"案例库"文件夹的实际路径
    base_folder = "C:\\Users\\27549\\OneDrive - whcqadc\\桌面\\knowledgeBase - 副本\\案例库"
    
    # 子文件夹列表
    subfolders = ["创新实践类", "合规风控类", "经营决策类", "运营操作类"]
    
    # Excel文件名
    excel_file = "资料汇总1.xlsx"
    
    # 运行主函数
    deduplicate_files_and_clean_excel(base_folder, subfolders, excel_file)