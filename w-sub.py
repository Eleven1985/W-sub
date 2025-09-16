#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
w-sub - 节点订阅汇总工具
功能：
1. 从指定URL获取节点配置
2. 合并多个源的节点
3. 生成包含所有节点的订阅文件
4. 支持按节点类型分类生成订阅文件
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
import shutil

# 导入节点优选工具
from node_selector import NodeSelector

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
    # 修改ConfigLoader类的load_config方法
    @staticmethod
    def load_config(config_file=None):
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
        
        # 默认节点源列表（确保即使找不到配置文件也能工作）
        DEFAULT_SOURCES = [
            "https://raw.githubusercontent.com/ebrasha/free-v2ray-public-list/refs/heads/main/V2Ray-Config-By-EbraSha.txt",
            "https://raw.githubusercontent.com/roosterkid/openproxylist/refs/heads/main/V2RAY_RAW.txt",
            "https://raw.githubusercontent.com/Awmiroosen/awmirx-v2ray/refs/heads/main/blob/main/v2-sub.txt",
            "https://raw.githubusercontent.com/Flikify/Free-Node/refs/heads/main/v2ray.txt",
            "https://raw.githubusercontent.com/ggborr/FREEE-VPN/refs/heads/main/8V2",
            "https://raw.githubusercontent.com/Rayan-Config/C-Sub/refs/heads/main/configs/proxy.txt",
            "https://raw.githubusercontent.com/xiaoji235/airport-free/refs/heads/main/v2ray.txt",
            "https://raw.githubusercontent.com/arshiacomplus/v2rayExtractor/refs/heads/main/mix/sub.html",
            "https://raw.githubusercontent.com/MahsaNetConfigTopic/config/refs/heads/main/xray_final.txt",
            "https://raw.githubusercontent.com/Mhdiqpzx/Mahdi-VIP/refs/heads/main/Mahdi-Vip.txt",
            "https://raw.githubusercontent.com/sinavm/SVM/refs/heads/main/subscriptions/xray/base64/vless",
            "https://raw.githubusercontent.com/Joker-funland/V2ray-configs/refs/heads/main/vless.txt",
            "https://raw.githubusercontent.com/itsyebekhe/PSG/refs/heads/main/subscriptions/xray/base64/vless",
            "https://raw.githubusercontent.com/SonzaiEkkusu/V2RayDumper/refs/heads/main/config.txt"
        ]
        
        # 首先尝试从配置文件加载
        config_loaded = False
        
        # 尝试多个可能的配置文件路径
        possible_paths = []
        if config_file:
            possible_paths.append(config_file)
        
        # 添加当前目录和configs子目录的可能路径
        possible_paths.extend([
            "config.txt",
            "configs/config.txt",
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.txt"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "configs", "config.txt")
        ])
        
        # 尝试所有可能的路径
        for path in possible_paths:
            try:
                with open(path, 'r', encoding='utf-8') as f:
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
                        # 简化格式：直接识别URL
                        elif re.match(r'^https?://', line):
                            config["SOURCES"].append(line)
                    
                    logger.info(f"成功加载配置文件: {path}")
                    config_loaded = True
                    break  # 找到并加载了配置文件，退出循环
            except Exception as e:
                logger.debug(f"尝试加载配置文件 {path} 失败: {str(e)}")
        
        # 如果没有加载到配置文件，使用默认节点源
        if not config_loaded:
            logger.warning("未能从配置文件加载节点源，将使用内置默认节点源")
            config["SOURCES"] = DEFAULT_SOURCES.copy()
        
        # 确保至少有节点源可用
        if not config["SOURCES"]:
            logger.warning("配置文件中没有有效的节点源，将使用内置默认节点源")
            config["SOURCES"] = DEFAULT_SOURCES.copy()
        
        logger.info(f"成功加载配置，共 {len(config['SOURCES'])} 个节点源")
        return config

