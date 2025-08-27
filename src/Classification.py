import pandas as pd
import requests
import time
import os
import re
import markdown
from bs4 import BeautifulSoup
import shutil
from datetime import datetime
import warnings
import json
import sys

# 添加当前目录到路径，以便导入app模块
sys.path.append(os.path.dirname(__file__))

# 忽略 pandas 的 SettingWithCopyWarning 警告
warnings.filterwarnings('ignore', category=pd.errors.SettingWithCopyWarning)

# --- 1. 配置参数 ---

# 导入共享配置函数
try:
    from app import get_default_ollama_config
except ImportError:
    # 如果无法导入，定义本地默认配置作为备用
    def get_default_ollama_config():
        return {
            'ollama_url': 'http://localhost:11434',
            'model_id': 'qwen3:8b',
            'temperature': 0.3,
            'timeout': 80,
            'max_retries': 3,
            'max_summary_length': 600,
            'num_ctx': 5120,
            'min_text_length': 150,
        }

def load_ollama_config():
    """加载Ollama配置"""
    config_path = os.path.join(os.path.dirname(__file__), 'config', 'ollama_config.json')
    default_config = get_default_ollama_config()
    
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            # 合并默认配置，确保所有字段都存在
            for key, value in default_config.items():
                if key not in config:
                    config[key] = value
            return config
        except Exception as e:
            print(f"加载配置文件失败: {e}，使用默认配置")
            return default_config.copy()
    else:
        print("配置文件不存在，使用默认配置")
        return default_config.copy()

def load_prompt_config():
    """加载系统提示词配置"""
    config_path = os.path.join(os.path.dirname(__file__), 'config', 'prompt_config.json')
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                return config
        except Exception as e:
            print(f"加载提示词配置文件失败: {e}，使用默认配置")
    return None

def generate_system_prompt_from_config(config):
    """根据配置生成系统提示词"""
    if not config:
        return DEFAULT_SYSTEM_PROMPT
    
    # 构建系统提示词
    prompt_parts = []
    
    # 角色定义
    if config.get('role_definition'):
        prompt_parts.append(config['role_definition'])
    
    # 无关判定规则
    if config.get('irrelevant_rules'):
        prompt_parts.append("【无关判定规则】（从前往后依次判定，满足任一条即输出\"无关\"）：")
        for i, rule in enumerate(config['irrelevant_rules'], 1):
            prompt_parts.append(f"{i}.{rule} → 无关")
    
    # 分类标准
    if config.get('categories'):
        prompt_parts.append("【分类标准】（仅当通过无关检测全部通过后执行，否则不允许执行分类）：")
        for category in config['categories']:
            name = category.get('name', '')
            description = category.get('description', '')
            if name and description:
                prompt_parts.append(f"{name}：{description}")
    
    # 输出要求
    category_names = [cat.get('name', '') for cat in config.get('categories', []) if cat.get('name')]
    if category_names:
        prompt_parts.append("【输出要求】：")
        prompt_parts.append("-必须严格按优先级判定\"无关\"，你需要仔细阅读全文，理解文字表达的主旨，而不是仅依靠片面字眼进行判断")
        categories_str = '/'.join(category_names + ['无关'])
        prompt_parts.append(f"-仅输出以下{len(category_names)+1}种之一（不加任何解释）： {categories_str}")
    
    # 参考例子
    if config.get('examples'):
        prompt_parts.append("【参考例子】")
        for example in config['examples']:
            category = example.get('category', '')
            content = example.get('content', '')
            if category and content:
                prompt_parts.append(f"{category}：{content}")
    
    prompt_parts.append("/no_think")
    
    return '\n'.join(prompt_parts)

