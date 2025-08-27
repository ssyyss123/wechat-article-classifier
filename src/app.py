from flask import Flask, request, jsonify, render_template
from flask_socketio import SocketIO, emit
import threading
import queue
import time
import os
import sys
from datetime import datetime
import json

# 添加当前目录到Python路径
sys.path.append(os.path.dirname(__file__))

# 导入WeChat.py的功能
from WeChat import search_accounts, get_articles_with_begin, download_and_classify_batch
from Classification import save_classification_results

app = Flask(__name__)

# 默认配置函数
def get_default_prompt_config():
    """获取系统提示词默认配置"""
    return {
        'role_definition': '你是一名专注于线下快消品零售行业文章分类的专家，负责为大卖场/超市/便利店企业筛选和归类具有实操价值的案例或经营规范类内容，严格按照以下规则执行：',
        'irrelevant_rules': [
            "文字主旨非线下快消品零售业强相关",
            "未包含具体企业实操案例/规范",
            "不属于大卖场/超市/便利店之一的零售企业",
            "存在：培训班/公示/广告/课程/会议/邀约/评奖/招聘/招募/推广/论坛/年会任一性质的内容",
            "涉及电商/直播等线上渠道",
            "所述是供应商/品牌方/餐饮业",
            "纯新闻/报道/数据/主观内容/时效信息",
            "含大量图片url链接"
        ],
        'categories': [
            {'name': '合规风控类', 'desc': '风险事件处理/监管合规案例'},
            {'name': '经营决策类', 'desc': '战略规划/商业模式/市场分析'},
            {'name': '运营操作类', 'desc': '日常运营/流程优化/执行标准'},
            {'name': '创新实践类', 'desc': '新技术应用/创新服务/差异化实践'}
        ],
        'examples': [
            {
                "text": "胖东来\"红内裤\"事件，一场信任危机下的企业合规警示录",
                "category": "合规风控类"
            },
            {
                "text": "沃尔玛推出自助结账系统，提升顾客购物体验",
                "category": "创新实践类"
            },
            {
                "text": "胖东来运营考核标准",
                "category": "运营操作类"
            },
            {
                "text": "创业型便利店该怎样才能做出成绩",
                "category": "经营决策类"
            }
        ]
    }

def get_default_app_config():
    """获取应用基础默认配置"""
    return {
        'api_token': '',
        'output_folder': 'D:\\智能分类\\原文章',
        'classification_folder': 'D:\\智能分类',
        'category_name': '核心案例库',
        'enable_classification': True
    }

def get_default_ollama_config():
    """获取Ollama默认配置"""
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
app.config['SECRET_KEY'] = 'wechat_scraper_secret_key'
socketio = SocketIO(app, cors_allowed_origins="*")

# 全局变量
task_status = {
    'running': False,
    'progress': 0,
    'total_articles': 0,
    'processed_articles': 0,
    'current_batch': 0,
    'total_batches': 0,
    'classification_count': 0,
    'logs': [],
    'selected_account': None
}

# 日志队列
log_queue = queue.Queue()

# 当前下载线程引用
current_download_thread = None

class WebLogger:
    """自定义日志类，将print输出重定向到日志存储"""
    def __init__(self):
        self.terminal = sys.stdout
        
    def write(self, message):
        if message.strip():  # 忽略空行
            timestamp = datetime.now().strftime('%H:%M:%S')
            log_entry = f"[{timestamp}] {message.strip()}"
            task_status['logs'].append(log_entry)
            # 保留最近500条日志，避免内存过度占用
            if len(task_status['logs']) > 500:
                task_status['logs'] = task_status['logs'][-500:]
        # 同时输出到终端
        self.terminal.write(message)
        
    def flush(self):
        self.terminal.flush()

# 重定向print输出
web_logger = WebLogger()
sys.stdout = web_logger

@app.route('/')
def index():
    """主页面"""
    return render_template('index.html')

