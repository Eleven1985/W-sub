#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
w-sub - 节点订阅汇总工具
功能：
1. 从指定URL获取节点配置
2. 合并多个源的节点
3. 测试节点延迟，筛选出速度最快的100个节点
4. 生成两个订阅文件：全部节点和最优节点
5. 更新README.md显示最优节点信息
"""
import os
import re
import sys
import time
import base64
import socket
import json
import logging
import requests
import concurrent.futures
from datetime import datetime
from urllib.parse import urlparse, quote

# 配置日志
sys.stdout.reconfigure(encoding='utf-8')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("w-sub.log", encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class ConfigLoader:
    """配置加载器，从配置文件读取设置"""
    @staticmethod
    def load_config(config_file="config.txt"):
        config = {
            "SOURCES": [],
            "MAX_NODES": 100,
            "TIMEOUT": 5,
            "OUTPUT_ALL_FILE": "subscription_all.txt",
            "OUTPUT_BEST_FILE": "subscription_best.txt",
            "WORKERS": 10,
            "PING_TIMEOUT": 3,
            "TEST_COUNT": 3,
            "MIN_VALID_NODES": 10,  # 最小有效节点数
            "MAX_RETRY": 2  # 获取节点源的重试次数
        }
        
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    # 忽略注释和空行
                    if line.startswith('#') or not line:
                        continue
                    
                    # 解析配置项
                    if '=' in line:
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip()
                        
                        if key == "SOURCES":
                            config[key].append(value)
                        elif key in config:
                            # 根据配置项类型转换值
                            if key in ["MAX_NODES", "TIMEOUT", "WORKERS", "PING_TIMEOUT", "TEST_COUNT", "MIN_VALID_NODES", "MAX_RETRY"]:
                                try:
                                    config[key] = int(value)
                                except ValueError:
                                    logger.warning(f"配置项 {key} 的值 {value} 不是有效的数字，使用默认值 {config[key]}")
                            else:
                                config[key] = value
            
            logger.info(f"成功加载配置，共 {len(config['SOURCES'])} 个节点源")
            return config
        except Exception as e:
            logger.error(f"加载配置文件失败: {str(e)}")
            logger.info("使用默认配置继续执行")
            return config

class NodeProcessor:
    def __init__(self, config):
        self.config = config
        self.nodes = []
        self.node_latencies = {}
        self.valid_nodes_count = 0
        self.failed_nodes_count = 0
        self.debug_info = []
    
    def fetch_nodes(self, url):
        """从指定URL获取节点配置"""
        retry_count = 0
        while retry_count <= self.config["MAX_RETRY"]:
            try:
                logger.info(f"正在获取节点源: {url} (尝试 {retry_count+1}/{self.config['MAX_RETRY']+1})")
                response = requests.get(url, timeout=self.config["TIMEOUT"])
                response.encoding = 'utf-8'
                
                if response.status_code == 200:
                    content = response.text
                    
                    # 尝试解码base64内容（多次尝试）
                    decoded_content = self._try_decode_base64(content)
                    
                    # 提取节点
                    new_nodes = self._extract_nodes(decoded_content)
                    logger.info(f"从{url}获取到{len(new_nodes)}个节点")
                    return new_nodes
                else:
                    logger.warning(f"获取{url}失败，状态码: {response.status_code}")
            except Exception as e:
                logger.error(f"获取{url}时发生错误: {str(e)}")
            
            retry_count += 1
            if retry_count <= self.config["MAX_RETRY"]:
                logger.info(f"{url} 获取失败，{self.config['TIMEOUT']}秒后重试...")
                time.sleep(self.config["TIMEOUT"])
        
        return []
    
    def _try_decode_base64(self, content):
        """智能尝试解码base64内容"""
        try:
            # 清理可能的换行符和空格
            cleaned_content = content.strip().replace('\n', '').replace('\r', '')
            
            # 检查是否可能是base64编码
            if re.match(r'^[A-Za-z0-9+/]+[=]{0,2}$', cleaned_content):
                # 尝试多种可能的填充方式
                for padding in ['', '=', '==']:
                    try:
                        padded_content = cleaned_content + padding
                        decoded = base64.b64decode(padded_content).decode('utf-8', errors='ignore')
                        # 验证解码结果是否合理
                        if len(decoded) > len(content) * 0.5 and any(char in decoded for char in ['vmess://', 'v2ray://', 'trojan://']):
                            logger.info("成功解码base64内容")
                            return decoded
                    except:
                        continue
        except Exception as e:
            logger.error(f"解码base64内容时发生错误: {str(e)}")
        
        # 解码失败，返回原始内容
        return content
    
    def _extract_nodes(self, content):
        """从内容中提取节点链接"""
        # 支持的节点类型正则表达式
        patterns = [
            r'(vmess://[^\s]+)',
            r'(v2ray://[^\s]+)',
            r'(trojan://[^\s]+)',
            r'(shadowsocks://[^\s]+)',
            r'(shadowsocksr://[^\s]+)',
        ]
        
        nodes = []
        for pattern in patterns:
            matches = re.findall(pattern, content, re.MULTILINE)
            nodes.extend(matches)
        
        # 去重
        unique_nodes = list(set(nodes))
        logger.info(f"从内容中提取并去重后，得到{len(unique_nodes)}个节点")
        return unique_nodes
    
    def _parse_node_info(self, node):
        """从节点链接中解析出服务器信息"""
        try:
            # 获取节点类型
            node_type = "Unknown"
            type_patterns = {
                'vmess://': 'vmess',
                'v2ray://': 'v2ray', 
                'trojan://': 'trojan',
                'shadowsocks://': 'ss',
                'shadowsocksr://': 'ssr'
            }
            
            for prefix, type_name in type_patterns.items():
                if node.startswith(prefix):
                    node_type = type_name
                    encoded_part = node[len(prefix):]
                    break
            else:
                # 不是以已知前缀开头，返回基本信息
                return "Unknown", "Unknown", node[:30] + ("..." if len(node) > 30 else "")
            
            # 尝试解码节点内容
            try:
                # 处理可能的URL编码
                encoded_part = encoded_part.replace('-', '+').replace('_', '/')
                # 补全base64填充
                padding_needed = 4 - (len(encoded_part) % 4)
                if padding_needed < 4:
                    encoded_part += '=' * padding_needed
                
                decoded = base64.b64decode(encoded_part).decode('utf-8', errors='ignore')
                
                # 尝试解析JSON格式的节点信息（主要针对vmess）
                if node_type == 'vmess' or node_type == 'v2ray':
                    try:
                        vmess_data = json.loads(decoded)
                        address = vmess_data.get('add', 'Unknown')
                        port = vmess_data.get('port', 'Unknown')
                        server_info = f"{address}:{port}"
                        return node_type, server_info, node[:30] + "..."
                    except json.JSONDecodeError:
                        pass
                
                # 提取地址信息
                address = "Unknown"
                # 查找域名或IP
                domain_pattern = r'([a-zA-Z0-9][a-zA-Z0-9-]{0,61}[a-zA-Z0-9]\.[a-zA-Z]{2,})'
                ip_pattern = r'\b(?:\d{1,3}\.){3}\d{1,3}\b'
                
                domain_matches = re.findall(domain_pattern, decoded)
                if domain_matches:
                    address = domain_matches[0]
                else:
                    ip_matches = re.findall(ip_pattern, decoded)
                    if ip_matches:
                        address = ip_matches[0]
                
                # 查找端口
                port_matches = re.findall(r':(\d{1,5})', decoded)
                port = port_matches[0] if port_matches else 'Unknown'
                
                server_info = f"{address}:{port}"
                return node_type, server_info, node[:30] + "..."
            except Exception as e:
                logger.debug(f"解析节点内容时出错: {str(e)}")
                # 从原始节点字符串中提取可能的地址
                domain_matches = re.findall(r'([a-zA-Z0-9][a-zA-Z0-9-]{0,61}[a-zA-Z0-9]\.[a-zA-Z]{2,})', node)
                ip_matches = re.findall(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', node)
                
                if domain_matches:
                    address = domain_matches[0]
                elif ip_matches:
                    address = ip_matches[0]
                else:
                    address = "Unknown"
                
                return node_type, address, node[:30] + "..."
        except Exception as e:
            logger.error(f"解析节点信息时发生错误: {str(e)}")
            return "Unknown", "Unknown", node[:30] + ("..." if len(node) > 30 else "")
    
    def _test_node_latency(self, node):
        """测试节点延迟"""
        try:
            node_type, address, node_id = self._parse_node_info(node)
            
            # 如果无法解析地址，跳过测试
            if address == "Unknown" or address == "" or ':' not in address and not re.match(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', address):
                self.debug_info.append(f"无法解析地址: {node_id} (类型: {node_type})")
                self.failed_nodes_count += 1
                return node, float('inf')
            
            # 分离主机和端口
            try:
                if ':' in address:
                    host, port = address.rsplit(':', 1)
                    port = int(port)
                else:
                    host = address
                    port = 443  # 默认使用443端口
            except:
                host = address
                port = 443
            
            # 记录调试信息
            self.debug_info.append(f"测试节点: {node_id} (类型: {node_type}, 地址: {host}:{port})")
            
            latencies = []
            for i in range(self.config["TEST_COUNT"]):
                try:
                    # 创建socket连接测试延迟
                    start_time = time.time()
                    with socket.create_connection((host, port), timeout=self.config["PING_TIMEOUT"]):
                        latency = (time.time() - start_time) * 1000  # 转换为毫秒
                        latencies.append(latency)
                        self.debug_info.append(f"测试 {i+1}/{self.config['TEST_COUNT']} 成功: {latency:.2f}ms")
                except socket.timeout:
                    self.debug_info.append(f"测试 {i+1}/{self.config['TEST_COUNT']} 超时")
                except Exception as e:
                    self.debug_info.append(f"测试 {i+1}/{self.config['TEST_COUNT']} 失败: {str(e)}")
                
                # 测试间隔
                time.sleep(0.1)
            
            # 计算平均延迟，如果没有成功的测试结果则返回无穷大
            if latencies:
                avg_latency = sum(latencies) / len(latencies)
                self.valid_nodes_count += 1
                self.debug_info.append(f"节点测试完成: {node_id} 平均延迟 {avg_latency:.2f}ms")
                return node, avg_latency
            else:
                self.failed_nodes_count += 1
                self.debug_info.append(f"节点测试失败: {node_id} 所有测试均未成功")
                return node, float('inf')
        except Exception as e:
            logger.error(f"测试节点延迟时发生错误: {str(e)}")
            self.failed_nodes_count += 1
            return node, float('inf')
    
    def merge_nodes(self):
        """合并所有源的节点"""
        all_nodes = []
        
        # 并发获取所有源的节点
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.config["WORKERS"]) as executor:
            results = list(executor.map(self.fetch_nodes, self.config["SOURCES"]))
        
        # 合并结果
        for nodes in results:
            all_nodes.extend(nodes)
        
        # 去重
        self.nodes = list(set(all_nodes))
        logger.info(f"合并后共获取到{len(self.nodes)}个唯一节点")
    
    def test_all_nodes_latency(self):
        """测试所有节点的延迟"""
        logger.info(f"开始测试节点延迟（共{len(self.nodes)}个节点）...")
        
        # 创建一个临时文件记录调试信息
        debug_file = "node_test_debug.txt"
        
        # 分批测试节点，避免资源耗尽
        batch_size = min(50, self.config["WORKERS"] * 3)
        for i in range(0, len(self.nodes), batch_size):
            batch_nodes = self.nodes[i:i+batch_size]
            logger.info(f"测试批次 {i//batch_size + 1}/{(len(self.nodes)+batch_size-1)//batch_size} ({len(batch_nodes)}个节点)")
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=self.config["WORKERS"]) as executor:
                results = list(executor.map(self._test_node_latency, batch_nodes))
            
            # 更新延迟结果
            for node, latency in results:
                if latency < float('inf'):
                    self.node_latencies[node] = latency
            
            # 保存调试信息
            with open(debug_file, 'w', encoding='utf-8') as f:
                f.write('\n'.join(self.debug_info))
            
            # 避免请求过于频繁
            if i + batch_size < len(self.nodes):
                time.sleep(1)
        
        logger.info(f"延迟测试完成，成功测试{len(self.node_latencies)}个节点，失败{self.failed_nodes_count}个节点")
        
        # 检查有效节点数是否满足最低要求
        if len(self.node_latencies) < self.config["MIN_VALID_NODES"]:
            logger.warning(f"有效节点数 {len(self.node_latencies)} 低于最小要求 {self.config['MIN_VALID_NODES']}")
    
    def filter_fastest_nodes(self):
        """筛选出延迟最低的节点"""
        # 按延迟排序
        sorted_nodes = sorted(
            self.node_latencies.items(), 
            key=lambda x: x[1]
        )
        
        # 保留前N个节点
        max_nodes = min(self.config["MAX_NODES"], len(sorted_nodes))
        fastest_nodes = [node for node, _ in sorted_nodes[:max_nodes]]
        
        logger.info(f"筛选出{len(fastest_nodes)}个延迟最低的节点")
        return fastest_nodes, sorted_nodes[:max_nodes]
    
    def generate_subscription(self, nodes, output_file):
        """生成订阅文件"""
        # 将节点列表转换为字符串
        nodes_text = '\n'.join(nodes)
        
        # Base64编码
        subscription_content = base64.b64encode(
            nodes_text.encode('utf-8')
        ).decode('utf-8')
        
        # 保存到文件
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(subscription_content)
        
        logger.info(f"订阅已生成并保存到 {output_file}，包含{len(nodes)}个节点")
        return subscription_content
    
    def update_readme(self, sorted_nodes_with_latency):
        """更新README.md文件，显示最优节点信息"""
        try:
            # 读取当前README内容
            if not os.path.exists('README.md'):
                logger.error("README.md文件不存在")
                return
                
            with open('README.md', 'r', encoding='utf-8') as f:
                readme_content = f.read()
            
            # 准备节点信息表格
            node_table = "| 排名 | 节点类型 | 服务器地址 | 延迟(ms) | 状态 |\n|------|----------|------------|----------|------|\n"
            for i, (node, latency) in enumerate(sorted_nodes_with_latency, 1):
                node_type, address, _ = self._parse_node_info(node)
                # 限制地址长度，避免表格过宽
                display_address = address[:40] + ("..." if len(address) > 40 else "")
                status = "✓" if latency < 1000 else "⚠️"
                node_table += f"| {i} | {node_type} | {display_address} | {latency:.2f} | {status} |\n"
            
            # 添加统计信息
            stats_info = f"""