def update_categories_from_config(config):
    """根据配置更新分类映射"""
    global VALID_CATEGORIES, FOLDER_CATEGORIES
    
    if not config or not config.get('categories'):
        return
    
    # 从配置中提取分类名称
    category_names = [cat.get('name', '') for cat in config['categories'] if cat.get('name')]
    
    if category_names:
        # 更新有效分类（包括"无关"）
        VALID_CATEGORIES = category_names + ["无关"]
        # 更新文件夹分类（不包括"无关"）
        FOLDER_CATEGORIES = category_names
        print(f"分类映射已更新: {VALID_CATEGORIES}")

def reload_config():
    """重新加载配置并更新全局变量"""
    global OLLAMA_URL, MODEL_ID, TEMPERATURE, TIMEOUT, MAX_RETRIES, MAX_SUMMARY_LENGTH, NUM_CTX, MIN_TEXT_LENGTH, SYSTEM_PROMPT
    
    # 加载Ollama配置
    ollama_config = load_ollama_config()
    OLLAMA_URL = ollama_config['ollama_url'] + '/api/chat'
    MODEL_ID = ollama_config['model_id']
    TEMPERATURE = ollama_config['temperature']
    TIMEOUT = ollama_config['timeout']
    MAX_RETRIES = ollama_config['max_retries']
    MAX_SUMMARY_LENGTH = ollama_config['max_summary_length']
    NUM_CTX = ollama_config['num_ctx']
    MIN_TEXT_LENGTH = ollama_config['min_text_length']
    
    # 加载系统提示词配置
    prompt_config = load_prompt_config()
    if prompt_config:
        # 根据配置生成系统提示词
        SYSTEM_PROMPT = generate_system_prompt_from_config(prompt_config)
        # 更新分类映射
        update_categories_from_config(prompt_config)
        print(f"系统提示词配置已加载并应用")
    else:
        # 使用Ollama配置中的系统提示词或默认值
        SYSTEM_PROMPT = ollama_config.get('system_prompt', DEFAULT_SYSTEM_PROMPT)
        print(f"使用默认系统提示词配置")
    
    print(f"Ollama配置已重新加载: {ollama_config}")
    return ollama_config

# 加载配置
config = load_ollama_config()
OLLAMA_URL = config['ollama_url'] + '/api/chat'
MODEL_ID = config['model_id']
TEMPERATURE = config['temperature']
TIMEOUT = config['timeout']
MAX_RETRIES = config['max_retries']
MAX_SUMMARY_LENGTH = config['max_summary_length']
NUM_CTX = config['num_ctx']
MIN_TEXT_LENGTH = config['min_text_length']

# 路径配置 (!!! 请根据您的实际情况修改这里的路径 !!!)
OUTPUT_FOLDER = r"C:\Users\27549\OneDrive - whcqadc\桌面\test2"  # 新的分类结果输出文件夹
CHANGES_CSV_PATH = os.path.join(OUTPUT_FOLDER, "资料汇总.csv")  # 记录分类结果的CSV

# 分类目录映射 (用于创建文件夹)
# 注意: 这里我们直接使用模型的输出中文名作为文件夹名
VALID_CATEGORIES = ["合规风控类", "经营决策类", "运营操作类", "创新实践类", "无关"]
# 用于创建文件夹的分类（不包括"无关"）
FOLDER_CATEGORIES = ["合规风控类", "经营决策类", "运营操作类", "创新实践类"]