@app.route('/api/search', methods=['POST'])
def api_search_accounts():
    """搜索公众号API"""
    try:
        data = request.get_json()
        keyword = data.get('keyword', '').strip()
        token = data.get('token', '').strip()
        
        if not keyword:
            return jsonify({'success': False, 'error': '请输入公众号名称'})
        
        if not token:
            return jsonify({'success': False, 'error': '请输入API Token'})
        
        print(f"开始搜索公众号: {keyword}")
        print(f"使用Token: {token[:20]}...")
        accounts = search_accounts(keyword, token)
        
        if accounts:
            print(f"找到 {len(accounts)} 个匹配的公众号")
            return jsonify({
                'success': True, 
                'accounts': accounts
            })
        else:
            print("未找到匹配的公众号")
            return jsonify({
                'success': False, 
                'error': '未找到匹配的公众号'
            })
        
    except Exception as e:
        print(f"搜索公众号时发生错误: {str(e)}")
        return jsonify({
            'success': False, 
            'error': f'搜索失败: {str(e)}'
        })

@app.route('/api/start_download_only', methods=['POST'])
def api_start_download_only():
    """开始只下载不分类任务API"""
    try:
        if task_status['running']:
            return jsonify({
                'success': False, 
                'error': '已有任务正在运行中'
            })
        
        data = request.get_json()
        account = data.get('account')
        token = data.get('token')
        output_folder = data.get('output_folder')
        
        if not account:
            return jsonify({
                'success': False, 
                'error': '请选择公众号'
            })
            
        if not token:
            return jsonify({
                'success': False, 
                'error': '请提供API Token'
            })
            
        if not output_folder:
            return jsonify({
                'success': False, 
                'error': '请提供下载文件夹路径'
            })
        
        # 重置任务状态
        task_status.update({
            'running': True,
            'progress': 0,
            'total_articles': 0,
            'processed_articles': 0,
            'current_batch': 0,
            'total_batches': 0,
            'classification_count': 0,
            'logs': [],
            'selected_account': account
        })
        
        # 在后台线程中执行只下载任务
        global current_download_thread
        download_thread = threading.Thread(
            target=download_only_task_worker, 
            args=(account, token, output_folder)
        )
        download_thread.daemon = True
        current_download_thread = download_thread
        download_thread.start()
        
        return jsonify({
            'success': True, 
            'message': '下载任务已开始'
        })
        
    except Exception as e:
        task_status['running'] = False
        print(f"启动只下载任务时发生错误: {str(e)}")
        return jsonify({
            'success': False, 
            'error': f'启动失败: {str(e)}'
        })
            
    except Exception as e:
        print(f"搜索公众号时发生错误: {str(e)}")
        return jsonify({
            'success': False, 
            'error': f'搜索失败: {str(e)}'
        })

@app.route('/api/start_download', methods=['POST'])
def api_start_download():
    """开始下载任务API"""
    try:
        if task_status['running']:
            return jsonify({
                'success': False, 
                'error': '已有任务正在运行中'
            })
        
        data = request.get_json()
        account = data.get('account')
        token = data.get('token')
        output_folder = data.get('output_folder')
        classification_folder = data.get('classification_folder')
        category_name = data.get('category_name')
        
        if not account:
            return jsonify({
                'success': False, 
                'error': '请选择公众号'
            })
            
        if not token:
            return jsonify({
                'success': False, 
                'error': '请提供API Token'
            })
            
        if not output_folder:
            return jsonify({
                'success': False, 
                'error': '请提供下载文件夹路径'
            })
            
        if not classification_folder:
            return jsonify({
                'success': False, 
                'error': '请提供分类结果文件夹路径'
            })
        
        # 重置任务状态
        task_status.update({
            'running': True,
            'progress': 0,
            'total_articles': 0,
            'processed_articles': 0,
            'current_batch': 0,
            'total_batches': 0,
            'classification_count': 0,
            'logs': [],
            'selected_account': account
        })
        
        # 在后台线程中执行下载任务
        global current_download_thread
        download_thread = threading.Thread(
            target=download_task_worker, 
            args=(account, token, output_folder, classification_folder, category_name)
        )
        download_thread.daemon = True
        current_download_thread = download_thread
        download_thread.start()
        
        return jsonify({
            'success': True, 
            'message': '下载任务已开始'
        })
        
    except Exception as e:
        task_status['running'] = False
        print(f"启动下载任务时发生错误: {str(e)}")
        return jsonify({
            'success': False, 
            'error': f'启动失败: {str(e)}'
        })

