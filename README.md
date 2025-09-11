# w-sub

节点订阅汇总工具，用于合并多个节点源并筛选最优节点。

## 功能特性

- 从多个源自动获取节点配置
- 智能合并并去重节点
- 测试节点延迟，筛选出速度最快的节点
- 同时生成两个订阅文件：
  - 包含所有节点的订阅文件
  - 筛选出的速度最快的节点订阅文件
- 配置分离，方便修改节点源和参数
- 自动更新README.md显示最新节点状态

## 项目结构

## 使用方法

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 运行程序

```bash
python w-sub.py
```

### 3. 获取订阅

程序运行完成后，会在当前目录生成 `subscription.txt` 文件，该文件包含了经过Base64编码的节点订阅内容。

## 配置项

你可以在 `w-sub.py` 文件中修改以下配置：

- `SOURCES`: 节点源URL列表
- `MAX_NODES`: 保留的最大节点数（默认为100）
- `TIMEOUT`: 请求超时时间（秒）
- `OUTPUT_FILE`: 输出文件名

## 注意事项

- 请确保你的网络能够访问配置的节点源
- 如需增加节点测试功能，可以开启 `TEST_CONNECTIVITY` 选项（会增加执行时间）
- 节点评分基于多种因素，包括节点类型、关键词和长度等

## License

MIT


### 最新节点状态

更新时间: 2025-09-11 08:08:21

共测试 244 个节点，筛选出以下 100 个最优节点（按延迟由低到高排序）：