## 节点统计信息

- 总获取节点数: {len(self.nodes)}
- 有效节点数: {self.valid_nodes_count}
- 无效节点数: {self.failed_nodes_count}
- 测试成功率: {(self.valid_nodes_count/len(self.nodes)*100) if self.nodes else 0:.2f}%
- 平均延迟: {sum(self.node_latencies.values())/len(self.node_latencies) if self.node_latencies else 0:.2f}ms
            """
            
            # 更新时间
            update_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            update_info = f"\n### 最新节点状态\n\n更新时间: {update_time}\n\n共测试 {len(self.node_latencies)} 个节点，筛选出以下 {len(sorted_nodes_with_latency)} 个最优节点（按延迟由低到高排序）：\n\n{node_table}\n{stats_info}\n\n**注意：** 节点状态信息与{subscription_content[:50]}...文件中的内容完全对应\n"
            
            # 替换或添加节点信息部分
            if "### 最新节点状态" in readme_content:
                # 替换现有内容
                readme_content = re.sub(
                    r'### 最新节点状态.*?(?=\n## |$)', 
                    update_info, 
                    readme_content, 
                    flags=re.DOTALL
                )
            else:
                # 添加到文件末尾
                readme_content += "\n" + update_info
            
            # 保存更新后的README
            with open('README.md', 'w', encoding='utf-8') as f:
                f.write(readme_content)
            
            logger.info("README.md已更新，显示最新节点信息")
        except Exception as e:
            logger.error(f"更新README.md时发生错误: {str(e)}")

def main():
    logger.info("=== w-sub 节点订阅汇总工具启动 ===")
    logger.info(f"当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 加载配置
    config = ConfigLoader.load_config()
    
    # 创建处理器实例
    processor = NodeProcessor(config)
    
    # 执行处理流程
    processor.merge_nodes()
    
    if not processor.nodes:
        logger.error("未能获取任何节点，请检查网络连接或源地址是否有效")
        return
    
    # 生成包含所有节点的订阅文件
    processor.generate_subscription(processor.nodes, config["OUTPUT_ALL_FILE"])
    
    # 测试节点延迟并生成最优节点订阅文件
    processor.test_all_nodes_latency()
    
    if processor.node_latencies:
        fastest_nodes, sorted_nodes_with_latency = processor.filter_fastest_nodes()
        processor.generate_subscription(fastest_nodes, config["OUTPUT_BEST_FILE"])
        
        # 更新README.md显示节点信息
        processor.update_readme(sorted_nodes_with_latency)
    else:
        logger.warning("未能测试出任何可用节点的延迟")
        # 即使没有有效节点，也更新README
        processor.update_readme([])
    
    logger.info("处理完成！")

if __name__ == "__main__":
    main()