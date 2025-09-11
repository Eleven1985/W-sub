#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
w-sub - 节点订阅汇总工具
功能：
1. 从指定URL获取节点配置
2. 合并多个源的节点
3. 识别节点国家归属地并添加国家简称
4. 生成一个订阅文件：包含所有节点
5. 按国家归属地生成单独的订阅文件
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

# 国家代码映射（常用国家和地区）
COUNTRY_CODE_MAP = {
    'jp': 'JP',  # 日本
    'japan': 'JP',
    'us': 'US',  # 美国
    'united states': 'US',
    'sg': 'SG',  # 新加坡
    'singapore': 'SG',
    'hk': 'HK',  # 香港
    'hong kong': 'HK',
    'tw': 'TW',  # 台湾
    'taiwan': 'TW',
    'kr': 'KR',  # 韩国
    'korea': 'KR',
    'de': 'DE',  # 德国
    'germany': 'DE',
    'uk': 'UK',  # 英国
    'united kingdom': 'UK',
    'ca': 'CA',  # 加拿大
    'canada': 'CA',
    'au': 'AU',  # 澳大利亚
    'australia': 'AU',
    'fr': 'FR',  # 法国
    'france': 'FR',
    'nl': 'NL',  # 荷兰
    'netherlands': 'NL',
    'ru': 'RU',  # 俄罗斯
    'russia': 'RU',
    'in': 'IN',  # 印度
    'india': 'IN',
    'th': 'TH',  # 泰国
    'thailand': 'TH',
    'vn': 'VN',  # 越南
    'vietnam': 'VN',
    'id': 'ID',  # 印度尼西亚
    'indonesia': 'ID'
}

# 常用数据中心/云服务提供商识别
DATA_CENTER_KEYWORDS = {
    'aws': ['amazon', 'aws', 'ec2'],
    'azure': ['azure', 'microsoft'],
    'gcp': ['google', 'gcp', 'compute'],
    'alibaba': ['aliyun', 'alibaba', 'alicloud'],
    'tencent': ['tencent', 'qcloud'],
    'baidu': ['baidu', 'bce'],
    'digitalocean': ['digitalocean', 'do'],
    'linode': ['linode']
}