@app.route('/api/stop_download', methods=['POST'])
def api_stop_download():
    """停止下载任务API"""
    global current_download_thread
    
    if not task_status['running']:
        return jsonify({
            'success': False, 
            'error': '当前没有运行中的任务'
        })
    
    task_status['running'] = False
    current_download_thread = None
    print("用户请求停止下载任务")
    
    return jsonify({
        'success': True, 
        'message': '停止信号已发送'
    })

@app.route('/api/ollama_config', methods=['POST'])
def api_save_ollama_config():
    """保存Ollama配置API"""
    try:
        data = request.get_json()
        
        # 验证必需的配置项
        required_fields = ['ollama_url', 'model_id', 'temperature', 'timeout', 
                          'max_retries', 'max_summary_length', 'num_ctx', 'min_text_length']
        
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'success': False, 
                    'error': f'缺少必需的配置项: {field}'
                })
        
        # 验证数值范围
        if not (0 <= data['temperature'] <= 2):
            return jsonify({
                'success': False, 
                'error': '温度参数必须在0.0-2.0之间'
            })
            
        if data['timeout'] < 1:
            return jsonify({
                'success': False, 
                'error': '超时时间必须大于0'
            })
            
        if data['max_retries'] < 0:
            return jsonify({
                'success': False, 
                'error': '最大重试次数不能小于0'
            })
            
        if data['max_summary_length'] < 100:
            return jsonify({
                'success': False, 
                'error': '最大摘要长度不能小于100'
            })
            
        if data['num_ctx'] < 512:
            return jsonify({
                'success': False, 
                'error': '上下文长度不能小于512'
            })
            
        if data['min_text_length'] < 0:
            return jsonify({
                'success': False, 
                'error': '最小字符阈值不能小于0'
            })
        
        # 保存配置到文件
        config_file = os.path.join(os.path.dirname(__file__), 'config', 'ollama_config.json')
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print(f"Ollama配置已保存: {config_file}")
        
        # 重新加载Classification模块的配置
        try:
            import Classification
            Classification.reload_config()
            print("Classification模块配置已更新")
        except Exception as e:
            print(f"更新Classification模块配置失败: {e}")
        
        return jsonify({
            'success': True, 
            'message': 'Ollama配置保存成功'
        })
        
    except Exception as e:
        print(f"保存Ollama配置时发生错误: {str(e)}")
        return jsonify({
            'success': False, 
            'error': f'保存失败: {str(e)}'
        })

@app.route('/api/ollama_config', methods=['GET'])
def api_get_ollama_config():
    """获取Ollama配置API"""
    try:
        config_file = os.path.join(os.path.dirname(__file__), 'config', 'ollama_config.json')
        
        # 获取默认配置
        default_config = get_default_ollama_config()
        
        if os.path.exists(config_file):
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            # 合并默认配置，确保所有字段都存在
            for key, value in default_config.items():
                if key not in config:
                    config[key] = value
        else:
            config = default_config
        
        return jsonify({
            'success': True, 
            'config': config
        })
        
    except Exception as e:
        print(f"获取Ollama配置时发生错误: {str(e)}")
        return jsonify({
            'success': False, 
            'error': f'获取配置失败: {str(e)}'
        })