class NodeProcessor:
    def __init__(self, config, output_dir=None):
        self.config = config
        self.nodes = []
        self.valid_nodes_count = 0
        self.failed_nodes_count = 0
        self.debug_info = []
        # 设置输出目录，默认在当前目录下创建subscriptions文件夹
        self.output_dir = output_dir or "subscriptions"
        # 确保输出目录存在
        self._ensure_output_dir()
    
    def _ensure_output_dir(self):
        """确保输出目录存在"""
        if not os.path.exists(self.output_dir):
            try:
                os.makedirs(self.output_dir)
                logger.info(f"已创建输出目录: {self.output_dir}")
            except Exception as e:
                logger.error(f"创建输出目录失败: {str(e)}")
                # 如果创建目录失败，使用当前目录
                self.output_dir = "."
                logger.warning(f"将使用当前目录作为输出目录")
    
    def _get_output_path(self, filename):
        """获取文件的完整输出路径"""
        return os.path.join(self.output_dir, filename)
    
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
    
    def generate_subscription(self, nodes, output_file):
        """生成订阅文件"""
        try:
            # 获取完整的输出路径
            full_output_path = self._get_output_path(output_file)
            logger.info(f"准备生成订阅文件: {full_output_path}，包含{len(nodes)}个节点")
            
            # 将节点列表转换为字符串
            nodes_text = '\n'.join(nodes)
            
            # Base64编码
            subscription_content = base64.b64encode(
                nodes_text.encode('utf-8')
            ).decode('utf-8')
            
            # 保存到文件
            with open(full_output_path, 'w', encoding='utf-8') as f:
                f.write(subscription_content)
            
            logger.info(f"订阅已生成并保存到 {full_output_path}，包含{len(nodes)}个节点")
            return subscription_content
        except Exception as e:
            logger.error(f"生成订阅文件{output_file}失败: {str(e)}")
            # 尝试创建空文件，确保文件存在
            try:
                full_output_path = self._get_output_path(output_file)
                with open(full_output_path, 'w', encoding='utf-8') as f:
                    f.write('')
                logger.warning(f"已创建空的{output_file}文件")
            except:
                pass
            return None

    def categorize_nodes_by_type(self):
        """按节点类型分类节点"""
        categorized_nodes = {
            'vmess': [],
            'v2ray': [],
            'trojan': [],
            'shadowsocks': [],
            'shadowsocksr': [],
            'vless': [],
            'ss': [],
            'ssr': [],
            'hysteria': [],
            'other': []  # 其他未分类的节点类型
        }
        
        for node in self.nodes:
            # 根据节点URL的前缀判断类型
            if node.startswith('vmess://'):
                categorized_nodes['vmess'].append(node)
            elif node.startswith('v2ray://'):
                categorized_nodes['v2ray'].append(node)
            elif node.startswith('trojan://') or node.startswith('trojan-go://'):
                categorized_nodes['trojan'].append(node)
            elif node.startswith('shadowsocks://'):
                categorized_nodes['shadowsocks'].append(node)
            elif node.startswith('shadowsocksr://'):
                categorized_nodes['shadowsocksr'].append(node)
            elif node.startswith('vless://'):
                categorized_nodes['vless'].append(node)
            elif node.startswith('ss://'):
                categorized_nodes['ss'].append(node)
            elif node.startswith('ssr://'):
                categorized_nodes['ssr'].append(node)
            elif node.startswith('hysteria://'):
                categorized_nodes['hysteria'].append(node)
            else:
                categorized_nodes['other'].append(node)
        
        # 记录分类结果
        for node_type, nodes_list in categorized_nodes.items():
            if node_type != 'other' or nodes_list:  # 只记录有节点的分类或非'other'分类
                logger.info(f"{node_type.upper()}类型节点数量: {len(nodes_list)}")
        
        return categorized_nodes
    
    def generate_category_subscriptions(self):
        """为每种节点类型生成订阅文件"""
        categorized_nodes = self.categorize_nodes_by_type()
        
        # 定义节点类型到文件名的映射
        type_to_filename = {
            'vmess': 'subscription_vmess.txt',
            'v2ray': 'subscription_v2ray.txt',
            'trojan': 'subscription_trojan.txt',
            'shadowsocks': 'subscription_shadowsocks.txt',
            'shadowsocksr': 'subscription_shadowsocksr.txt',
            'vless': 'subscription_vless.txt',
            'ss': 'subscription_ss.txt',
            'ssr': 'subscription_ssr.txt',
            'hysteria': 'subscription_hysteria.txt',
            'other': 'subscription_other.txt'
        }
        
        # 为每种类型生成订阅文件
        for node_type, nodes_list in categorized_nodes.items():
            if nodes_list:  # 只有当该类型有节点时才生成文件
                filename = type_to_filename[node_type]
                self.generate_subscription(nodes_list, filename)
        
        logger.info("所有节点类型的订阅文件已生成完成")

    def generate_best_nodes_subscription(self):
        """使用独立的NodeSelector生成最优节点订阅"""
        try:
            # 创建NodeSelector实例
            selector = NodeSelector(self.config)
            
            # 测试并选择最优节点
            best_nodes = selector.test_and_select_best_nodes(self.nodes)
            
            # 生成最优节点订阅文件
            output_path = self._get_output_path(self.config["OUTPUT_BEST_FILE"])
            result = selector.generate_best_subscription(best_nodes, output_path)
            
            # 双重保障：如果生成失败，再次尝试使用当前类的方法生成
            if result is None:
                logger.warning("使用NodeSelector生成最优节点订阅失败，尝试使用备用方法")
                self.generate_subscription(best_nodes, self.config["OUTPUT_BEST_FILE"])
            
            return best_nodes
        except Exception as e:
            logger.error(f"生成最优节点订阅时发生错误: {str(e)}")
            
            # 最后的尝试：强制创建文件
            try:
                output_path = self._get_output_path(self.config["OUTPUT_BEST_FILE"])
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(base64.b64encode('\n'.join(self.nodes).encode('utf-8')).decode('utf-8'))
                logger.info(f"已强制生成{self.config['OUTPUT_BEST_FILE']}文件")
            except Exception as inner_e:
                logger.error(f"强制生成文件失败: {str(inner_e)}")
            
            return self.nodes

def main():
    logger.info("=== w-sub 节点订阅汇总工具启动 ===")
    logger.info(f"当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 加载配置
    config = ConfigLoader.load_config()
    
    # 创建处理器实例，指定输出目录
    processor = NodeProcessor(config, "subscriptions_output")
    
    # 执行处理流程
    processor.merge_nodes()
    
    if not processor.nodes:
        logger.error("未能获取任何节点，请检查网络连接或源地址是否有效")
        return
    
    # 生成包含所有节点的订阅文件
    processor.generate_subscription(processor.nodes, config["OUTPUT_ALL_FILE"])
    
    # 生成最优节点订阅文件（使用独立的NodeSelector）
    processor.generate_best_nodes_subscription()
    
    # 按节点类型生成分类订阅文件
    processor.generate_category_subscriptions()
    
    logger.info(f"=== w-sub 节点订阅汇总工具运行完成 ===")
    logger.info(f"所有节点处理完成，共生成{len(processor.nodes)}个节点的订阅")

if __name__ == "__main__":
    main()