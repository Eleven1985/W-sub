#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
w-sub - 节点订阅汇总工具
功能：
1. 从指定URL获取节点配置
2. 合并多个源的节点
3. 生成一个订阅文件：包含所有节点
4. 支持按国家筛选节点（可选）
5. 支持按国家生成单独的订阅文件（可选）
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
            "WORKERS": 10,
            "MAX_RETRY": 2,  # 获取节点源的重试次数
            "USE_COUNTRY_CODE": False,
            "GENERATE_COUNTRY_FILES": False,
            "MIN_NODES_PER_COUNTRY": 5
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
                            elif key in ["USE_COUNTRY_CODE", "GENERATE_COUNTRY_FILES"]:
                                # 转换布尔值
                                config[key] = value.lower() == 'true'
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
            
            # 尝试多种可能的解码方式
            # 1. 直接尝试解码
            try:
                decoded = base64.b64decode(cleaned_content, validate=True).decode('utf-8', errors='ignore')
                if any(char in decoded for char in ['vmess://', 'v2ray://', 'trojan://', 'shadowsocks://', 'vless://']):
                    logger.info("成功解码base64内容")
                    return decoded
            except:
                pass
            
            # 2. 尝试不同的填充方式
            for padding in ['', '=', '==']:
                try:
                    padded_content = cleaned_content + padding
                    decoded = base64.b64decode(padded_content).decode('utf-8', errors='ignore')
                    if any(char in decoded for char in ['vmess://', 'v2ray://', 'trojan://', 'shadowsocks://', 'vless://']):
                        logger.info("成功解码base64内容(使用填充)")
                        return decoded
                except:
                    continue
            
            # 3. 尝试每4个字符一组进行解码
            for i in range(4):
                try:
                    adjusted_content = cleaned_content[i:]
                    decoded = base64.b64decode(adjusted_content).decode('utf-8', errors='ignore')
                    if any(char in decoded for char in ['vmess://', 'v2ray://', 'trojan://', 'shadowsocks://', 'vless://']):
                        logger.info(f"成功解码base64内容(偏移{i})")
                        return decoded
                except:
                    continue
        except Exception as e:
            logger.error(f"解码base64内容时发生错误: {str(e)}")
        
        # 解码失败，返回原始内容
        return content
    
    def _extract_nodes(self, content):
        """从内容中提取节点链接"""
        # 支持的节点类型正则表达式，增加了vless等新型节点类型
        patterns = [
            r'(vmess://[^\s]+)',
            r'(v2ray://[^\s]+)',
            r'(trojan://[^\s]+)',
            r'(shadowsocks://[^\s]+)',
            r'(shadowsocksr://[^\s]+)',
            r'(vless://[^\s]+)',
            r'(ss://[^\s]+)',
            r'(ssr://[^\s]+)',
            r'(trojan-go://[^\s]+)'
        ]
        
        nodes = []
        for pattern in patterns:
            matches = re.findall(pattern, content, re.MULTILINE)
            nodes.extend(matches)
        
        # 去重
        unique_nodes = list(set(nodes))
        logger.info(f"从内容中提取并去重后，得到{len(unique_nodes)}个节点")
        return unique_nodes
    
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
        
        # 如果需要按国家分组，则处理节点
        if self.config["USE_COUNTRY_CODE"] or self.config["GENERATE_COUNTRY_FILES"]:
            self._group_nodes_by_country()
    
    def _group_nodes_by_country(self):
        """按国家代码对节点进行分组"""
        # 简单的国家代码识别（实际应用中可能需要更复杂的解析）
        country_pattern = re.compile(r'#([A-Z]{2})')
        
        for node in self.nodes:
            # 尝试从节点名称中提取国家代码
            match = country_pattern.search(node)
            if match:
                country_code = match.group(1)
                if country_code not in self.nodes_by_country:
                    self.nodes_by_country[country_code] = []
                self.nodes_by_country[country_code].append(node)
        
        logger.info(f"按国家代码分组后，得到{len(self.nodes_by_country)}个国家/地区的节点")
    
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
    
    def generate_country_subscriptions(self):
        """按国家生成单独的订阅文件"""
        if not self.config["GENERATE_COUNTRY_FILES"]:
            return
        
        output_dir = "country_subscriptions"
        os.makedirs(output_dir, exist_ok=True)
        
        for country_code, nodes in self.nodes_by_country.items():
            if len(nodes) >= self.config["MIN_NODES_PER_COUNTRY"]:
                output_file = os.path.join(output_dir, f"subscription_{country_code}.txt")
                self.generate_subscription(nodes, output_file)




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
    
    # 如果配置了按国家生成文件，则执行
    processor.generate_country_subscriptions()
    
    logger.info("处理完成！")

if __name__ == "__main__":
    main()