# -*- coding: utf-8 -*-
import re
import base64
import logging
import requests
from concurrent.futures import ThreadPoolExecutor

class NodeFetcher:
    """节点获取器，负责从URL获取节点信息"""
    
    def __init__(self, config):
        self.config = config
        self.timeout = config.get("TIMEOUT", 5)
        self.max_retry = config.get("MAX_RETRY", 2)
    
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
        """从内容中提取节点信息"""
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
            # 添加更多节点格式支持
            if re.match(r'^(vmess|v2ray|trojan|trojan-go|shadowsocks|shadowsocksr|vless|ss|ssr|hysteria|tuic|naiveproxy|socks5|http|https|wireguard|sing-box|clash|xray)://', line):
                nodes.append(line)
        
        return nodes
    
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