@app.route('/api/prompt_config', methods=['POST'])
def api_save_prompt_config():
    """保存系统提示词配置API"""
    try:
        data = request.get_json()
        
        # 验证必需的配置项
        required_fields = ['role_definition', 'irrelevant_rules', 'categories']
        
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'success': False, 
                    'error': f'缺少必需的配置项: {field}'
                })
        
        # 验证数据格式
        if not isinstance(data['irrelevant_rules'], list) or len(data['irrelevant_rules']) == 0:
            return jsonify({
                'success': False, 
                'error': '无关判定规则必须是非空数组'
            })
            
        if not isinstance(data['categories'], list) or len(data['categories']) == 0:
            return jsonify({
                'success': False, 
                'error': '分类标准必须是非空数组'
            })
            
        # 验证分类标准格式
        for category in data['categories']:
            if not isinstance(category, dict) or 'name' not in category or 'desc' not in category:
                return jsonify({
                    'success': False, 
                    'error': '分类标准格式错误，必须包含name和desc字段'
                })
        
        # 验证参考例子格式（如果存在）
        if 'examples' in data and data['examples']:
            if not isinstance(data['examples'], list):
                return jsonify({
                    'success': False, 
                    'error': '参考例子必须是数组格式'
                })
            for example in data['examples']:
                if not isinstance(example, dict) or 'text' not in example or 'category' not in example:
                    return jsonify({
                        'success': False, 
                        'error': '参考例子格式错误，必须包含text和category字段'
                    })
        
        # 保存配置到文件
        config_file = os.path.join(os.path.dirname(__file__), 'config', 'prompt_config.json')
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print(f"系统提示词配置已保存: {config_file}")
        
        # 重新加载Classification模块的配置
        try:
            import Classification
            Classification.reload_config()
            print("Classification模块配置已更新")
        except Exception as e:
            print(f"更新Classification模块配置失败: {e}")
        
        return jsonify({
            'success': True, 
            'message': '系统提示词配置保存成功'
        })
        
    except Exception as e:
        print(f"保存系统提示词配置时发生错误: {str(e)}")
        return jsonify({
            'success': False, 
            'error': f'保存失败: {str(e)}'
        })

@app.route('/api/prompt_config', methods=['GET'])
def api_get_prompt_config():
    """获取系统提示词配置API"""
    try:
        config_file = os.path.join(os.path.dirname(__file__), 'config', 'prompt_config.json')
        
        # 获取默认配置
        default_config = get_default_prompt_config()
        
        if os.path.exists(config_file):
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            # 合并默认配置，确保所有字段都存在
            for key, value in default_config.items():
                if key not in config:
                    config[key] = value
        else:
            config = default_config
        
        # 生成系统提示词
        if 'system_prompt' not in config:
            config['system_prompt'] = generate_system_prompt_from_config(config)
        
        return jsonify({
            'success': True, 
            'config': config
        })
        
    except Exception as e:
        print(f"获取系统提示词配置时发生错误: {str(e)}")
        return jsonify({
            'success': False, 
            'error': f'获取配置失败: {str(e)}'
        })

