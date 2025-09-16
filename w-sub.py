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

# 导入新创建的模块
from node_merger import NodeMerger
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
    @staticmethod
    def load_config(config_file=None):
        """加载配置，优先使用configs/config.txt"""
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
        
        # 添加配置文件的可能路径，优先使用configs/config.txt
        current_dir = os.path.dirname(os.path.abspath(__file__))
        possible_paths.extend([
            os.path.join(current_dir, "configs", "config.txt"),  # 优先使用configs子目录
            os.path.join(current_dir, "config.txt"),
            "configs/config.txt",
            "config.txt"
        ])
        
        # 尝试所有可能的路径
        for path in possible_paths:
            try:
                if os.path.exists(path):
                    logger.info(f"尝试加载配置文件: {path}")
                    with open(path, 'r', encoding='utf-8') as f:
                        config["SOURCES"] = []  # 清空默认源，优先使用配置文件中的源
                        
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
                logger.error(f"尝试加载配置文件 {path} 失败: {str(e)}")
        
        # 如果没有加载到配置文件或配置文件中没有节点源，使用默认节点源
        if not config_loaded:
            logger.warning("未能从配置文件加载节点源，将使用内置默认节点源")
            config["SOURCES"] = DEFAULT_SOURCES.copy()
        elif not config["SOURCES"]:
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
        # 添加调试信息：显示当前工作目录和输出目录的绝对路径
        logger.debug(f"当前工作目录: {os.getcwd()}")
        logger.debug(f"输出目录绝对路径: {os.path.abspath(self.output_dir)}")
    
    def _ensure_output_dir(self):
        """确保输出目录存在"""
        # 首先尝试使用绝对路径
        absolute_output_dir = os.path.abspath(self.output_dir)
        
        # 尝试创建目录
        try:
            if not os.path.exists(absolute_output_dir):
                os.makedirs(absolute_output_dir, exist_ok=True)
                logger.info(f"已创建输出目录: {absolute_output_dir}")
            else:
                logger.info(f"输出目录已存在: {absolute_output_dir}")
            # 使用绝对路径作为输出目录
            self.output_dir = absolute_output_dir
        except Exception as e:
            logger.error(f"创建输出目录失败: {str(e)}")
            # 尝试使用用户文档目录作为备选
            try:
                # 移除重复的import os语句
                # 获取用户文档目录
                docs_dir = os.path.expanduser("~")
                if os.name == 'nt':  # Windows系统
                    docs_dir = os.path.join(docs_dir, "Documents")
                
                # 在文档目录下创建输出文件夹
                fallback_dir = os.path.join(docs_dir, "w-sub-output")
                if not os.path.exists(fallback_dir):
                    os.makedirs(fallback_dir, exist_ok=True)
                self.output_dir = fallback_dir
                logger.warning(f"将使用备用目录作为输出目录: {fallback_dir}")
            except Exception as inner_e:
                # 最后的备选：使用当前目录
                logger.error(f"创建备用目录也失败: {str(inner_e)}")
                self.output_dir = os.getcwd()
                logger.warning(f"将使用当前目录作为输出目录: {self.output_dir}")
    
    def _get_output_path(self, filename):
        """获取文件的完整输出路径"""
        return os.path.join(self.output_dir, filename)
    
    def generate_subscription(self, nodes, output_file):
        """生成订阅文件"""
        try:
            # 获取完整的输出路径
            full_output_path = self._get_output_path(output_file)
            logger.info(f"准备生成订阅文件: {full_output_path}，包含{len(nodes)}个节点")
            
            # 确保输出目录存在（再次确认）
            output_dir = os.path.dirname(full_output_path)
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir, exist_ok=True)
                logger.info(f"确保输出目录存在: {output_dir}")
            
            # 将节点列表转换为字符串
            nodes_text = '\n'.join(nodes)
            
            # Base64编码
            subscription_content = base64.b64encode(
                nodes_text.encode('utf-8')
            ).decode('utf-8')
            
            # 保存到文件
            with open(full_output_path, 'w', encoding='utf-8') as f:
                f.write(subscription_content)
                f.flush()
                # 在Windows系统上，尝试确保数据写入磁盘
                if os.name == 'nt':
                    try:
                        os.fsync(f.fileno())
                    except:
                        pass  # Windows可能不支持fsync，忽略错误
            
            # 验证文件是否成功创建
            if os.path.exists(full_output_path):
                file_size = os.path.getsize(full_output_path)
                if file_size > 0:
                    logger.info(f"订阅已生成并保存到 {full_output_path}，包含{len(nodes)}个节点，文件大小: {file_size}字节")
                else:
                    logger.warning(f"订阅文件已创建但为空: {full_output_path}")
            else:
                logger.warning(f"订阅文件写入后未找到: {full_output_path}")
            
            return subscription_content
        except Exception as e:
            logger.error(f"生成订阅文件{output_file}失败: {str(e)}")
            # 尝试创建空文件，确保文件存在
            try:
                full_output_path = self._get_output_path(output_file)
                with open(full_output_path, 'w', encoding='utf-8') as f:
                    f.write('')
                logger.warning(f"已创建空的{output_file}文件")
            except Exception as inner_e:
                logger.error(f"创建空文件也失败: {str(inner_e)}")
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
    
    # 创建合并器实例并执行处理流程
    merger = NodeMerger(config)
    processor.nodes = merger.merge_nodes()
    
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