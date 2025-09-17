# -*- coding: utf-8 -*-
import re
import base64
import logging
import requests
import os
import time
from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict

class NodeProcessor:
    """节点处理器，整合节点获取和合并功能"""
    
    # 预编译正则表达式以提高效率
    NODE_PATTERN = re.compile(r'^(vmess|v2ray|trojan|trojan-go|shadowsocks|shadowsocksr|vless|ss|ssr|hysteria|hysteria2|tuic|wireguard|naiveproxy|socks|http|https|clash|shadowsocks2|vmess\+tls|vless\+tls)://')
    URL_PATTERN = re.compile(r'^https?://')
    
    # 协议特定的正则表达式，用于提取更精确的节点标识
    VMESS_PATTERN = re.compile(r'server":"([^"]+)".*?port":(\d+)')
    VLESS_PATTERN = re.compile(r'@([^:]+):(\d+)')
    TROJAN_PATTERN = re.compile(r'@([^:]+):(\d+)')
    
    def __init__(self, config):
        self.config = config
        self.timeout = config.get("TIMEOUT", 5)
        self.max_retry = config.get("MAX_RETRY", 2)
        self.workers = min(config.get("WORKERS", 10), 20)  # 限制最大并发数，避免资源浪费
        self._node_id_cache = set()  # 用于高效去重的节点标识缓存
        self._protocol_stats = defaultdict(int)  # 统计各协议节点数量
    
    def fetch_nodes(self, url):
        """从指定URL获取节点列表"""
        nodes = []
        retry_count = 0
        
        while retry_count <= self.max_retry:
            try:
                # 使用会话对象提高连接复用效率
                with requests.Session() as session:
                    session.headers.update({
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                    })
                    logging.info(f"正在获取节点源: {url} (尝试 {retry_count + 1}/{self.max_retry + 1})")
                    response = session.get(url, timeout=self.timeout)
                    response.raise_for_status()
                    
                    # 尝试解码响应内容
                    content = response.text.strip()
                    if content:
                        extracted_nodes = self._extract_nodes(content)
                        # 对获取到的节点进行初步去重和筛选
                        valid_nodes = self._filter_invalid_nodes(extracted_nodes)
                        
                        if valid_nodes:
                            nodes = valid_nodes
                            logging.info(f"成功从 {url} 获取 {len(nodes)} 个有效节点")
                            break
                        else:
                            logging.warning(f"从 {url} 获取内容，但未能提取到有效节点")
                    else:
                        logging.warning(f"从 {url} 获取的内容为空")
            except requests.RequestException as e:
                logging.error(f"获取节点源 {url} 失败: {str(e)}")
            except Exception as e:
                logging.error(f"处理节点源 {url} 时发生未预期错误: {str(e)}")
            
            retry_count += 1
            if retry_count <= self.max_retry:
                logging.info(f"将在重试 {url}")
                time.sleep(1)  # 添加短暂延迟避免请求过于频繁
        
        return nodes
    
    def _extract_nodes(self, content):
        """从内容中提取节点信息"""
        nodes = []
        
        # 首先尝试解码Base64，提高节点提取效率
        decoded_content = self._try_decode_base64(content)
        if decoded_content:
            content = decoded_content
        
        # 优化按行处理逻辑，避免不必要的操作
        for line in content.split('\n'):
            stripped_line = line.strip()
            if stripped_line and self.NODE_PATTERN.match(stripped_line):
                nodes.append(stripped_line)
        
        return nodes
    
    def _try_decode_base64(self, content):
        """尝试解码Base64内容"""
        try:
            # 快速检查是否可能是Base64格式
            if not all(c.isalnum() or c in '+/=' for c in content):
                return None
            
            # 尝试直接解码或添加填充后解码
            try:
                return base64.b64decode(content).decode('utf-8')
            except:
                # 尝试添加填充后解码
                missing_padding = len(content) % 4
                if missing_padding:
                    content += '=' * (4 - missing_padding)
                return base64.b64decode(content).decode('utf-8')
        except:
            logging.debug("内容不是有效的Base64格式")
            return None
    
    def _extract_node_identifier(self, node):
        """提取节点的唯一标识符，用于更精确的去重"""
        try:
            # 协议特定的节点标识提取，提高去重精度
            if node.startswith('vmess://'):
                data = node.split('://')[1]
                try:
                    decoded = base64.b64decode(data + '=' * (4 - len(data) % 4)).decode('utf-8', errors='ignore')
                    match = self.VMESS_PATTERN.search(decoded)
                    if match:
                        return f"vmess:{match.group(1)}:{match.group(2)}"
                except:
                    pass
            elif node.startswith('vless://'):
                data = node.split('://')[1]
                match = self.VLESS_PATTERN.search(data)
                if match:
                    return f"vless:{match.group(1)}:{match.group(2)}"
            elif node.startswith('trojan://'):
                data = node.split('://')[1]
                match = self.TROJAN_PATTERN.search(data)
                if match:
                    return f"trojan:{match.group(1)}:{match.group(2)}"
            # 对于其他协议，使用简化但仍有效的提取方式
            # 提取协议和服务器部分作为标识
            protocol_end = node.find('://')
            if protocol_end > 0:
                protocol = node[:protocol_end]
                server_part = node[protocol_end+3:].split('#')[0].split('?')[0].split('/')[0]
                return f"{protocol}:{server_part[:100]}"  # 限制长度以平衡性能和精确度
            
            # 作为最后的备选方案
            return node[:200]  # 截取部分作为标识
        except:
            return node[:200]  # 发生错误时返回原始节点的前200个字符
    
    def _filter_invalid_nodes(self, nodes):
        """过滤无效节点，提高节点质量"""
        if not nodes:
            return []
            
        valid_nodes = []
        unique_ids = set()
        
        for node in nodes:
            # 提取节点唯一标识
            node_id = self._extract_node_identifier(node)
            
            # 检查是否已存在相同标识的节点
            if node_id not in unique_ids and node_id not in self._node_id_cache:
                unique_ids.add(node_id)
                self._node_id_cache.add(node_id)
                valid_nodes.append(node)
                
                # 统计协议类型
                protocol_end = node.find('://')
                if protocol_end > 0:
                    protocol = node[:protocol_end]
                    self._protocol_stats[protocol] += 1
        
        return valid_nodes
    
    def merge_nodes(self):
        """合并所有节点源"""
        all_nodes = []
        
        # 获取所有节点源
        sources = self.config.get("SOURCES", [])
        if not sources:
            logging.error("没有配置节点源")
            return []
        
        # 过滤无效的源URL并去重
        valid_sources = list(dict.fromkeys([url for url in sources if self.URL_PATTERN.match(url)]))
        if len(valid_sources) < len(sources):
            logging.warning(f"过滤了 {len(sources) - len(valid_sources)} 个无效或重复的源URL")
            sources = valid_sources
        
        source_count = len(sources)
        if source_count == 0:
            logging.error("没有有效的节点源")
            return []
        
        logging.info(f"开始合并 {source_count} 个节点源")
        
        # 根据源的数量动态调整并发数
        adaptive_workers = min(source_count, self.workers)
        
        # 并发获取节点
        try:
            with ThreadPoolExecutor(max_workers=adaptive_workers) as executor:
                # 使用列表推导式替代extend操作
                all_nodes = [node for result in executor.map(self.fetch_nodes, sources) for node in result]
            
            # 记录协议统计信息
            if self._protocol_stats:
                stats_str = ", ".join([f"{proto}: {count}" for proto, count in self._protocol_stats.items()])
                logging.info(f"节点协议分布: {stats_str}")
            
            logging.info(f"节点合并完成，共获取 {len(all_nodes)} 个唯一有效节点")
        except Exception as e:
            logging.error(f"合并节点时发生错误: {str(e)}")
            # 尝试串行获取作为备选方案
            all_nodes = self._fetch_nodes_serially(sources)
        
        return all_nodes
    
    def _fetch_nodes_serially(self, sources):
        """串行获取节点，作为并发失败的备选方案"""
        all_nodes = []
        
        logging.info("尝试串行获取节点源")
        for url in sources:
            nodes = self.fetch_nodes(url)
            all_nodes.extend(nodes)
            time.sleep(0.5)  # 添加短暂延迟
        
        logging.info(f"串行获取完成，共获取 {len(all_nodes)} 个唯一有效节点")
        return all_nodes
    
    def generate_subscription_file(self, nodes, output_file):
        """生成订阅文件"""
        try:
            if not nodes:
                logging.warning(f"没有节点可生成订阅: {output_file}")
                return None
            
            logging.info(f"准备生成订阅文件: {output_file}，包含{len(nodes)}个节点")
            
            # 将节点列表转换为字符串并编码
            nodes_text = '\n'.join(nodes)
            subscription_content = base64.b64encode(nodes_text.encode('utf-8')).decode('utf-8')
            
            # 确保目录存在并写入文件
            os.makedirs(os.path.dirname(output_file), exist_ok=True)
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
        except Exception as e:
            logging.error(f"生成订阅文件时发生错误: {str(e)}")
            return None