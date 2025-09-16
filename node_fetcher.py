# -*- coding: utf-8 -*-
"""
node_fetcher - 节点获取模块
功能：从指定URL获取节点配置，支持Base64解码和节点提取
"""
import os
import re
import time
import base64
import logging
import requests

# 配置日志
logger = logging.getLogger(__name__)

class NodeFetcher:
    """节点获取器，负责从URL获取节点配置"""
    def __init__(self, config):
        self.config = config
        # 确保配置中有必要的键
        if not self.config:
            self.config = {}
        
    def fetch_nodes(self, url):
        """从指定URL获取节点配置"""
        retry_count = 0
        nodes = []
        
        # 验证URL是否有效
        if not url or not isinstance(url, str) or not url.startswith(('http://', 'https://')):
            logger.error(f"无效的URL: {url}")
            return nodes
        
        max_retry = self.config.get('MAX_RETRY', 2)
        timeout = self.config.get('TIMEOUT', 5)
        
        while retry_count <= max_retry:
            try:
                logger.info(f"正在获取节点源: {url} (尝试 {retry_count+1}/{max_retry+1})")
                response = requests.get(url, timeout=timeout)
                response.encoding = 'utf-8'
                
                if response.status_code == 200:
                    content = response.text
                    
                    # 尝试解码base64内容
                    decoded_content = self._try_decode_base64(content)
                    
                    # 提取节点
                    new_nodes = self._extract_nodes(decoded_content)
                    logger.info(f"从{url}获取到{len(new_nodes)}个节点")
                    nodes = new_nodes
                    break  # 成功获取后退出重试循环
                else:
                    logger.warning(f"获取{url}失败，状态码: {response.status_code}")
            except requests.exceptions.RequestException as e:
                logger.error(f"获取{url}时发生网络错误: {str(e)}")
            except Exception as e:
                logger.error(f"获取{url}时发生未知错误: {str(e)}")
            
            retry_count += 1
            if retry_count <= max_retry:
                logger.info(f"{url} 获取失败，{timeout}秒后重试...")
                time.sleep(timeout)
        
        return nodes
    
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
        logger.info(f"从内容中提取并去重后，得到{len(unique_nodes)}个节点 (原始提取: {len(nodes)})个节点")
        return unique_nodes