class ConfigLoader:
    """配置加载器，从配置文件读取设置"""
    @staticmethod
    def load_config(config_file="config.txt"):
        config = {
            "SOURCES": [],
            "TIMEOUT": 5,
            "OUTPUT_ALL_FILE": "subscription_all.txt",
            "WORKERS": 10,
            "MAX_RETRY": 2,  # 获取节点源的重试次数
            "USE_COUNTRY_CODE": True,  # 是否使用国家代码
            "APPEND_PROVIDER": True,  # 是否添加云服务商信息
            "GENERATE_COUNTRY_FILES": True,  # 是否按国家生成文件
            "MIN_NODES_PER_COUNTRY": 5  # 每个国家文件的最小节点数
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
                            if key in ["TIMEOUT", "WORKERS", "MAX_RETRY", "MIN_NODES_PER_COUNTRY"]:
                                try:
                                    config[key] = int(value)
                                except ValueError:
                                    logger.warning(f"配置项 {key} 的值 {value} 不是有效的数字，使用默认值 {config[key]}")
                            elif key in ["USE_COUNTRY_CODE", "APPEND_PROVIDER", "GENERATE_COUNTRY_FILES"]:
                                config[key] = value.lower() in ('true', 'yes', '1')
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
        self.valid_nodes_count = 0
        self.failed_nodes_count = 0
        self.debug_info = []
        self.nodes_by_country = {}
    
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
                return "Unknown", "Unknown", node
            
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
                        # 尝试从ps字段获取节点名称
                        ps = vmess_data.get('ps', '').strip()
                        return node_type, server_info, ps if ps else address
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
                
                return node_type, address, address
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
                
                return node_type, address, address
        except Exception as e:
            logger.error(f"解析节点信息时发生错误: {str(e)}")
            return "Unknown", "Unknown", node
    
    def _identify_country(self, address):
        """根据节点地址识别国家"""
        if not address or address == "Unknown":
            return ""
        
        # 转为小写进行匹配
        address_lower = address.lower()
        
        # 检查域名中的国家代码顶级域名
        tld_pattern = r'\.([a-z]{2})$'
        tld_match = re.search(tld_pattern, address_lower)
        if tld_match:
            tld = tld_match.group(1)
            if tld in COUNTRY_CODE_MAP:
                return COUNTRY_CODE_MAP[tld]
            # 直接返回可能的国家代码（如果是2个字母）
            if len(tld) == 2:
                return tld.upper()
        
        # 检查域名或描述中的国家关键词
        for country, code in COUNTRY_CODE_MAP.items():
            if country in address_lower:
                return code
        
        # 检查是否为云服务提供商的地址
        provider = self._identify_provider(address_lower)
        if provider and self.config["APPEND_PROVIDER"]:
            return provider
        
        return ""
    
    def _identify_provider(self, address):
        """识别云服务提供商"""
        for provider, keywords in DATA_CENTER_KEYWORDS.items():
            for keyword in keywords:
                if keyword in address:
                    return provider.upper()[:3]  # 取前3个字母作为标识
        return ""
    
    def _update_node_name_with_country(self, node):
        """更新节点名称，添加国家代码"""
        if not self.config["USE_COUNTRY_CODE"]:
            return node
        
        try:
            node_type, address, node_name = self._parse_node_info(node)
            country_code = self._identify_country(address)
            
            # 如果已经包含国家代码，不再添加
            if country_code and not re.search(rf'\b{country_code}\b', node_name):
                # 尝试更新vmess节点的名称
                if node_type == 'vmess' and node.startswith('vmess://'):
                    encoded_part = node[len('vmess://'):]
                    # 处理可能的URL编码
                    encoded_part = encoded_part.replace('-', '+').replace('_', '/')
                    # 补全base64填充
                    padding_needed = 4 - (len(encoded_part) % 4)
                    if padding_needed < 4:
                        encoded_part += '=' * padding_needed
                    
                    try:
                        decoded = base64.b64decode(encoded_part).decode('utf-8')
                        vmess_data = json.loads(decoded)
                        # 更新ps字段，添加国家代码
                        if 'ps' in vmess_data:
                            if not re.search(rf'\b{country_code}\b', vmess_data['ps']):
                                vmess_data['ps'] = f"[{country_code}] {vmess_data['ps']}"
                        else:
                            vmess_data['ps'] = f"[{country_code}] {address}"
                        # 重新编码
                        updated_json = json.dumps(vmess_data, ensure_ascii=False)
                        updated_encoded = base64.b64encode(updated_json.encode('utf-8')).decode('utf-8')
                        # 替换base64中的+和/，去掉padding
                        updated_encoded = updated_encoded.replace('+', '-').replace('/', '_').rstrip('=')
                        return f'vmess://{updated_encoded}'
                    except:
                        pass
                
                # 对于其他类型节点，我们无法直接修改名称，保持原样
                logger.debug(f"无法更新节点名称: {node_type} 类型节点")
        except Exception as e:
            logger.error(f"更新节点名称时发生错误: {str(e)}")
        
        return node
    
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
        
        # 更新节点名称，添加国家代码
        if self.config["USE_COUNTRY_CODE"]:
            logger.info("正在更新节点名称，添加国家代码...")
            updated_nodes = []
            for node in self.nodes:
                updated_node = self._update_node_name_with_country(node)
                updated_nodes.append(updated_node)
            self.nodes = updated_nodes
            logger.info("节点名称更新完成")
    
    def group_nodes_by_country(self):
        """按国家分组节点"""
        logger.info("正在按国家分组节点...")
        self.nodes_by_country = {}
        unknown_country_count = 0
        
        for node in self.nodes:
            try:
                _, address, _ = self._parse_node_info(node)
                country_code = self._identify_country(address)
                
                if country_code:
                    if country_code not in self.nodes_by_country:
                        self.nodes_by_country[country_code] = []
                    self.nodes_by_country[country_code].append(node)
                else:
                    unknown_country_count += 1
            except Exception as e:
                logger.error(f"处理节点时发生错误: {str(e)}")
                unknown_country_count += 1
        
        logger.info(f"按国家分组完成，共识别到{len(self.nodes_by_country)}个国家/地区，{unknown_country_count}个节点无法识别国家")
        return self.nodes_by_country
    
    def generate_country_subscriptions(self):
        """生成各个国家的订阅文件"""
        if not self.config["GENERATE_COUNTRY_FILES"]:
            logger.info("未启用按国家生成文件功能，跳过此步骤")
            return
        
        # 按国家分组节点
        if not self.nodes_by_country:
            self.group_nodes_by_country()
        
        # 确保国家文件夹存在
        country_files_dir = "country_files"
        if not os.path.exists(country_files_dir):
            os.makedirs(country_files_dir)
        
        # 为每个国家生成订阅文件
        generated_files = []
        for country_code, country_nodes in self.nodes_by_country.items():
            # 跳过节点数不足的国家
            if len(country_nodes) < self.config["MIN_NODES_PER_COUNTRY"]:
                logger.info(f"国家 {country_code} 的节点数不足 {self.config['MIN_NODES_PER_COUNTRY']} 个，跳过生成文件")
                continue
            
            # 生成文件名
            output_file = os.path.join(country_files_dir, f"{country_code}.txt")
            
            # 生成订阅文件
            self.generate_subscription(country_nodes, output_file)
            generated_files.append((country_code, output_file, len(country_nodes)))
        
        logger.info(f"已生成{len(generated_files)}个国家/地区的订阅文件")
        for country_code, file_path, node_count in generated_files:
            logger.info(f"  - {country_code}: {file_path} ({node_count}个节点)")
        
        return generated_files
    
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
    
    # 生成按国家分类的订阅文件
    processor.generate_country_subscriptions()
    
    logger.info("处理完成！")

if __name__ == "__main__":
    main()