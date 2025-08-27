# WeChat文章下载器

一个智能的微信公众号文章下载和分类系统，支持批量下载公众号文章并使用本地大模型进行智能分类。

## 使用方法
- 本项目的微信公众号下载功能调用的是“wechat-article-exporter”项目的API，该项目包含完善的微信公众号文章下载功能，如果仅需批量下载公众号文章，可以直接前往：https://docs.wxdown.online/
- 如果需要批量分类下载功能，请使用本项目，您需要先前往以下网址注册一个“微信公众账号”：https://mp.weixin.qq.com/cgi-bin/registermidpage?action=index&lang=zh_CN
<img width="1859" height="973" alt="image" src="https://github.com/user-attachments/assets/abbef896-3a10-4567-99ee-7ef5cff4c4d4" />


## 功能特性

### 🔍 公众号搜索
- 支持关键词搜索微信公众号
- 显示公众号详细信息（头像、名称、FakeID等）
- 可视化选择目标公众号

### 📥 批量下载
- 批量下载公众号所有的历史文章
- 将下载的HTML文件转换为Markdown格式保存
- 实时显示下载进度和统计信息

### 🤖 智能分类
- 使用Ollama本地AI模型进行文章分类
- 支持自定义分类规则和提示词

### 🌐 Web界面
- 实时任务状态监控
- 配置管理（API Token、文件夹路径、AI模型等）
- 实时日志显示

## 技术架构

- **后端**: Flask + SocketIO 
- **前端**: HTML5 + CSS3 + JavaScript 
- **AI分类**: Ollama本地模型 
- **数据处理**: Pandas + BeautifulSoup
- **文件格式**: Markdown、CSV

## 环境要求

- Python 3.8+ (推荐 3.8-3.10)
- Ollama (用于AI分类功能)
- 微信文章下载API访问权限

## 安装和配置

### 1. 环境设置


```bash
# 创建conda环境 (推荐使用Python 3.8-3.10)
conda create -n wechat_downloader python=3.10 -y

# 激活环境
conda activate wechat_downloader

# 安装依赖
pip install -r requirements.txt
```


### 2. Ollama安装和配置

```bash
# 安装Ollama (访问 https://ollama.ai)
# 下载并安装适合的模型，例如：
ollama pull qwen3:8b
```

### 3. 配置文件

项目会自动创建配置文件：
- `src/config/app_config.json` - 基础配置（API Token、文件夹路径）
- `src/config/ollama_config.json` - AI模型配置
- `src/config/prompt_config.json` - 分类提示词配置

## 使用方法

### 启动服务

```bash
# 激活环境
conda activate wechat_downloader

# 启动Web服务
python src/app.py
```

访问 http://localhost:5000 打开Web界面

### 基本流程

1. **系统配置**
   - 配置API Token
   - 设置下载文件夹和分类结果文件夹
   - 配置Ollama模型参数
   - 自定义分类提示词

2. **搜索公众号**
   - 输入公众号名称进行搜索
   - 从搜索结果中选择目标公众号

3. **开始下载**
   - 点击"开始下载"按钮
   - 系统会批量下载文章并实时分类
   - 查看实时进度和日志

4. **查看结果**
   - 下载的文章保存在指定文件夹
   - 分类结果保存为CSV文件
   - 按分类创建对应文件夹

## 项目结构

```
Trae Project/
├── src/
│   ├── app.py              # Flask Web应用主程序
│   ├── WeChat.py           # 微信API接口和下载功能
│   ├── Classification.py   # AI分类功能
│   ├── Remove.py           # 文件清理工具
│   ├── config/             # 配置文件目录
│   │   ├── app_config.json
│   │   ├── ollama_config.json
│   │   └── prompt_config.json
│   └── templates/
│       └── index.html      # Web界面模板
├── docs/                   # 文档目录
├── requirements.txt        # 项目依赖
└── README.md              # 项目说明
```

## 分类规则

系统默认是对线下快消品零售行业（大卖场/超市/便利店）的文章进行分类：

- **合规风控类**: 风险事件处理、监管合规案例
- **经营决策类**: 战略调整、发展经营决策案例  
- **运营操作类**: 标准化流程、执行细则
- **创新实践类**: 新技术应用、商业模式创新案例
- **无关**: 不符合行业要求或无实操价值的内容

- 可以按照需求在前端自行修改提示词配置和Ollama模型配置



## 注意事项

1. **依赖版本兼容性**: 严格按照README中的安装步骤执行
2. **Python版本**: 推荐使用Python 3.8-3.10，避免使用过新或过旧的版本
3. **API权限**: 确保拥有合法的微信文章下载API访问权限
4. **Ollama服务**: 需要在本地运行Ollama服务（默认端口11434）
5. **网络环境**: 确保网络连接稳定，项目已配置禁用代理，避免触发限制导致下载失败
6. 分类结果仅供参考，建议人工审核和筛选
7. 本项目仅供学习和研究使用，不涉及任何商业用途

## 许可证

本项目仅供学习和研究使用，请遵守相关法律法规和平台使用条款。
