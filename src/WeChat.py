# -*- coding: utf-8 -*-

import requests
import os
import json
import time
import pandas as pd
from datetime import datetime
from urllib.parse import urlencode
import html2text # 导入新添加的HTML转Markdown库

# --- 配置区 ---

# API 的基础URL (已根据你提供的信息更新)
BASE_URL = "https://exporter.wxdown.online"
# 你的授权 token (已根据你提供的信息更新)
TOKEN = "fd010cbc-ae87-413d-bdb6-165d8c3a21ad"

# 请求头
HEADERS = {
    "Authorization": TOKEN,
    "Content-Type": "application/json"
}

# 禁用代理设置，解决网络连接问题
os.environ['NO_PROXY'] = '*'

# --- 函数定义区 ---

def search_accounts(keyword, token=None):
    """
    根据关键字搜索公众号。
    """
    print(f"正在搜索公众号: {keyword}...")
    api_url = f"{BASE_URL}/api/v1/account"
    params = {
        "keyword": keyword,
        "begin": 0,
        "size": 5
    }
    
    # 使用传入的token或默认token
    current_token = token if token else TOKEN
    headers = {
        "Authorization": current_token,
        "Content-Type": "application/json"
    }

    try:
        response = requests.get(api_url, headers=headers, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get("base_resp", {}).get("ret") == 0 and "list" in data:
                print(f"成功找到 {data.get('total', 0)} 个相关公众号。")
                return data["list"]
            else:
                print(f"API返回错误: {data.get('base_resp', {}).get('err_msg', '未知错误')}")
                return None
        else:
            print(f"请求失败! HTTP 状态码: {response.status_code}")
            print("--- 服务器返回的原始内容 ---\n" + response.text + "\n--------------------------")
            return None
    except json.JSONDecodeError:
        print("错误: 服务器返回的不是有效的JSON格式。")
        print(f"HTTP 状态码: {response.status_code}")
        print("--- 服务器返回的原始内容 ---\n" + response.text + "\n--------------------------")
        return None
    except requests.exceptions.RequestException as e:
        print(f"网络请求错误: {e}")
        return None


def download_and_classify_batch(articles, output_dir, batch_size=20, task_status=None, token=None, classification_folder=None, category_name=None):
    """
    批量下载文章并立即分类，每下载batch_size篇后暂停20秒
    对于分类为无关的文章，删除对应文档
    支持停止检查和实时进度更新
    """
    from Classification import initialize_classification, classify_single_article
    
    # 初始化分类环境
    initialize_classification(classification_folder, category_name)
    
    classification_records = []
    sequence_number = 1
    
    for i, article in enumerate(articles):
        # 检查是否需要停止
        if task_status and not task_status.get('running', True):
            print("\n检测到停止信号，终止下载任务")
            break
            
        print(f"\n正在下载第 {i+1}/{len(articles)} 篇文章...")
        
        # 下载文章
        file_path = download_article(article["link"], output_dir, article["title"], token)
        
        if file_path:  # 下载成功
            # 立即进行分类
            record = classify_single_article(file_path, sequence_number, article, classification_folder, category_name)
            
            if record:  # 分类成功且不是无关
                classification_records.append(record)
                sequence_number += 1
                print(f"文章已分类并保存: {article['title']}")
            else:  # 分类为无关，删除文档
                try:
                    os.remove(file_path)
                    print(f"已删除无关文档: {os.path.basename(file_path)}")
                except Exception as e:
                    print(f"删除文档失败: {e}")
        else:
            print(f"文章下载失败，跳过: {article['title']}")
        
        # 更新实时进度（如果提供了task_status）
        if task_status:
            # 更新当前批次的处理进度
            current_batch_processed = (i + 1)
            current_batch_total = len(articles)
            task_status['progress'] = int((current_batch_processed / current_batch_total) * 100)
            
            # 更新全局统计（用于统计面板显示）
            task_status['processed_articles'] = task_status.get('processed_articles', 0) + 1
        
        # 每下载batch_size篇后暂停
        if (i + 1) % batch_size == 0 and i + 1 < len(articles):
            print(f"已处理 {i+1} 篇文章，暂停20秒...")
            # 在暂停期间也检查停止信号
            for _ in range(20):
                if task_status and not task_status.get('running', True):
                    print("\n暂停期间检测到停止信号，终止下载任务")
                    return classification_records
                time.sleep(1)
    
    return classification_records


def download_articles_only(articles, output_dir, batch_size=20, task_status=None, token=None):
    """
    批量下载文章但不进行分类，每下载batch_size篇后暂停20秒
    支持停止检查和实时进度更新
    """
    for i, article in enumerate(articles):
        # 检查是否需要停止
        if task_status and not task_status.get('running', True):
            print("\n检测到停止信号，终止下载任务")
            break
            
        print(f"\n正在下载第 {i+1}/{len(articles)} 篇文章...")
        
        # 下载文章
        file_path = download_article(article["link"], output_dir, article["title"], token)
        
        if file_path:  # 下载成功
            print(f"文章已下载: {article['title']}")
        else:
            print(f"文章下载失败，跳过: {article['title']}")
        
        # 更新实时进度（如果提供了task_status）
        if task_status:
            # 更新当前批次的处理进度
            current_batch_processed = (i + 1)
            current_batch_total = len(articles)
            task_status['progress'] = int((current_batch_processed / current_batch_total) * 100)
            
            # 更新全局统计（用于统计面板显示）
            task_status['processed_articles'] = task_status.get('processed_articles', 0) + 1
        
        # 每下载batch_size篇后暂停
        if (i + 1) % batch_size == 0 and i + 1 < len(articles):
            print(f"已处理 {i+1} 篇文章，暂停20秒...")
            # 在暂停期间也检查停止信号
            for _ in range(20):
                if task_status and not task_status.get('running', True):
                    print("\n暂停期间检测到停止信号，终止下载任务")
                    return
                time.sleep(1)


def get_articles_with_begin(fakeid, begin=0, count=20, token=None):
    """
    获取指定公众号的文章列表，支持分页
    """
    print(f"正在获取 fakeid 为 {fakeid} 的公众号文章列表 (从第 {begin + 1} 篇开始，获取 {count} 篇)...")
    api_url = f"{BASE_URL}/api/v1/article"
    params = {
        "fakeid": fakeid,
        "begin": begin,
        "size": count
    }
    
    # 使用传入的token或默认token
    current_token = token if token else TOKEN
    headers = {
        "Authorization": current_token,
        "Content-Type": "application/json"
    }

    try:
        response = requests.get(api_url, headers=headers, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get("base_resp", {}).get("ret") == 0 and "articles" in data:
                print(f"成功获取到 {len(data['articles'])} 篇文章。")
                return data["articles"]
            else:
                print(f"获取文章列表失败: {data.get('base_resp', {}).get('err_msg', '未知错误')}")
                return None
        else:
            print(f"请求失败! HTTP 状态码: {response.status_code}")
            print("--- 服务器返回的原始内容 ---\n" + response.text + "\n--------------------------")
            return None
    except json.JSONDecodeError:
        print("错误: 服务器返回的不是有效的JSON格式。")
        print(f"HTTP 状态码: {response.status_code}")
        print("--- 服务器返回的原始内容 ---\n" + response.text + "\n--------------------------")
        return None
    except requests.exceptions.RequestException as e:
        print(f"网络请求错误: {e}")
        return None



def download_article(article_url, output_dir, article_title, token=None):
    """
    下载单篇文章，将其从HTML转换为Markdown并保存。
    返回保存的文件路径，如果失败返回None。
    """
    print(f"准备下载文章: {article_title}")
    api_url = f"{BASE_URL}/api/v1/download"
    params = {
        "url": article_url,
        "format": "markdown"
    }
    
    # 使用传入的token或默认token
    current_token = token if token else TOKEN
    headers = {
        "Authorization": current_token,
        "Content-Type": "application/json"
    }

    try:
        response = requests.get(api_url, headers=headers, params=params, timeout=20)
        if response.status_code == 200:
            safe_title = "".join(c for c in article_title if c not in r'\/:*?"<>|').strip()
            file_path = os.path.join(output_dir, f"{safe_title}.md")

            try:
                data = response.json()
                html_content = data.get("html", "")

                if html_content:
                    # --- 核心转换逻辑 ---
                    # 1. 创建一个转换器实例
                    h = html2text.HTML2Text()
                    # 2. 告诉转换器忽略图片和链接，可以根据需要调整
                    # h.ignore_links = True
                    # h.ignore_images = True
                    # 3. 执行转换
                    markdown_content = h.handle(html_content)
                    
                    # 4. 将转换后的Markdown内容写入文件
                    with open(file_path, "w", encoding="utf-8-sig") as f:
                        f.write(markdown_content)
                    print(f"文章已成功转换为Markdown并保存到: {file_path}")
                    return file_path
                else:
                    print(f"警告: 文章 '{article_title}' 的返回内容中不包含HTML，无法转换。")
                    return None

            except json.JSONDecodeError:
                print(f"警告: 文章 '{article_title}' 的返回内容不是预期的JSON格式。将直接保存原始文本。")
                with open(file_path, "w", encoding="utf-8-sig") as f:
                    f.write(response.text)
                return file_path
            except IOError as e:
                print(f"保存文件时发生IO错误: {e}")
                return None

        else:
            print(f"下载文章 '{article_title}' 失败! HTTP 状态码: {response.status_code}")
            print("--- 服务器返回的原始内容 ---\n" + response.text + "\n--------------------------")
            return None

    except requests.exceptions.RequestException as e:
        print(f"下载文章 '{article_title}' 时发生网络错误: {e}")
        return None


# --- 主逻辑区 ---

def main():
    """
    主函数：自动选择第一个公众号并批量下载所有文章，边下载边分类
    每20篇等待20秒，直到下载完所有文章
    """
    account_name = input("请输入公众号名称: ")
    
    # 搜索公众号
    accounts = search_accounts(account_name)
    if not accounts:
        print("未找到匹配的公众号")
        return
    
    # 自动选择第一个公众号
    selected_account = accounts[0]
    print(f"自动选择公众号: {selected_account['nickname']}")
    
    # 创建输出目录
    output_directory = selected_account["nickname"].strip()
    if not os.path.exists(output_directory):
        os.makedirs(output_directory)
        print(f"创建目录: {output_directory}")
    
    # 批量下载所有文章
    print("\n开始批量下载并分类文章...")
    all_classification_records = []
    begin = 0
    batch_size = 20
    
    while True:
        # 获取当前批次的文章列表
        articles = get_articles_with_begin(selected_account["fakeid"], begin, batch_size)
        if not articles:
            print(f"第 {begin//batch_size + 1} 批次未获取到文章，下载完成")
            break
        
        print(f"\n=== 第 {begin//batch_size + 1} 批次：获取到 {len(articles)} 篇文章 ===")
        
        # 下载并分类当前批次的文章
        classification_records = download_and_classify_batch(articles, output_directory, batch_size)
        all_classification_records.extend(classification_records)
        
        # 立即保存当前批次的分类结果
        if classification_records:
            from Classification import save_classification_results
            save_classification_results(classification_records)
            print(f"第 {begin//batch_size + 1} 批次：成功保存 {len(classification_records)} 篇相关文章到CSV")
        else:
            print(f"第 {begin//batch_size + 1} 批次：没有相关文章需要保存")
        
        # 如果获取的文章数少于batch_size，说明已经是最后一批
        if len(articles) < batch_size:
            print("已下载完所有文章")
            break
        
        # 准备下一批次
        begin += batch_size
        print(f"\n第 {begin//batch_size} 批次完成，等待20秒后继续...")
        time.sleep(20)
    
    print(f"\n所有批次处理完成！")
    print(f"总计成功分类并保存 {len(all_classification_records)} 篇相关文章")


def classify_articles(articles, source_directory, account_nickname, classification_folder=None, category_name=None):
    """
    对下载的文章进行分类
    """
    try:
        # 导入分类模块
        import sys
        sys.path.append(os.path.dirname(__file__))
        from Classification import classify_wechat_articles
        
        # 调用分类函数
        classify_wechat_articles(articles, source_directory, account_nickname, classification_folder, category_name)
        
    except ImportError as e:
        print(f"无法导入分类模块: {e}")
        print("请确保 Classification.py 文件存在且可用。")
    except Exception as e:
        print(f"分类过程中发生错误: {e}")


if __name__ == "__main__":
    main()