# 系统提示词 (与原脚本保持一致)
# 默认系统提示词
DEFAULT_SYSTEM_PROMPT = """
你是一名专注于线下快消品零售行业文章分类的专家，负责为大卖场/超市/便利店企业筛选和归类具有实操价值的案例或经营规范类内容，严格按照以下规则执行：
【无关判定规则】（从前往后依次判定，满足任一条即输出"无关"）：
1.文字主旨非线下快消品零售业强相关 → 无关
2.未包含具体企业实操案例/规范 → 无关
3.不属于大卖场/超市/便利店之一的零售企业 → 无关
4.存在：培训班/公示/广告/课程/会议/邀约/评奖/招聘/招募/推广/论坛/年会任一性质的内容→ 无关
5.涉及电商/直播等线上渠道 → 无关
6.所述是供应商/品牌方/餐饮业 → 无关
7.纯新闻/报道/数据/主观内容/时效信息 → 无关
8.含大量图片url链接 → 无关
【分类标准】（仅当通过无关检测全部通过后执行，否则不允许执行分类）：
合规风控类：风险事件处理/监管合规案例
经营决策类：战略调整/发展经营决策案例
运营操作类：标准化流程/执行细则
创新实践类：新技术应用/商业模式创新案例
【输出要求】：
-必须严格按优先级判定"无关"，你需要仔细阅读全文，理解文字表达的主旨，而不是仅依靠片面字眼进行判断
-仅输出以下5种之一（不加任何解释）： 合规风控类/经营决策类/运营操作类/创新实践类/无关
【参考例子】
创新实践类：上品商超智慧零售驱动新增长，焕发行业新活力
经营决策类：从做2B起家到靠2C逆袭，山姆在中国的生意经
运营操作类：胖东来运营考核标准
合规风控类：胖东来"红内裤事件"，一场信任危机下的企业合规警示录
/no_think
"""

# 初始化系统提示词
prompt_config = load_prompt_config()
if prompt_config:
    # 根据配置生成系统提示词
    SYSTEM_PROMPT = generate_system_prompt_from_config(prompt_config)
    # 更新分类映射
    update_categories_from_config(prompt_config)
else:
    # 使用配置文件中的系统提示词，如果没有则使用默认值
    SYSTEM_PROMPT = config.get('system_prompt', DEFAULT_SYSTEM_PROMPT)

# --- 2. 辅助函数 (部分复用原脚本) ---

def extract_title_from_filename(filename):
    """从文件名中提取标题，用于和Excel进行匹配"""
    # 移除.md后缀
    base_name = os.path.splitext(filename)[0]
    # 尝试匹配 [YYYY-MM-DD]标题 格式
    pattern = r'\[\d{4}-\d{2}-\d{2}\](.*)'
    match = re.match(pattern, base_name)
    if match:
        return match.group(1).strip()
    # 如果不匹配，则返回整个文件名（无后缀）
    return base_name.strip()

def normalize_string_for_matching(text):
    """清理字符串，移除所有非字母和数字的字符，并转为小写，用于模糊匹配"""
    if not isinstance(text, str):
        return ""
    # 移除非字母、非数字、非中文字符
    return re.sub(r'[^\w\u4e00-\u9fa5]', '', text).lower()

def extract_text_from_markdown(md_file):
    """从markdown文件中提取纯文本"""
    with open(md_file, 'r', encoding='utf-8') as f:
        md_content = f.read()
    html = markdown.markdown(md_content)
    soup = BeautifulSoup(html, 'html.parser')
    return soup.get_text(separator=' ', strip=True)

def create_summary(text, max_length=MAX_SUMMARY_LENGTH):
    """创建文章摘要"""
    return text[:max_length]

def clean_response(content):
    """清洗响应内容"""
    cleaned = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
    # 确保响应是有效的分类
    if cleaned not in VALID_CATEGORIES:
        return "无关"  # 如果模型输出意外内容，默认为"无关"
    return cleaned

def query_ollama_with_retry(prompt):
    """带重试机制的Ollama查询"""
    user_prompt = f"{prompt} /no think"
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt}
    ]
    payload = {
        "model": MODEL_ID, "messages": messages, "stream": False,
        "options": {"temperature": TEMPERATURE, "num_ctx": NUM_CTX}
    }

    for attempt in range(MAX_RETRIES):
        try:
            response = requests.post(OLLAMA_URL, json=payload, timeout=TIMEOUT)
            response.raise_for_status()
            content = response.json()["message"]["content"]
            return clean_response(content)
        except requests.exceptions.RequestException as e:
            if attempt == MAX_RETRIES - 1:
                return f"[错误] 请求失败: {str(e)}"
            time.sleep(2)
    return "[错误] 达到最大重试次数"


