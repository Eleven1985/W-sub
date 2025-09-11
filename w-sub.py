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
import requests
import concurrent.futures
from datetime import datetime
from urllib.parse import urlparse

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
            "TEST_COUNT": 3
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
                            if key in ["MAX_NODES", "TIMEOUT", "WORKERS", "PING_TIMEOUT", "TEST_COUNT"]:
                                try:
                                    config[key] = int(value)
                                except ValueError:
                                    print(f"警告：配置项 {key} 的值 {value} 不是有效的数字，使用默认值 {config[key]}")
                            else:
                                config[key] = value
            
            print(f"成功加载配置，共 {len(config['SOURCES'])} 个节点源")
            return config
        except Exception as e:
            print(f"加载配置文件失败: {str(e)}")
            print("使用默认配置继续执行")
            return config

class NodeProcessor:
    def __init__(self, config):
        self.config = config
        self.nodes = []
        self.node_latencies = {}
        
    def fetch_nodes(self, url):
        """从指定URL获取节点配置"""
        try:
            print(f"正在获取节点源: {url}")
            response = requests.get(url, timeout=self.config["TIMEOUT"])
            response.encoding = 'utf-8'
            
            if response.status_code == 200:
                # 处理base64编码的内容
                content = response.text
                try:
                    # 尝试解码可能的base64内容
                    decoded = base64.b64decode(content).decode('utf-8', errors='ignore')
                    if len(decoded) > len(content) * 0.7:  # 简单判断是否为有效解码
                        content = decoded
                except:
                    pass
                
                # 提取节点
                new_nodes = self._extract_nodes(content)
                print(f"从{url}获取到{len(new_nodes)}个节点")
                return new_nodes
            else:
                print(f"获取{url}失败，状态码: {response.status_code}")
                return []
        except Exception as e:
            print(f"获取{url}时发生错误: {str(e)}")
            return []
    
    def _extract_nodes(self, content):
        """从内容中提取节点链接"""
        # 支持的节点类型正则表达式
        patterns = [
            r'v2ray://[^\s]+',
            r'vmess://[^\s]+',
            r'trojan://[^\s]+',
            r'shadowsocks://[^\s]+',
            r'shadowsocksr://[^\s]+',
        ]
        
        nodes = []
        for pattern in patterns:
            matches = re.findall(pattern, content, re.MULTILINE)
            nodes.extend(matches)
        
        # 去重
        return list(set(nodes))
    
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
        print(f"合并后共获取到{len(self.nodes)}个唯一节点")
    
    def _parse_node_info(self, node):
        """从节点链接中解析出服务器信息"""
        try:
            # 获取节点类型
            node_type = "Unknown"
            for type_keyword in ['vmess://', 'v2ray://', 'trojan://', 'shadowsocks://', 'shadowsocksr://']:
                if type_keyword in node:
                    node_type = type_keyword.replace('://', '')
                    break
            
            # 尝试解析节点地址
            address = "Unknown"
            if '://' in node:
                try:
                    parts = node.split('://', 1)
                    if len(parts) > 1:
                        decoded = base64.b64decode(parts[1]).decode('utf-8', errors='ignore')
                        # 查找可能的服务器地址
                        for pattern in [r'"add":"([^"]+)"', r'address=([^,]+)', r'([a-zA-Z0-9.-]+):\d+']:
                            matches = re.findall(pattern, decoded)
                            if matches:
                                address = matches[0]
                                break
                except:
                    pass
            
            # 从节点文本中提取可能的域名或IP作为备用
            if address == "Unknown":
                domain_pattern = r'([a-zA-Z0-9][a-zA-Z0-9-]{0,61}[a-zA-Z0-9]\.[a-zA-Z]{2,})'
                ip_pattern = r'\b(?:\d{1,3}\.){3}\d{1,3}\b'
                
                domain_matches = re.findall(domain_pattern, node)
                if domain_matches:
                    address = domain_matches[0]
                else:
                    ip_matches = re.findall(ip_pattern, node)
                    if ip_matches:
                        address = ip_matches[0]
            
            # 截取节点链接的一部分作为标识
            node_id = node[:30] + ("..." if len(node) > 30 else "")
            
            return node_type, address, node_id
        except:
            return "Unknown", "Unknown", node[:30] + ("..." if len(node) > 30 else "")
    
    def _test_node_latency(self, node):
        """测试节点延迟"""
        try:
            node_type, address, _ = self._parse_node_info(node)
            if address == "Unknown" or address == "":
                return node, float('inf')  # 无法解析地址，延迟设为无穷大
            
            latencies = []
            for _ in range(self.config["TEST_COUNT"]):
                start_time = time.time()
                
                # 创建socket连接测试延迟
                try:
                    with socket.create_connection((address, 443), timeout=self.config["PING_TIMEOUT"]):
                        latency = (time.time() - start_time) * 1000  # 转换为毫秒
                        latencies.append(latency)
                except:
                    continue
            
            # 计算平均延迟，如果没有成功的测试结果则返回无穷大
            return node, sum(latencies) / len(latencies) if latencies else float('inf')
        except:
            return node, float('inf')
    
    def test_all_nodes_latency(self):
        """测试所有节点的延迟"""
        print(f"开始测试节点延迟（共{len(self.nodes)}个节点）...")
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.config["WORKERS"]) as executor:
            results = list(executor.map(self._test_node_latency, self.nodes))
        
        # 保存延迟结果，过滤掉无法连接的节点
        valid_results = [(node, latency) for node, latency in results if latency < float('inf')]
        self.node_latencies = {node: latency for node, latency in valid_results}
        
        print(f"延迟测试完成，成功测试{len(valid_results)}个节点")
    
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
        
        print(f"筛选出{len(fastest_nodes)}个延迟最低的节点")
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
        
        print(f"订阅已生成并保存到 {output_file}")
        return subscription_content
    
    def update_readme(self, sorted_nodes_with_latency):
        """更新README.md文件，显示最优节点信息"""
        try:
            # 读取当前README内容
            with open('README.md', 'r', encoding='utf-8') as f:
                readme_content = f.read()
            
            # 准备节点信息表格
            node_table = "| 排名 | 节点类型 | 服务器地址 | 延迟(ms) |\n|------|----------|------------|----------|\n"
            for i, (node, latency) in enumerate(sorted_nodes_with_latency, 1):
                node_type, address, _ = self._parse_node_info(node)
                # 限制地址长度，避免表格过宽
                display_address = address[:30] + ("..." if len(address) > 30 else "")
                node_table += f"| {i} | {node_type} | {display_address} | {latency:.2f} |\n"
            
            # 更新时间
            update_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            update_info = f"\n### 最新节点状态\n\n更新时间: {update_time}\n\n共测试 {len(self.node_latencies)} 个节点，筛选出以下 {len(sorted_nodes_with_latency)} 个最优节点（按延迟由低到高排序）：\n\n"
            
            # 替换或添加节点信息部分
            if "### 最新节点状态" in readme_content:
                # 替换现有内容
                readme_content = re.sub(
                    r'### 最新节点状态.*?(?=\n## |$)', 
                    update_info + node_table, 
                    readme_content, 
                    flags=re.DOTALL
                )
            else:
                # 添加到文件末尾
                readme_content += "\n" + update_info + node_table
            
            # 保存更新后的README
            with open('README.md', 'w', encoding='utf-8') as f:
                f.write(readme_content)
            
            print("README.md已更新，显示最新节点信息")
        except Exception as e:
            print(f"更新README.md时发生错误: {str(e)}")

def main():
    print("=== w-sub 节点订阅汇总工具 ===")
    print(f"当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 加载配置
    config = ConfigLoader.load_config()
    
    # 创建处理器实例
    processor = NodeProcessor(config)
    
    # 执行处理流程
    processor.merge_nodes()
    
    if not processor.nodes:
        print("错误：未能获取任何节点，请检查网络连接或源地址是否有效")
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
        print("警告：未能测试出任何可用节点的延迟")
    
    print("\n处理完成！")

if __name__ == "__main__":
    main()