def generate_system_prompt_from_config(config):
    """根据配置生成系统提示词"""
    prompt = config.get('role_definition', '你是一名专业的文章分类专家，负责对文章进行准确分类，严格按照以下规则执行：')
    prompt += '\n\n【无关判定规则】（从前往后依次判定，满足任一条即输出\"无关\"）：\n'
    
    rules = config.get('irrelevant_rules', [])
    if rules:
        for i, rule in enumerate(rules, 1):
            prompt += f'{i}.{rule} → 无关\n'
    else:
        prompt += '1.文字主旨非相关领域 → 无关\n'
    
    prompt += '\n【分类标准】（仅当通过无关检测全部通过后执行，否则不允许执行分类）：\n'
    categories = config.get('categories', [])
    if categories:
        for category in categories:
            prompt += f"{category['name']}：{category['desc']}\n"
    else:
        prompt += '通用分类：通用内容分类\n'
    
    prompt += '\n【输出要求】\n'
    prompt +='-必须严格按优先级判定\"无关\"，你需要仔细阅读全文，理解文字表达的主旨，而不是仅依靠片面字眼进行判断\n'
    prompt += '-仅输出以下'
    category_names = [cat['name'] for cat in categories] if categories else ['通用分类']
    prompt += f"{len(category_names) + 1}种之一（不加任何解释）： {'/'.join(category_names)}/无关\n"
    
    examples = config.get('examples', [])
    if examples:
        prompt += '\n【参考例子】\n'
        for example in examples:
            prompt += f'"{example["text"]}" → {example["category"]}\n'
    
    return prompt

@app.route('/api/generate_prompt', methods=['POST'])
def api_generate_prompt():
    """生成系统提示词API"""
    try:
        data = request.get_json()
        
        # 验证必需的配置项
        required_fields = ['role_definition', 'irrelevant_rules', 'categories']
        
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'success': False, 
                    'error': f'缺少必需的配置项: {field}'
                })
        
        # 生成系统提示词
        system_prompt = generate_system_prompt_from_config(data)
        
        return jsonify({
            'success': True,
            'system_prompt': system_prompt
        })
        
    except Exception as e:
        print(f"生成系统提示词时发生错误: {str(e)}")
        return jsonify({
            'success': False, 
            'error': f'生成失败: {str(e)}'
        })

@app.route('/api/app_config', methods=['POST'])
def api_save_app_config():
    """保存应用基础配置API"""
    try:
        data = request.get_json()
        
        # 验证必需的配置项
        required_fields = ['api_token', 'output_folder']
        
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({
                    'success': False, 
                    'error': f'缺少必需的配置项: {field}'
                })
        
        # 如果启用分类功能，则验证分类相关字段
        if data.get('enable_classification', True):
            classification_fields = ['classification_folder', 'category_name']
            for field in classification_fields:
                if field not in data or not data[field]:
                    return jsonify({
                        'success': False, 
                        'error': f'启用分类功能时缺少必需的配置项: {field}'
                    })
        
        # 保存配置到文件
        config_file = os.path.join(os.path.dirname(__file__), 'config', 'app_config.json')
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print(f"应用基础配置已保存: {config_file}")
        
        return jsonify({
            'success': True, 
            'message': '应用基础配置保存成功'
        })
        
    except Exception as e:
        print(f"保存应用基础配置时发生错误: {str(e)}")
        return jsonify({
            'success': False, 
            'error': f'保存失败: {str(e)}'
        })

@app.route('/api/app_config', methods=['GET'])
def api_get_app_config():
    """获取应用基础配置API"""
    try:
        config_file = os.path.join(os.path.dirname(__file__), 'config', 'app_config.json')
        
        # 获取默认配置
        default_config = get_default_app_config()
        
        if os.path.exists(config_file):
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
                # 合并默认配置，确保所有字段都存在
                for key, value in default_config.items():
                    if key not in config:
                        config[key] = value
                return jsonify({
                    'success': True,
                    'config': config
                })
        else:
            # 如果配置文件不存在，创建默认配置文件
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, ensure_ascii=False, indent=2)
            
            return jsonify({
                'success': True,
                'config': default_config
            })
            
    except Exception as e:
        print(f"获取应用基础配置时发生错误: {str(e)}")
        return jsonify({
            'success': False, 
            'error': f'获取配置失败: {str(e)}',
            'config': default_config
        })

@app.route('/api/app_config/default', methods=['GET'])
def api_get_default_app_config():
    """获取应用基础默认配置API"""
    try:
        # 获取默认配置
        default_config = get_default_app_config()
        
        return jsonify({
            'success': True,
            'config': default_config
        })
            
    except Exception as e:
        print(f"获取应用基础默认配置时发生错误: {str(e)}")
        return jsonify({
            'success': False, 
            'error': f'获取默认配置失败: {str(e)}',
            'config': default_config
        })