def initialize_classification(classification_folder=None, category_name=None):
    """
    初始化分类环境，创建输出文件夹（不包括"无关"文件夹）
    """
    # 使用传入的分类文件夹或默认文件夹
    current_output_folder = classification_folder if classification_folder else OUTPUT_FOLDER
    
    # 如果指定了大类名称，在分类文件夹下创建大类文件夹
    if category_name:
        current_output_folder = os.path.join(current_output_folder, category_name)
    
    os.makedirs(current_output_folder, exist_ok=True)
    for category in FOLDER_CATEGORIES:
        category_folder = os.path.join(current_output_folder, category)
        os.makedirs(category_folder, exist_ok=True)
    print(f"分类输出文件夹已初始化: {current_output_folder}")
    
    return current_output_folder

def classify_single_article(file_path, sequence_number, article_info=None, classification_folder=None, category_name=None):
    """
    对单篇文章进行分类
    返回分类记录字典，如果分类为无关则返回None
    """
    filename = os.path.basename(file_path)
    
    try:
        # 提取文本内容
        text_content = extract_text_from_markdown(file_path)
        if not text_content.strip():
            print(f"跳过空文件: {filename}")
            return None
        
        # 如果内容过短，直接归为"无关"
        if len(text_content) < MIN_TEXT_LENGTH:
            classification_result = "无关"
            print(f"⏩ 文件 '{filename}' 内容过短（{len(text_content)}字 < {MIN_TEXT_LENGTH}字），自动归为'无关'。")
        else:
            # 创建摘要
            summary = create_summary(text_content)
            # 调用大模型进行分类
            classification_result = query_ollama_with_retry(summary)
        
        if classification_result.startswith("[错误]"):
            print(f"❌ 文件 '{filename}' 处理失败: {classification_result}")
            return None
        
        # 如果分类为无关，返回None（不保存文件和记录）
        if classification_result == "无关":
            print(f"✅ 文件 '{filename}' -> 分类为: '{classification_result}'（将被删除）")
            return None
        
        # 检查目标分类目录是否已存在同名文件
        # 使用传入的分类文件夹或默认文件夹
        current_output_folder = classification_folder if classification_folder else OUTPUT_FOLDER
        
        # 如果指定了大类名称，在分类文件夹下创建大类文件夹
        if category_name:
            current_output_folder = os.path.join(current_output_folder, category_name)
        
        target_folder = os.path.join(current_output_folder, classification_result)
        target_path = os.path.join(target_folder, filename)
        
        if os.path.exists(target_path):
            print(f"⚠️ 文件 '{filename}' 在分类目录中已存在，跳过保存和记录")
            return None
        
        # 复制文件到新的分类目录
        shutil.copy2(file_path, target_path)
        
        # 创建分类记录
        file_title = extract_title_from_filename(filename)
        record = {
            "序号": sequence_number,
            "大类": category_name if category_name else "核心案例库",
            "小类": classification_result,
            "文档名称": file_title,
            "入库日期": datetime.now().strftime("%Y-%m-%d"),
            "来源": article_info.get("link", "") if article_info else "",
            "发布日期": ""
        }
        
        # 处理发布日期
        if article_info and article_info.get("create_time"):
            try:
                # 将时间戳转换为日期
                publish_date = datetime.fromtimestamp(article_info["create_time"]).strftime("%Y-%m-%d")
                record["发布日期"] = publish_date
            except:
                record["发布日期"] = ""
        
        print(f"✅ 文件 '{filename}' -> 分类为: '{classification_result}'")
        return record
        
    except Exception as e:
        print(f"🔥 处理文件 '{filename}' 时发生未知异常: {e}")
        return None

