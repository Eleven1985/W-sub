# -*- coding: utf-8 -*-
import re
import base64
import logging
import requests
import os
import json
import time
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor

class NodeProcessor:
    """节点处理器，整合节点获取和合并功能"""
    
    def __init__(self, config):
        self.config = config
        self.timeout = config.get("TIMEOUT", 5)
        self.max_retry = config.get("MAX_RETRY", 2)
        self.workers = config.get("WORKERS", 10)
        # 添加黑名单配置，用于过滤特定节点
        self.blacklist_domains = self.config.get("BLACKLIST_DOMAINS", [])
        self.blacklist_ips = self.config.get("BLACKLIST_IPS", [])
        # 添加协议偏好设置
        self.preferred_protocols = self.config.get("PREFERRED_PROTOCOLS", [])
        # 添加节点质量检测设置
        self.check_connectivity = self.config.get("CHECK_CONNECTIVITY", False)
        self.connectivity_timeout = self.config.get("CONNECTIVITY_TIMEOUT", 3)
        
    def fetch_nodes(self, url):
        """从指定URL获取节点列表"""
        nodes = []
        retry_count = 0
        
        while retry_count <= self.max_retry:
            try:
                logging.info(f"正在获取节点源: {url} (尝试 {retry_count + 1}/{self.max_retry + 1})")
                response = requests.get(url, timeout=self.timeout, headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                })
                response.raise_for_status()
                
                # 尝试解码响应内容
                content = response.text.strip()
                if content:
                    nodes = self._extract_nodes(content)
                    if nodes:
                        logging.info(f"成功从 {url} 获取 {len(nodes)} 个节点")
                        break
                    else:
                        logging.warning(f"从 {url} 获取内容，但未能提取到节点")
                else:
                    logging.warning(f"从 {url} 获取的内容为空")
            except Exception as e:
                logging.error(f"获取节点源 {url} 失败: {str(e)}")
            
            retry_count += 1
            if retry_count <= self.max_retry:
                logging.info(f"将在重试 {url}")
        
        return nodes
    
    def _extract_nodes(self, content):
        """从内容中提取节点信息，增强节点类型检测和基本格式验证"""
        nodes = []
        
        # 首先尝试解码Base64
        decoded_content = self._try_decode_base64(content)
        if decoded_content:
            content = decoded_content
        
        # 按行处理内容
        lines = content.split('\n')
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # 检查是否为支持的节点类型
            if self._is_valid_node_format(line):
                # 应用过滤规则
                if self._should_keep_node(line):
                    nodes.append(line)
        
        return nodes
    
    def _is_valid_node_format(self, line):
        """更严格地检查节点格式是否有效"""
        # 支持的节点类型列表
        supported_protocols = [
            'vmess', 'v2ray', 'trojan', 'trojan-go', 'shadowsocks', 'shadowsocksr', 
            'vless', 'ss', 'ssr', 'hysteria', 'hysteria2', 'tuic', 'wireguard', 
            'naiveproxy', 'socks', 'http', 'https', 'clash'
        ]
        
        # 检查协议前缀
        for protocol in supported_protocols:
            if line.lower().startswith(f'{protocol}://'):
                # 检查基本格式有效性（非空且有足够长度）
                if len(line) > len(protocol) + 3 and len(line.split('://')[1]) > 10:
                    return True
        
        return False
    
    def _should_keep_node(self, node):
        """根据过滤规则决定是否保留节点"""
        # 1. 检查黑名单
        if self._is_in_blacklist(node):
            logging.debug(f"节点被黑名单过滤: {node[:50]}...")
            return False
        
        # 2. 如果有偏好协议设置，只保留偏好的协议
        if self.preferred_protocols:
            protocol = node.split('://')[0].lower()
            if protocol not in [p.lower() for p in self.preferred_protocols]:
                return False
        
        # 3. 检查节点基本有效性（如域名/IP格式）
        if not self._check_node_basic_validity(node):
            return False
        
        # 4. 如果启用了连通性检查，验证节点是否可连接
        if self.check_connectivity:
            if not self._check_node_connectivity(node):
                logging.debug(f"节点连通性检查失败: {node[:50]}...")
                return False
        
        return True
    
    def _is_in_blacklist(self, node):
        """检查节点是否在黑名单中"""
        # 简化版：检查节点字符串中是否包含黑名单域名或IP
        node_lower = node.lower()
        
        # 检查黑名单域名
        for domain in self.blacklist_domains:
            if domain.lower() in node_lower:
                return True
        
        # 检查黑名单IP
        for ip in self.blacklist_ips:
            if ip in node_lower:
                return True
        
        return False
    
    def _check_node_basic_validity(self, node):
        """检查节点的基本有效性"""
        try:
            # 尝试提取节点信息（这里是简化实现，实际应根据不同协议解析）
            protocol_part, content_part = node.split('://', 1)
            
            # 检查内容部分是否为空或过短
            if not content_part or len(content_part) < 10:
                return False
            
            # 对于某些协议，可以进一步解析验证
            if protocol_part in ['vmess', 'vless', 'trojan']:
                # 尝试解码内容，检查是否包含必要信息
                try:
                    # 处理可能的填充问题
                    missing_padding = len(content_part) % 4
                    if missing_padding:
                        content_part += '=' * (4 - missing_padding)
                    
                    # Base64解码
                    decoded = base64.b64decode(content_part).decode('utf-8', errors='ignore')
                    
                    # 对于vmess和vless，通常是JSON格式
                    if protocol_part in ['vmess', 'vless']:
                        try:
                            json.loads(decoded)
                            return True
                        except json.JSONDecodeError:
                            return False
                    return True
                except:
                    return False
            
            return True
        except:
            return False
    
    def _check_node_connectivity(self, node):
        """简单检查节点连通性（简化版实现）"""
        try:
            # 这里是简化实现，实际应根据不同协议实现相应的连通性测试
            # 提取服务器地址和端口（如果可能）
            protocol_part, content_part = node.split('://', 1)
            
            # 对于HTTP/Socks等简单协议，可以尝试建立TCP连接
            if protocol_part in ['http', 'https', 'socks', 'socks5']:
                try:
                    # 解析URL获取地址和端口
                    parsed = urlparse(node)
                    host = parsed.netloc.split(':')[0]
                    port = int(parsed.netloc.split(':')[1]) if ':' in parsed.netloc else 80
                    
                    # 尝试建立TCP连接
                    import socket
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(self.connectivity_timeout)
                    sock.connect((host, port))
                    sock.close()
                    return True
                except:
                    return False
            
            # 对于其他协议，我们暂时跳过详细的连通性测试
            # 在实际应用中，这里应该为每种协议实现特定的连通性测试
            return True
        except:
            return False
    
    def merge_nodes(self):
        """合并所有节点源，增强去重和过滤功能"""
        all_nodes = []
        unique_nodes = set()
        # 添加基于关键属性的去重字典
        key_attributes = {}
        
        # 获取所有节点源
        sources = self.config.get("SOURCES", [])
        if not sources:
            logging.error("没有配置节点源")
            return []
        
        logging.info(f"开始合并 {len(sources)} 个节点源")
        
        # 并发获取节点
        try:
            with ThreadPoolExecutor(max_workers=self.workers) as executor:
                results = list(executor.map(self.fetch_nodes, sources))
            
            # 合并所有节点并去重
            for nodes in results:
                for node in nodes:
                    # 首先进行基本字符串去重
                    if node not in unique_nodes:
                        # 尝试基于节点关键属性进行智能去重
                        node_key = self._get_node_key(node)
                        if node_key and node_key not in key_attributes:
                            key_attributes[node_key] = node
                            unique_nodes.add(node)
                            all_nodes.append(node)
                        elif not node_key:
                            # 如果无法提取关键属性，则使用字符串去重
                            unique_nodes.add(node)
                            all_nodes.append(node)
            
            logging.info(f"节点合并完成，共获取 {len(all_nodes)} 个唯一节点")
        except Exception as e:
            logging.error(f"合并节点时发生错误: {str(e)}")
            # 尝试串行获取作为备选方案
            all_nodes = self._fetch_nodes_serially(sources)
        
        # 对节点进行排序，优先保留优质节点
        all_nodes = self._sort_nodes_by_quality(all_nodes)
        
        return all_nodes
    
    def _get_node_key(self, node):
        """提取节点的关键属性，用于智能去重"""
        try:
            protocol_part, content_part = node.split('://', 1)
            
            # 尝试解析不同协议的关键属性
            if protocol_part in ['vmess', 'vless']:
                try:
                    # 处理填充问题
                    missing_padding = len(content_part) % 4
                    if missing_padding:
                        content_part += '=' * (4 - missing_padding)
                    
                    # Base64解码
                    decoded = base64.b64decode(content_part).decode('utf-8')
                    node_info = json.loads(decoded)
                    
                    # 使用地址和端口作为关键属性
                    if 'add' in node_info and 'port' in node_info:
                        return f"{protocol_part}:{node_info['add']}:{node_info['port']}"
                except:
                    pass
            elif protocol_part in ['trojan', 'shadowsocks', 'ss', 'ssr']:
                # 对于这些协议，尝试提取服务器地址和端口
                try:
                    # 这里是简化实现，实际应根据协议规范解析
                    # 假设格式为: 协议://用户名@地址:端口 或 协议://编码后的信息
                    if '@' in content_part and ':' in content_part.split('@')[1]:
                        server_info = content_part.split('@')[1].split('#')[0]
                        if ':' in server_info:
                            host, port = server_info.split(':', 1)
                            port = port.split('?')[0]  # 移除可能的参数
                            return f"{protocol_part}:{host}:{port}"
                except:
                    pass
            
            # 如果无法提取关键属性，返回None
            return None
        except:
            return None
    
    def _sort_nodes_by_quality(self, nodes):
        """根据节点质量对节点进行排序"""
        # 简化版：优先保留某些协议的节点
        # 在实际应用中，这里应该基于连通性测试结果、响应时间等进行排序
        protocol_priority = {
            'vless': 10, 'vmess': 9, 'trojan': 8, 'shadowsocks': 7,
            'ss': 7, 'hysteria': 6, 'hysteria2': 6, 'tuic': 5,
            'socks': 4, 'http': 3, 'https': 3
        }
        
        def get_priority(node):
            try:
                protocol = node.split('://')[0].lower()
                return protocol_priority.get(protocol, 2)
            except:
                return 1
        
        # 按优先级降序排序
        return sorted(nodes, key=get_priority, reverse=True)
    
    def _try_decode_base64(self, content):
        """尝试解码Base64内容"""
        try:
            # 尝试直接解码
            return base64.b64decode(content).decode('utf-8')
        except:
            try:
                # 尝试添加填充后解码
                missing_padding = len(content) % 4
                if missing_padding:
                    content += '=' * (4 - missing_padding)
                return base64.b64decode(content).decode('utf-8')
            except:
                logging.debug("内容不是有效的Base64格式")
                return None
    
    def _fetch_nodes_serially(self, sources):
        """串行获取节点，作为并发失败的备选方案"""
        all_nodes = []
        unique_nodes = set()
        
        logging.info("尝试串行获取节点源")
        for url in sources:
            nodes = self.fetch_nodes(url)
            for node in nodes:
                if node not in unique_nodes:
                    unique_nodes.add(node)
                    all_nodes.append(node)
        
        logging.info(f"串行获取完成，共获取 {len(all_nodes)} 个唯一节点")
        return all_nodes
    
    # 找到 generate_subscription_file 方法并修改
    def generate_subscription_file(self, nodes, output_file):
        """生成订阅文件"""
        try:
            if not nodes:
                logging.warning(f"没有节点可生成订阅: {output_file}")
                return None
            
            logging.info(f"准备生成订阅文件: {output_file}，包含{len(nodes)}个节点")
            
            # 将节点列表转换为字符串并编码，使用\r\n作为行分隔符以兼容v2ray
            nodes_text = '\r\n'.join(nodes)
            subscription_content = base64.b64encode(nodes_text.encode('utf-8')).decode('utf-8')
            
            # 保存到文件
            try:
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(subscription_content)
                
                # 验证文件是否成功创建
                if os.path.exists(output_file):
                    file_size = os.path.getsize(output_file)
                    if file_size > 0:
                        logging.info(f"订阅已生成: {output_file}，大小: {file_size}字节")
                    else:
                        logging.warning(f"订阅文件为空: {output_file}")
                else:
                    logging.error(f"订阅文件创建失败: {output_file}")
                
                return subscription_content
            except Exception as file_err:
                logging.error(f"写入文件失败: {str(file_err)}")
                return None
        except Exception as e:
            logging.error(f"生成订阅文件时发生未预期错误: {str(e)}")
            return None