@app.route('/api/prompt_config/default', methods=['GET'])
def api_get_default_prompt_config():
    """获取系统提示词默认配置API"""
    try:
        # 获取默认配置
        default_config = get_default_prompt_config()
        
        return jsonify({
            'success': True,
            'config': default_config
        })
            
    except Exception as e:
        print(f"获取系统提示词默认配置时发生错误: {str(e)}")
        return jsonify({
            'success': False, 
            'error': f'获取默认配置失败: {str(e)}',
            'config': default_config
        })

@app.route('/api/status')
def api_get_status():
    """获取任务状态API"""
    return jsonify(task_status)

@app.route('/api/clear_logs', methods=['POST'])
def api_clear_logs():
    """清空日志API"""
    try:
        task_status['logs'] = []
        print("日志已清空")
        return jsonify({
            'success': True,
            'message': '日志已清空'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'清空日志失败: {str(e)}'
        })

def download_task_worker(account, token, output_folder, classification_folder, category_name=None):
    """下载任务工作线程"""
    try:
        print(f"开始处理公众号: {account['nickname']}")
        print(f"使用Token: {token[:20]}...")
        print(f"下载文件路径: {output_folder}")
        print(f"分类结果路径: {classification_folder}")
        
        # 创建输出目录
        output_directory = os.path.join(output_folder, account["nickname"].strip())
        if not os.path.exists(output_directory):
            os.makedirs(output_directory)
            print(f"创建目录: {output_directory}")
        
        # 批量下载所有文章
        print("\n开始批量下载并分类文章...")
        all_classification_records = []
        begin = 0
        batch_size = 20
        
        while task_status['running']:
            # 获取当前批次的文章列表
            articles = get_articles_with_begin(account["fakeid"], begin, batch_size, token)
            if not articles:
                print(f"第 {begin//batch_size + 1} 批次未获取到文章，下载完成")
                break
            
            # 更新状态
            task_status['current_batch'] = begin//batch_size + 1
            task_status['total_articles'] += len(articles)
            
            print(f"\n=== 第 {task_status['current_batch']} 批次：获取到 {len(articles)} 篇文章 ===")
            
            # 发送进度更新
            socketio.emit('progress_update', {
                'current_batch': task_status['current_batch'],
                'total_articles': task_status['total_articles'],
                'processed_articles': task_status['processed_articles']
            })
            
            # 下载并分类当前批次的文章（传递task_status以支持停止检查和实时进度更新）
            classification_records = download_and_classify_batch(articles, output_directory, batch_size, task_status, token, classification_folder, category_name)
            all_classification_records.extend(classification_records)
            
            # 更新分类计数
            task_status['classification_count'] += len(classification_records)
            
            # 如果任务被停止，退出循环
            if not task_status['running']:
                break
            
            # 立即保存当前批次的分类结果
            if classification_records:
                save_classification_results(classification_records, classification_folder, category_name)
                print(f"第 {task_status['current_batch']} 批次：成功保存 {len(classification_records)} 篇相关文章到CSV")
            else:
                print(f"第 {task_status['current_batch']} 批次：没有相关文章需要保存")
            
            # 发送统计更新
            socketio.emit('stats_update', {
                'total_articles': task_status['total_articles'],
                'processed_articles': task_status['processed_articles'],
                'classification_count': task_status['classification_count']
            })
            
            # 如果获取的文章数少于batch_size，说明已经是最后一批
            if len(articles) < batch_size:
                print("已下载完所有文章")
                break
            
            # 准备下一批次
            begin += batch_size
            if task_status['running']:
                print(f"\n第 {task_status['current_batch']} 批次完成，等待20秒后继续...")
                time.sleep(20)
        
        if task_status['running']:
            print(f"\n所有批次处理完成！")
            print(f"总计成功分类并保存 {len(all_classification_records)} 篇相关文章")
            socketio.emit('task_completed', {
                'total_classified': len(all_classification_records)
            })
        else:
            print("\n任务已被用户停止")
            socketio.emit('task_stopped', {})
            
    except Exception as e:
        print(f"下载任务执行过程中发生错误: {str(e)}")
        socketio.emit('task_error', {'error': str(e)})
    finally:
        global current_download_thread
        task_status['running'] = False
        current_download_thread = None

