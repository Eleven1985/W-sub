#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
w-sub - 节点订阅汇总工具
功能：
1. 从指定URL获取节点配置
2. 合并多个源的节点
3. 测试节点响应速度并排序
4. 生成包含最优节点的订阅文件
"""
import os
import re
import sys
import time
import base64
import json
import logging
import requests
import concurrent.futures
from datetime import datetime
import socket
import struct
import urllib.parse

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
            "TIMEOUT": 5,
            "OUTPUT_ALL_FILE": "subscription_all.txt",
            "OUTPUT_BEST_FILE": "subscription_best.txt",
            "WORKERS": 10,
            "MAX_RETRY": 2,  # 获取节点源的重试次数
            "BEST_NODES_COUNT": 50,  # 优选节点数量
            "TEST_TIMEOUT": 3  # 节点测试超时时间（秒）
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
                            if key in ["TIMEOUT", "WORKERS", "MAX_RETRY", "BEST_NODES_COUNT", "TEST_TIMEOUT"]:
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

class NodeTester:
    """节点测试器，用于测试节点的响应速度"""
    @staticmethod
    def test_node_speed(node_url, timeout=3):
        """测试节点响应速度"""
        try:
            # 提取服务器信息
            server_info = NodeTester._extract_server_info(node_url)
            if not server_info or len(server_info) != 2:
                logger.debug(f"无法解析节点信息: {node_url[:50]}...")
                return None
            
            host, port = server_info
            
            # 创建套接字并测量连接时间
            start_time = time.time()
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(timeout)
                s.connect((host, port))
                end_time = time.time()
                response_time = end_time - start_time
                return response_time
        except socket.gaierror:
            logger.debug(f"节点域名解析失败: {host if 'host' in locals() else 'unknown'}")
            return None
        except socket.timeout:
            logger.debug(f"节点连接超时: {node_url[:50]}...")
            return None
        except ConnectionRefusedError:
            logger.debug(f"节点连接被拒绝: {node_url[:50]}...")
            return None
        except Exception as e:
            # 忽略测试失败的节点，仅记录调试信息
            logger.debug(f"测试节点失败: {str(e)}")
            return None
    
    @staticmethod
    def _extract_server_info(node_url):
        """从节点URL中提取服务器地址和端口"""
        try:
            # 处理vmess节点
            if node_url.startswith('vmess://'):
                try:
                    vmess_data = node_url[8:]
                    # 确保base64字符串长度是4的倍数
                    padding_length = 4 - (len(vmess_data) % 4)
                    if padding_length < 4:
                        vmess_data += '=' * padding_length
                    
                    decoded = base64.b64decode(vmess_data).decode('utf-8', errors='ignore')
                    vmess_json = json.loads(decoded)
                    return vmess_json.get('add'), int(vmess_json.get('port', 0))
                except:
                    # 如果标准解析失败，尝试使用更宽松的方式
                    try:
                        # 直接在URL中查找可能的IP和端口
                        ip_port_match = re.search(r'(\d+\.\d+\.\d+\.\d+):(\d+)', node_url)
                        if ip_port_match:
                            return ip_port_match.group(1), int(ip_port_match.group(2))
                    except:
                        pass
                    return None
            
            # 处理vless节点
            elif node_url.startswith('vless://'):
                # vless://uuid@host:port?path=...
                match = re.search(r'vless://[^@]+@([^:]+):(\d+)', node_url)
                if match:
                    return match.group(1), int(match.group(2))
                
                # 尝试匹配IP地址和端口
                ip_port_match = re.search(r'(\d+\.\d+\.\d+\.\d+):(\d+)', node_url)
                if ip_port_match:
                    return ip_port_match.group(1), int(ip_port_match.group(2))
            
            # 处理trojan节点
            elif node_url.startswith('trojan://'):
                # trojan://password@host:port?path=...
                match = re.search(r'trojan://[^@]+@([^:]+):(\d+)', node_url)
                if match:
                    return match.group(1), int(match.group(2))
                
                # 尝试匹配IP地址和端口
                ip_port_match = re.search(r'(\d+\.\d+\.\d+\.\d+):(\d+)', node_url)
                if ip_port_match:
                    return ip_port_match.group(1), int(ip_port_match.group(2))
            
            # 处理shadowsocks节点
            elif node_url.startswith('shadowsocks://') or node_url.startswith('ss://'):
                # ss://base64(加密:密码)@host:port
                ss_data = node_url[5:] if node_url.startswith('ss://') else node_url[13:]
                # 解码ss节点信息
                if '#' in ss_data:
                    ss_data = ss_data.split('#')[0]
                if '@' in ss_data:
                    try:
                        encoded_part, server_part = ss_data.split('@')
                        if ':' in server_part:
                            host, port = server_part.split(':')
                            return host, int(port)
                    except:
                        pass
                
                # 尝试匹配IP地址和端口
                ip_port_match = re.search(r'(\d+\.\d+\.\d+\.\d+):(\d+)', node_url)
                if ip_port_match:
                    return ip_port_match.group(1), int(ip_port_match.group(2))
            
            # 处理其他类型节点，尝试通用解析方法
            # 查找URL中的host:port模式
            match = re.search(r'@([^:]+):(\d+)', node_url)
            if match:
                return match.group(1), int(match.group(2))
            
            # 尝试匹配IP地址和端口
            ip_port_match = re.search(r'(\d+\.\d+\.\d+\.\d+):(\d+)', node_url)
            if ip_port_match:
                return ip_port_match.group(1), int(ip_port_match.group(2))
            
            # 增强：尝试匹配域名和端口
            domain_port_match = re.search(r'([a-zA-Z0-9.-]+):(\d+)', node_url)
            if domain_port_match:
                domain = domain_port_match.group(1)
                # 确保这是一个有效的域名格式（不是URL中的其他部分）
                if not domain.startswith('http') and '.' in domain:
                    return domain, int(domain_port_match.group(2))
            
            return None
        except Exception as e:
            logger.debug(f"解析节点信息失败: {str(e)}")
            return None

class NodeProcessor:
    def __init__(self, config):
        self.config = config
        self.nodes = []
        self.valid_nodes_count = 0
        self.failed_nodes_count = 0
        self.debug_info = []
        self.nodes_with_speed = []  # 存储节点和对应的响应时间
    
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
            original_length = len(cleaned_content)
            
            # 尝试多种可能的解码方式
            # 1. 直接尝试解码
            try:
                decoded = base64.b64decode(cleaned_content, validate=True).decode('utf-8', errors='ignore')
                if any(char in decoded for char in ['vmess://', 'v2ray://', 'trojan://', 'shadowsocks://', 'vless://']):
                    logger.info(f"成功解码base64内容 (原始长度: {original_length}, 解码后长度: {len(decoded)})")
                    return decoded
            except:
                pass
            
            # 2. 尝试不同的填充方式
            for padding in ['', '=', '==']:
                try:
                    padded_content = cleaned_content + padding
                    decoded = base64.b64decode(padded_content).decode('utf-8', errors='ignore')
                    if any(char in decoded for char in ['vmess://', 'v2ray://', 'trojan://', 'shadowsocks://', 'vless://']):
                        logger.info(f"成功解码base64内容(使用填充) (原始长度: {original_length})")
                        return decoded
                except:
                    continue
            
            # 3. 尝试每4个字符一组进行解码
            for i in range(4):
                try:
                    adjusted_content = cleaned_content[i:]
                    decoded = base64.b64decode(adjusted_content).decode('utf-8', errors='ignore')
                    if any(char in decoded for char in ['vmess://', 'v2ray://', 'trojan://', 'shadowsocks://', 'vless://']):
                        logger.info(f"成功解码base64内容(偏移{i}) (原始长度: {original_length})")
                        return decoded
                except:
                    continue
            
            # 4. 增强：尝试按行解码
            lines = content.strip().split('\n')
            if len(lines) > 1:
                decoded_lines = []
                for line in lines:
                    try:
                        decoded_line = base64.b64decode(line.strip(), validate=True).decode('utf-8', errors='ignore')
                        decoded_lines.append(decoded_line)
                    except:
                        decoded_lines.append(line)
                combined = '\n'.join(decoded_lines)
                if any(char in combined for char in ['vmess://', 'v2ray://', 'trojan://', 'shadowsocks://', 'vless://']):
                    logger.info(f"成功解码多行base64内容 (行数: {len(lines)})")
                    return combined
        except Exception as e:
            logger.error(f"解码base64内容时发生错误: {str(e)}")
        
        # 解码失败，返回原始内容
        logger.debug(f"无法解码base64内容，返回原始内容 (长度: {original_length})")
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
            r'(vless://[^\s]+)',
            r'(ss://[^\s]+)',
            r'(ssr://[^\s]+)',
            r'(trojan-go://[^\s]+)',
            # 增强：添加更多可能的节点格式
            r'(clash://[^\s]+)',
            r'(sing-box://[^\s]+)',
            r'(hysteria://[^\s]+)'
        ]
        
        nodes = []
        for pattern in patterns:
            matches = re.findall(pattern, content, re.MULTILINE)
            nodes.extend(matches)
        
        # 去重
        unique_nodes = list(set(nodes))
        logger.info(f"从内容中提取并去重后，得到{len(unique_nodes)}个节点 (原始提取: {len(nodes)})")
        return unique_nodes
    
    def merge_nodes(self):
        """合并所有源的节点"""
        all_nodes = []
        total_extracted = 0
        
        # 并发获取所有源的节点
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.config["WORKERS"]) as executor:
            results = list(executor.map(self.fetch_nodes, self.config["SOURCES"]))
        
        # 合并结果
        for nodes in results:
            total_extracted += len(nodes)
            all_nodes.extend(nodes)
        
        # 去重
        self.nodes = list(set(all_nodes))
        logger.info(f"合并后共获取到{len(self.nodes)}个唯一节点 (总提取: {total_extracted}个节点)")
        logger.info(f"去重后减少了{total_extracted - len(self.nodes)}个重复节点")
    
    def test_and_select_best_nodes(self):
        """测试节点速度并选择最优节点"""
        logger.info(f"开始测试节点响应速度，共{len(self.nodes)}个节点需要测试")
        
        # 并发测试节点速度
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.config["WORKERS"] * 2) as executor:
            # 创建任务列表
            futures = {executor.submit(NodeTester.test_node_speed, node, self.config["TEST_TIMEOUT"]): node for node in self.nodes}
            
            # 收集结果
            for future in concurrent.futures.as_completed(futures):
                node = futures[future]
                try:
                    speed = future.result()
                    if speed is not None:
                        self.nodes_with_speed.append((node, speed))
                except Exception as e:
                    logger.debug(f"测试节点异常: {str(e)}")
        
        # 按响应速度排序（时间越短越好）
        self.nodes_with_speed.sort(key=lambda x: x[1])
        
        logger.info(f"成功测试了{len(self.nodes_with_speed)}个节点")
        
        # 如果没有成功测试的节点，返回全部节点
        if not self.nodes_with_speed:
            logger.warning("所有节点测试失败，将使用所有节点作为备选")
            return self.nodes
        
        # 选择前N个最快的节点
        best_nodes_count = min(self.config["BEST_NODES_COUNT"], len(self.nodes_with_speed))
        best_nodes = [node for node, speed in self.nodes_with_speed[:best_nodes_count]]
        
        # 记录前10个最快节点的信息
        for i, (node, speed) in enumerate(self.nodes_with_speed[:10]):
            logger.info(f"第{i+1}快节点: 响应时间 {speed*1000:.2f}ms")
        
        return best_nodes
    
    def generate_subscription(self, nodes, output_file):
        """生成订阅文件"""
        try:
            logger.info(f"准备生成订阅文件: {output_file}，包含{len(nodes)}个节点")
            
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
        except Exception as e:
            logger.error(f"生成订阅文件{output_file}失败: {str(e)}")
            # 尝试创建空文件，确保文件存在
            try:
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write('')
                logger.warning(f"已创建空的{output_file}文件")
            except:
                pass
            return None


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
    
    # 测试节点速度并选择最优节点
    best_nodes = processor.test_and_select_best_nodes()
    
    # 生成包含所有节点的订阅文件
    processor.generate_subscription(processor.nodes, config["OUTPUT_ALL_FILE"])
    
    # 生成包含最优节点的订阅文件（即使best_nodes为空，也尝试生成）
    try:
        if best_nodes:
            processor.generate_subscription(best_nodes, config["OUTPUT_BEST_FILE"])
        else:
            logger.warning("没有找到最优节点，将使用所有节点生成最优订阅文件")
            processor.generate_subscription(processor.nodes, config["OUTPUT_BEST_FILE"])
    except Exception as e:
        logger.error(f"生成最优节点订阅文件时发生严重错误: {str(e)}")
        # 最后的尝试：强制创建文件
        try:
            with open(config["OUTPUT_BEST_FILE"], 'w', encoding='utf-8') as f:
                f.write(base64.b64encode('\n'.join(processor.nodes).encode('utf-8')).decode('utf-8'))
            logger.info(f"已强制生成{config['OUTPUT_BEST_FILE']}文件")
        except Exception as inner_e:
            logger.error(f"强制生成文件失败: {str(inner_e)}")
    
    logger.info("处理完成！")

if __name__ == "__main__":
    main()