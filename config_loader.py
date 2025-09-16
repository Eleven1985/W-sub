# -*- coding: utf-8 -*-
import os
import re
import logging

class ConfigLoader:
    """配置加载器，从配置文件读取节点源和其他设置"""
    
    def __init__(self):
        # 默认节点源列表
        self.DEFAULT_SOURCES = [
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
    
    def load_config(self):
        """加载配置，优先使用configs/config.txt"""
        config = {
            "SOURCES": [],
            "TIMEOUT": 8,  # 增加超时时间
            "OUTPUT_ALL_FILE": "subscription_all.txt",
            "OUTPUT_BEST_FILE": "subscription_best.txt",
            "WORKERS": 10,
            "MAX_RETRY": 3,  # 增加重试次数
            "BEST_NODES_COUNT": 50,
            "TEST_TIMEOUT": 4  # 增加测试超时时间
        }
        
        # 尝试多个可能的配置文件路径
        possible_paths = []
        current_dir = os.path.dirname(os.path.abspath(__file__))
        possible_paths.extend([
            os.path.join(current_dir, "configs", "config.txt"),  # 优先使用configs子目录
            os.path.join(current_dir, "config.txt"),
            "configs/config.txt",
            "config.txt"
        ])
        
        # 尝试所有可能的路径
        config_loaded = False
        for path in possible_paths:
            try:
                if os.path.exists(path):
                    logging.info(f"尝试加载配置文件: {path}")
                    with open(path, 'r', encoding='utf-8') as f:
                        config["SOURCES"] = []  # 清空默认源
                        
                        for line in f:
                            line = line.strip()
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
                                    if key in ["TIMEOUT", "WORKERS", "MAX_RETRY", "BEST_NODES_COUNT", "TEST_TIMEOUT"]:
                                        try:
                                            config[key] = int(value)
                                        except ValueError:
                                            logging.warning(f"配置项 {key} 值无效，使用默认值")
                                    else:
                                        config[key] = value
                            # 简化格式：直接识别URL
                            elif re.match(r'^https?://', line):
                                config["SOURCES"].append(line)
                    
                    logging.info(f"成功加载配置文件: {path}")
                    config_loaded = True
                    break
            except Exception as e:
                logging.error(f"加载配置文件 {path} 失败: {str(e)}")
        
        # 如果没有加载到配置文件或配置文件中没有节点源，使用默认节点源
        if not config_loaded:
            logging.warning("未能从配置文件加载节点源，将使用内置默认节点源")
            config["SOURCES"] = self.DEFAULT_SOURCES.copy()
        elif not config["SOURCES"]:
            logging.warning("配置文件中没有有效的节点源，将使用内置默认节点源")
            config["SOURCES"] = self.DEFAULT_SOURCES.copy()
        
        logging.info(f"成功加载配置，共 {len(config['SOURCES'])} 个节点源")
        return config