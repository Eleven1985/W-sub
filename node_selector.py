#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
node_selector - 节点速度测试和优选工具
功能：
1. 测试节点响应速度
2. 选择最优的节点
3. 生成最优节点订阅文件
"""
import os
import sys
import time
import base64
import logging
import concurrent.futures
import socket
import json
import re
from datetime import datetime

# 配置日志
sys.stdout.reconfigure(encoding='utf-8')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("node_selector.log", encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

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

class NodeSelector:
    """节点选择器，用于测试和选择最优节点"""
    def __init__(self, config):
        self.config = config
        self.nodes_with_speed = []
    
    def test_and_select_best_nodes(self, nodes):
        """测试节点速度并选择最优节点"""
        logger.info(f"[NodeSelector] 开始测试节点响应速度，共{len(nodes)}个节点需要测试")
        
        # 初始化节点速度列表
        self.nodes_with_speed = []
        
        # 并发测试节点速度
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.config["WORKERS"] * 2) as executor:
            # 创建任务列表
            futures = {executor.submit(NodeTester.test_node_speed, node, self.config["TEST_TIMEOUT"]): node for node in nodes}
            
            # 收集结果
            for future in concurrent.futures.as_completed(futures):
                node = futures[future]
                try:
                    speed = future.result()
                    if speed is not None:
                        self.nodes_with_speed.append((node, speed))
                except Exception as e:
                    logger.debug(f"[NodeSelector] 测试节点异常: {str(e)}")
        
        # 按响应速度排序（时间越短越好）
        self.nodes_with_speed.sort(key=lambda x: x[1])
        
        logger.info(f"[NodeSelector] 成功测试了{len(self.nodes_with_speed)}个节点")
        
        # 如果没有成功测试的节点，返回全部节点
        if not self.nodes_with_speed:
            logger.warning("[NodeSelector] 所有节点测试失败，将使用所有节点作为备选")
            return nodes
        
        # 选择前N个最快的节点
        best_nodes_count = min(self.config["BEST_NODES_COUNT"], len(self.nodes_with_speed))
        best_nodes = [node for node, speed in self.nodes_with_speed[:best_nodes_count]]
        
        # 记录前10个最快节点的信息
        for i, (node, speed) in enumerate(self.nodes_with_speed[:10]):
            logger.info(f"[NodeSelector] 第{i+1}快节点: 响应时间 {speed*1000:.2f}ms")
        
        logger.info(f"[NodeSelector] 已选择{len(best_nodes)}个最优节点")
        return best_nodes

    def generate_best_subscription(self, nodes, output_file):
        """生成最优节点订阅文件"""
        try:
            logger.info(f"[NodeSelector] 准备生成最优节点订阅文件: {output_file}，包含{len(nodes)}个节点")
            
            # 将节点列表转换为字符串
            nodes_text = '\n'.join(nodes)
            
            # Base64编码
            subscription_content = base64.b64encode(
                nodes_text.encode('utf-8')
            ).decode('utf-8')
            
            # 保存到文件
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(subscription_content)
            
            logger.info(f"[NodeSelector] 最优节点订阅已生成并保存到 {output_file}，包含{len(nodes)}个节点")
            return subscription_content
        except Exception as e:
            logger.error(f"[NodeSelector] 生成最优节点订阅文件{output_file}失败: {str(e)}")
            # 尝试创建空文件，确保文件存在
            try:
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write('')
                logger.warning(f"[NodeSelector] 已创建空的{output_file}文件")
            except:
                pass
            return None

if __name__ == "__main__":
    # 示例用法
    logger.info("=== Node Selector 工具启动 ===")
    logger.info(f"当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 示例配置
    sample_config = {
        "WORKERS": 10,
        "TEST_TIMEOUT": 3,
        "BEST_NODES_COUNT": 50
    }
    
    # 创建选择器实例
    selector = NodeSelector(sample_config)
    
    # 这里仅作为示例，实际使用时会传入真实的节点列表
    logger.info("Node Selector 示例运行完成")