def save_classification_results(classification_records, output_folder=None, category_name=None):
    """
    保存分类结果到CSV文件
    """
    if classification_records:
        df_results = pd.DataFrame(classification_records)
        
        # 使用传入的输出文件夹或默认文件夹
        current_output_folder = output_folder if output_folder else OUTPUT_FOLDER
        
        # 如果指定了大类名称，在分类文件夹下创建大类文件夹
        if category_name:
            current_output_folder = os.path.join(current_output_folder, category_name)
        
        csv_path = os.path.join(current_output_folder, "资料汇总.csv")
        
        # 确保输出文件夹存在
        if not os.path.exists(current_output_folder):
            os.makedirs(current_output_folder)
        
        # 检查CSV文件是否存在，如果存在则追加，否则创建新文件
        if os.path.exists(csv_path):
            # 读取现有数据
            existing_df = pd.read_csv(csv_path, encoding='utf-8-sig')
            # 合并数据
            combined_df = pd.concat([existing_df, df_results], ignore_index=True)
            # 重新编号序号列
            combined_df['序号'] = range(1, len(combined_df) + 1)
            # 保存合并后的数据
            combined_df.to_csv(csv_path, index=False, encoding='utf-8-sig')
            print(f"成功！追加记录 {len(classification_records)} 条文档分类结果。")
        else:
            # 文件不存在，直接保存
            df_results.to_csv(csv_path, index=False, encoding='utf-8-sig')
            print(f"成功！新建记录 {len(classification_records)} 条文档分类结果。")
        
        print(f"分类结果已保存至: {csv_path}")
        
        # 显示分类统计
        print("\n本批次分类统计:")
        for category in VALID_CATEGORIES:
            category_count = len([r for r in classification_records if r.get('小类') == category])
            if category_count > 0:
                print(f"   - {category}: {category_count} 个文件")
    else:
        print("本次运行没有检测到任何可处理的文件。")

def classify_wechat_articles(articles, source_directory, account_nickname, classification_folder=None, category_name=None):
    """
    专门为微信文章分类设计的函数（保留原有功能）
    """
    print("--- 开始执行微信文章分类任务 ---")

    # 初始化分类环境
    actual_output_folder = initialize_classification(classification_folder, category_name)

    classification_records = []
    total_files_processed = 0
    
    # 获取源目录中的所有markdown文件
    if not os.path.isdir(source_directory):
        print(f"错误：源目录 '{source_directory}' 不存在。")
        return

    md_files = [f for f in os.listdir(source_directory) if f.endswith('.md')]
    if not md_files:
        print("源目录中没有找到Markdown文件。")
        return

    total_files = len(md_files)
    print(f"开始处理 {total_files} 个文件...")
    
    for index, filename in enumerate(md_files, 1):
        file_path = os.path.join(source_directory, filename)
        total_files_processed += 1
        
        progress_percent = (index / total_files) * 100
        print(f"[{index}/{total_files}] ({progress_percent:.1f}%) 正在处理: {filename}")
        
        # 查找对应的文章信息
        article_info = None
        file_title = extract_title_from_filename(filename)
        
        for article in articles:
            if article.get("title") and normalize_string_for_matching(article["title"]) == normalize_string_for_matching(file_title):
                article_info = article
                break
        
        # 使用单篇文章分类函数
        record = classify_single_article(file_path, index, article_info, classification_folder, category_name)
        if record:
            classification_records.append(record)
            print(f"✔️ 已记录文章信息。")

    # 保存分类结果
    print("\n正在保存分类结果...")
    save_classification_results(classification_records, actual_output_folder, category_name)

    print("\n--- 微信文章分类任务完成 ---")
    print(f"总共处理了 {total_files_processed} 个文件。")


# --- 3. 主逻辑 ---

def main():
    """主执行函数"""
    print("--- 开始执行文档重新分类任务 ---")
    print("注意：此功能需要配置EXCEL_FILE_PATH和SOURCE_SUBFOLDERS等参数")
    print("当前脚本主要用于微信文章分类，请使用classify_wechat_articles函数")


if __name__ == "__main__":
    main()