def download_only_task_worker(account, token, output_folder):
    """只下载不分类任务工作线程"""
    try:
        print(f"开始处理公众号: {account['nickname']}")
        print(f"使用Token: {token[:20]}...")
        print(f"下载文件路径: {output_folder}")
        
        # 创建输出目录
        output_directory = os.path.join(output_folder, account["nickname"].strip())
        if not os.path.exists(output_directory):
            os.makedirs(output_directory)
            print(f"创建目录: {output_directory}")
        
        # 批量下载所有文章
        print("\n开始批量下载文章...")
        begin = 0
        batch_size = 20
        
        while task_status['running']:
            # 获取当前批次的文章列表
            articles = get_articles_with_begin(account["fakeid"], begin, batch_size, token)
            if not articles:
                print(f"第 {begin//batch_size + 1} 批次未获取到文章，下载完成")
                break
            
            # 更新状态
            task_status['current_batch'] = begin//batch_size + 1
            task_status['total_articles'] += len(articles)
            
            print(f"\n=== 第 {task_status['current_batch']} 批次：获取到 {len(articles)} 篇文章 ===")
            
            # 发送进度更新
            socketio.emit('progress_update', {
                'current_batch': task_status['current_batch'],
                'total_articles': task_status['total_articles'],
                'processed_articles': task_status['processed_articles']
            })
            
            # 只下载当前批次的文章，不进行分类
            from WeChat import download_articles_only
            download_articles_only(articles, output_directory, batch_size, task_status, token)
            
            # 如果任务被停止，退出循环
            if not task_status['running']:
                break
            
            # 发送统计更新
            socketio.emit('stats_update', {
                'total_articles': task_status['total_articles'],
                'processed_articles': task_status['processed_articles'],
                'classification_count': 0  # 不分类时为0
            })
            
            # 如果获取的文章数少于batch_size，说明已经是最后一批
            if len(articles) < batch_size:
                print("已下载完所有文章")
                break
            
            # 准备下一批次
            begin += batch_size
            if task_status['running']:
                print(f"\n第 {task_status['current_batch']} 批次完成，等待20秒后继续...")
                time.sleep(20)
        
        if task_status['running']:
            print(f"\n所有批次处理完成！")
            print(f"总计成功下载 {task_status['total_articles']} 篇文章")
            socketio.emit('task_completed', {
                'total_classified': 0  # 不分类时为0
            })
        else:
            print("\n任务已被用户停止")
            socketio.emit('task_stopped', {})
            
    except Exception as e:
        print(f"只下载任务执行过程中发生错误: {str(e)}")
        socketio.emit('task_error', {'error': str(e)})
    finally:
        global current_download_thread
        task_status['running'] = False
        current_download_thread = None

@socketio.on('connect')
def handle_connect():
    print('客户端已连接')
    emit('connected', {'status': 'success'})

@socketio.on('disconnect')
def handle_disconnect():
    print('客户端已断开连接')

if __name__ == '__main__':
    # 创建templates目录
    templates_dir = os.path.join(os.path.dirname(__file__), 'templates')
    if not os.path.exists(templates_dir):
        os.makedirs(templates_dir)
    
    print("WeChat文章下载器Web版启动中...")
    print("访问地址: http://localhost:5000")
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)