| 排名 | 节点类型 | 服务器地址 | 延迟(ms) |
|------|----------|------------|----------|
| 1 | vmess | 25.26.27.209 | 1.88 |
| 2 | vmess | 172.66.40.99 | 1.98 |
| 3 | vmess | 172.67.170.13 | 2.01 |
| 4 | vmess | 102.177.176.249 | 2.04 |
| 5 | vmess | elma.ns.cloudflare.com | 2.11 |
| 6 | vmess | elma.ns.cloudflare.com | 2.14 |
| 7 | vmess | 25.25.25.209 | 2.19 |
| 8 | vmess | 172.67.234.68 | 2.19 |
| 9 | vmess | 162.159.243.133 | 2.19 |
| 10 | vmess | 102.177.176.209 | 2.21 |
| 11 | vmess | 25.26.27.210 | 2.21 |
| 12 | vmess | 25.25.25.249 | 2.24 |
| 13 | vmess | npmjs.com | 2.25 |
| 14 | vmess | 162.159.243.133 | 2.27 |
| 15 | vmess | 102.132.188.249 | 2.37 |
| 16 | vmess | 185.146.173.25 | 2.38 |
| 17 | vmess | 104.21.0.11 | 2.39 |
| 18 | vmess | 104.16.0.0 | 2.41 |
| 19 | vmess | 185.146.173.25 | 2.42 |
| 20 | vmess | 102.177.176.210 | 2.45 |
| 21 | vmess | 185.146.173.25 | 2.45 |
| 22 | vmess | 25.26.27.249 | 2.46 |
| 23 | vmess | 185.146.173.25 | 2.51 |
| 24 | vmess | 102.177.189.101 | 2.53 |
| 25 | vmess | 104.16.0.10 | 2.54 |
| 26 | vmess | 172.67.71.145 | 2.55 |
| 27 | vmess | 172.67.71.145 | 2.57 |
| 28 | vmess | npmjs.com | 2.58 |
| 29 | vmess | npmjs.com | 2.62 |
| 30 | vmess | npmjs.com | 2.64 |
| 31 | vmess | npmjs.com | 2.65 |
| 32 | trojan | zula.ir | 2.80 |
| 33 | vmess | 104.21.0.0 | 2.82 |
| 34 | trojan | zula.ir | 2.82 |
| 35 | trojan | zula.ir | 2.84 |
| 36 | trojan | zula.ir | 3.09 |
| 37 | vmess | fastcup.net | 3.35 |
| 38 | vmess | fastcup.net | 3.44 |
| 39 | vmess | elma.ns.cloudflare.com | 3.62 |
| 40 | vmess | www.speedtest.net | 3.63 |
| 41 | vmess | www.speedtest.net | 3.89 |
| 42 | vmess | csgo.com | 4.14 |
| 43 | vmess | www.speedtest.net | 4.24 |
| 44 | vmess | www.speedtest.net | 4.26 |
| 45 | vmess | 104.17.223.18 | 4.47 |
| 46 | vmess | npmjs.com | 4.71 |
| 47 | vmess | 25.25.25.210 | 4.83 |
| 48 | vmess | 185.146.173.25 | 4.86 |
| 49 | vmess | cc2dash.89060004.xyz | 4.91 |
| 50 | vmess | www.speedtest.net | 5.66 |
| 51 | vmess | www.speedtest.net | 5.87 |
| 52 | vmess | icook.tw | 5.92 |
| 53 | vmess | 102.132.188.209 | 5.95 |
| 54 | vmess | www.speedtest.net | 5.97 |
| 55 | vmess | www.speedtest.net | 5.97 |
| 56 | vmess | 151.101.3.8 | 6.10 |
| 57 | trojan | csgo.com | 6.31 |
| 58 | vmess | 102.132.188.210 | 6.80 |
| 59 | vmess | www.speedtest.net | 7.40 |
| 60 | vmess | 154.53.40.110 | 7.85 |
| 61 | vmess | pubg.ac | 8.31 |
| 62 | vmess | pubg.ac | 9.15 |
| 63 | vmess | www.speedtest.net | 9.63 |
| 64 | vmess | www.speedtest.net | 9.65 |
| 65 | trojan | pubg.ac | 10.07 |
| 66 | vmess | www.speedtest.net | 10.14 |
| 67 | vmess | aio.unlimited.biz.id | 10.41 |
| 68 | vmess | 23.162.200.227 | 13.50 |
| 69 | vmess | npmjs.com | 14.86 |
| 70 | vmess | 15.204.234.200 | 19.15 |
| 71 | vmess | 15.204.234.200 | 19.21 |
| 72 | vmess | 15.204.234.200 | 19.25 |
| 73 | vmess | 15.204.234.200 | 19.30 |
| 74 | vmess | 45.8.146.129 | 19.63 |
| 75 | vmess | 45.8.146.129 | 19.76 |
| 76 | vmess | 45.8.146.129 | 19.76 |
| 77 | vmess | 15.235.83.227 | 19.81 |
| 78 | vmess | 15.235.83.228 | 20.06 |
| 79 | vmess | 15.235.83.228 | 20.08 |
| 80 | vmess | 15.235.83.228 | 20.12 |
| 81 | vmess | 15.204.234.200 | 20.48 |
| 82 | vmess | 15.204.234.200 | 20.91 |
| 83 | trojan | fastcup.net | 21.07 |
| 84 | vmess | csgo.com | 22.49 |
| 85 | vmess | fastcup.net | 23.13 |
| 86 | trojan | fastcup.net | 23.47 |
| 87 | vmess | cc2dash.89060004.xyz | 23.64 |
| 88 | vmess | npmjs.com | 23.69 |
| 89 | vmess | csgo.com | 23.70 |
| 90 | trojan | csgo.com | 23.81 |
| 91 | vmess | 15.235.83.227 | 24.08 |
| 92 | vmess | 15.204.234.200 | 24.64 |
| 93 | trojan | csgo.com | 25.19 |
| 94 | vmess | 15.204.234.200 | 25.79 |
| 95 | trojan | 090227.xyz | 29.03 |
| 96 | vmess | vall.codefyinc.com | 35.86 |
| 97 | trojan | fastcup.net | 40.89 |
| 98 | trojan | csgo.com | 41.49 |
| 99 | vmess | chat.deepseek.com | 41.52 |
| 100 | trojan | pubg.ac | 41.89 |

